import csv
import hashlib
import json
import os
from pathlib import Path

import duckdb
import typer
import yaml
from pydantic import BaseModel

from evombl.analysis.paired_inhibitors import run_paired_ic50_analysis
from evombl.chemistry.standardize import standardize_smiles
from evombl.configuration import load_metadata_policy, load_yaml, validate_configuration
from evombl.domain import (
    AssayRecord,
    CompoundRecord,
    EvidenceSourceRecord,
    ExperimentalBatchRecord,
    MeasurementRecord,
    ProteinVariantRecord,
)
from evombl.domain.bibliographic import MetadataCandidateRecord
from evombl.domain.enums import SourceType
from evombl.ingestion.bibliographic import (
    PUBMED_NORMALIZER_VERSION,
    CandidatePersistenceConflictError,
    NondeterministicNormalizationError,
    candidate_from_capture,
    compare_candidates,
    normalize_doi,
    record_pubmed_processing,
    save_candidate,
    triage,
)
from evombl.ingestion.metadata import CrossrefAdapter, EuropePmcAdapter, PubmedAdapter
from evombl.proteins.identity_registry import verify_identity_registry
from evombl.proteins.sequences import normalize_sequence, sequence_hash
from evombl.provenance.manifests import write_manifest
from evombl.scientific_extraction import build_outputs, validate_and_report
from evombl.settings import Settings
from evombl.storage.database import (
    initialize_database,
    verify_integrity,
)
from evombl.storage.database import (
    migrate as run_migrations,
)
from evombl.storage.database import (
    schema_version as read_schema_version,
)
from evombl.storage.repositories import EvidenceSourceRepository, stable_hash, stable_json

app = typer.Typer(help="EvoMBL evidence infrastructure.")


@app.command("verify-imp-identity-registry")
def verify_imp_identity_registry(
    registry_path: Path = Path("data/curated/identities/imp_escape_core/identity_registry.csv"),
    fasta_path: Path = Path("data/curated/identities/imp_escape_core/sequences.fasta"),
    report_dir: Path = Path("reports/batch-3c1a"),
) -> None:
    try:
        identities, sequences, comparisons = verify_identity_registry(
            registry_path, fasta_path, report_dir
        )
    except ValueError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc
    typer.echo(
        f"IMP identity registry valid: {identities} identities, "
        f"{sequences} sequences, {comparisons} comparisons"
    )


@app.command("validate-scientific-extraction")
def validate_scientific_extraction(
    input_path: Path = Path("data/curated/pilot/papers-001-003/measurements.csv"),
    parquet_path: Path = Path("data/curated/pilot/papers-001-003/measurements.parquet"),
    report_path: Path = Path("reports/batch-3a/measurement-qc.csv"),
) -> None:
    try:
        count = validate_and_report(input_path, parquet_path, report_path)
    except ValueError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc
    typer.echo(f"Scientific extraction valid: {count} observations")


@app.command("build-evidence-matrix")
def build_evidence_matrix(
    input_path: Path = Path("data/curated/pilot/papers-001-003/measurements.csv"),
    matrix_path: Path = Path("reports/batch-3a/variant-inhibitor-evidence.csv"),
    summary_path: Path = Path("reports/batch-3a/assay-context-summary.csv"),
    readiness_path: Path = Path("reports/batch-3a/readiness.md"),
) -> None:
    try:
        rows, columns = build_outputs(input_path, matrix_path, summary_path, readiness_path)
    except ValueError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc
    typer.echo(f"Evidence matrix written: {rows} rows x {columns} columns")


@app.command("analyze-paired-ic50")
def analyze_paired_ic50(
    input_path: Path = Path("data/curated/pilot/papers-001-003/measurements.csv"),
    imp14_adjudication_path: Path = Path(
        "data/curated/identities/imp_escape_core/imp14_engineered_mutants.csv"
    ),
    report_dir: Path = Path("reports/batch-3d1"),
) -> None:
    try:
        observations, pairs, republications = run_paired_ic50_analysis(
            input_path, imp14_adjudication_path, report_dir
        )
    except ValueError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(1) from exc
    typer.echo(
        f"Paired IC50 analysis valid: {observations} observations, {pairs} pairs, "
        f"{republications} republished Paper 3 pairs"
    )


@app.command("migrate")
def migrate(path: Path = Path("data/evombl.duckdb")) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    typer.echo(f"Schema version {run_migrations(path)}")


@app.command("schema-version")
def schema_version(path: Path = Path("data/evombl.duckdb")) -> None:
    typer.echo(read_schema_version(path))


@app.command("verify-evidence-graph")
def verify_evidence_graph(path: Path = Path("data/evombl.duckdb")) -> None:
    verify_data(path)


@app.command("register-seed-sources")
def register_seed_sources(
    path: Path = Path("data/evombl.duckdb"), config: Path = Path("config/seed_sources.yaml")
) -> None:
    run_migrations(path)
    payload = yaml.safe_load(config.read_text(encoding="utf-8"))
    entries = payload.get("sources", [])
    if not isinstance(entries, list):
        raise typer.BadParameter("seed sources must be a list")
    inserted = 0
    with duckdb.connect(str(path)) as connection:
        for entry in entries:
            doi = str(entry["doi"])
            seed_id = str(entry["seed_id"])
            existing = connection.execute(
                "SELECT source_id FROM source_identifiers WHERE scheme='doi' AND lower(value)=lower(?)",
                [doi],
            ).fetchone()
            source_id = str(existing[0]) if existing else seed_id.replace("EVO-SEED-", "EVO-SRC-")
            if not existing:
                record = EvidenceSourceRecord(
                    source_id=source_id,
                    source_type=SourceType.LITERATURE,
                    doi=doi,
                    pmid=entry.get("pmid"),
                    notes=f"metadata_pending_verification; purpose={entry['purpose']}",
                )
                inserted += int(EvidenceSourceRepository().insert(connection, record))
            identifier_id = (
                "EVO-ID-" + hashlib.sha256(("doi:" + doi.lower()).encode()).hexdigest()[:16].upper()
            )
            connection.execute(
                "INSERT OR IGNORE INTO source_identifiers(identifier_id,source_id,scheme,value) VALUES (?,?,?,?)",
                [identifier_id, source_id, "doi", doi],
            )
            connection.execute(
                "INSERT OR IGNORE INTO seed_source_registry(seed_id,source_id,requested_doi,requested_pmid,purpose) VALUES (?,?,?,?,?)",
                [seed_id, source_id, doi, entry.get("pmid"), entry["purpose"]],
            )
    typer.echo(f"Registered {len(entries)} seed sources ({inserted} new)")


@app.command("preflight-metadata-retrieval")
def preflight_metadata_retrieval(config_dir: Path = Path("config"), offline: bool = False) -> None:
    errors = validate_configuration(config_dir)
    settings = Settings(config_dir=config_dir)
    if not offline and not settings.contact_email:
        errors.append("EVOMBL_CONTACT_EMAIL is required for network retrieval")
    if errors:
        for error in errors:
            typer.echo(error, err=True)
        raise typer.Exit(1)
    policy = load_metadata_policy(config_dir)
    typer.echo(
        f"Metadata preflight valid ({policy.policy_version}; offline={str(offline).lower()})"
    )


def _seed_rows(config_dir: Path) -> list[dict[str, object]]:
    rows = load_yaml(config_dir / "seed_sources.yaml")["sources"]
    assert isinstance(rows, list)
    return sorted(rows, key=lambda row: str(row["seed_id"]))


@app.command("fetch-seed-source-metadata")
def fetch_seed_source_metadata(
    path: Path = Path("data/evombl.duckdb"),
    config_dir: Path = Path("config"),
    offline: bool = False,
    refresh: bool = False,
    source_id: str | None = None,
    provider: str | None = None,
    limit: int | None = None,
    continue_on_error: bool = True,
) -> None:
    preflight_metadata_retrieval(config_dir, offline)
    run_migrations(path)
    settings = Settings(config_dir=config_dir)
    contact = settings.contact_email or "offline@example.invalid"
    allowed = {"crossref", "europe_pmc", "ncbi_pubmed"}
    if provider and provider not in allowed:
        raise typer.BadParameter(f"provider must be one of {sorted(allowed)}")
    seeds = _seed_rows(config_dir)
    if source_id:
        seeds = [row for row in seeds if row["seed_id"] == source_id]
    if not seeds:
        raise typer.BadParameter("source filter matched no seed")
    if limit is not None:
        seeds = seeds[:limit]
    failures = []
    normalization_failures = []
    persistence_failures = []
    saved = 0
    with duckdb.connect(str(path)) as connection:
        for seed in seeds:
            sid = str(seed["seed_id"])
            mapped = connection.execute(
                "SELECT source_id FROM seed_source_registry WHERE seed_id=?", [sid]
            ).fetchone()
            if not mapped:
                raise typer.BadParameter(
                    f"{sid} is not registered; run register-seed-sources first"
                )
            evidence_id = str(mapped[0])
            queries = [("crossref", str(seed["doi"])), ("europe_pmc", f"DOI:{seed['doi']}")]
            if seed.get("pmid"):
                queries.extend(
                    [("europe_pmc", f"EXT_ID:{seed['pmid']}"), ("ncbi_pubmed", str(seed["pmid"]))]
                )
            for name, query in queries:
                if provider and name != provider:
                    continue
                cls = {
                    "crossref": CrossrefAdapter,
                    "europe_pmc": EuropePmcAdapter,
                    "ncbi_pubmed": PubmedAdapter,
                }[name]
                try:
                    capture = cls(
                        Path("data/raw/api"),
                        contact,
                        "EvoMBL/0.1",
                        connection=connection,
                        source_id=evidence_id,
                        ncbi_api_key=bool(os.getenv("NCBI_API_KEY")),
                    ).fetch(query, offline=offline, refresh=refresh)
                    try:
                        candidate = candidate_from_capture(sid, evidence_id, capture)
                    except LookupError as exc:
                        if name == "ncbi_pubmed":
                            record_pubmed_processing(
                                connection, capture, "record_not_found", error=exc
                            )
                        continue
                    except Exception as exc:
                        if name == "ncbi_pubmed":
                            record_pubmed_processing(
                                connection, capture, "normalization_failure", error=exc
                            )
                            normalization_failures.append(
                                f"{sid}:{name}:normalization_failure:{type(exc).__name__}"
                            )
                            continue
                        raise
                    normalizer_version = (
                        PUBMED_NORMALIZER_VERSION
                        if name == "ncbi_pubmed"
                        else "bibliographic-normalizer-v1"
                    )
                    try:
                        result = save_candidate(connection, candidate, query, normalizer_version)
                    except NondeterministicNormalizationError as exc:
                        if name == "ncbi_pubmed":
                            record_pubmed_processing(
                                connection,
                                capture,
                                "nondeterministic_normalization",
                                candidate_id=candidate.candidate_id,
                                error=exc,
                            )
                        persistence_failures.append(
                            f"{sid}:{name}:nondeterministic_normalization:{type(exc).__name__}"
                        )
                        continue
                    except CandidatePersistenceConflictError as exc:
                        if name == "ncbi_pubmed":
                            record_pubmed_processing(
                                connection,
                                capture,
                                "candidate_persistence_conflict",
                                candidate_id=candidate.candidate_id,
                                error=exc,
                            )
                        persistence_failures.append(
                            f"{sid}:{name}:candidate_persistence_conflict:{type(exc).__name__}"
                        )
                        continue
                    saved += int(result.inserted)
                    if name == "ncbi_pubmed":
                        record_pubmed_processing(
                            connection,
                            capture,
                            result.outcome,
                            candidate_id=result.candidate_id,
                            normalized_record_hash=result.normalized_record_hash,
                            semantic_bibliographic_hash=result.semantic_bibliographic_hash,
                            predecessor_candidate_id=result.predecessor_candidate_id,
                        )
                except Exception as exc:
                    failures.append(f"{sid}:{name}:{type(exc).__name__}")
                    if not continue_on_error:
                        break
    typer.echo(
        f"Metadata retrieval completed: {saved} new candidates; {len(failures)} technical failures; "
        f"{len(normalization_failures)} normalization failures; "
        f"{len(persistence_failures)} persistence failures"
    )
    if failures:
        for item in failures:
            typer.echo(item, err=True)
        raise typer.Exit(1)
    if normalization_failures:
        for item in normalization_failures:
            typer.echo(item, err=True)
        raise typer.Exit(1)
    if persistence_failures:
        for item in persistence_failures:
            typer.echo(item, err=True)
        raise typer.Exit(1)


def _load_candidates(
    connection: duckdb.DuckDBPyConnection, seed_id: str
) -> list[MetadataCandidateRecord]:
    return [
        MetadataCandidateRecord.model_validate_json(row[0])
        for row in connection.execute(
            "SELECT record_json FROM metadata_candidates WHERE seed_id=? "
            "ORDER BY provider,created_at NULLS FIRST,candidate_id",
            [seed_id],
        ).fetchall()
    ]


@app.command("compare-source-metadata")
def compare_source_metadata(
    path: Path = Path("data/evombl.duckdb"), config_dir: Path = Path("config")
) -> None:
    comparisons = 0
    with duckdb.connect(str(path)) as connection:
        for seed in _seed_rows(config_dir):
            candidates = _load_candidates(connection, str(seed["seed_id"]))
            latest = {c.provider: c for c in candidates}
            values = list(latest.values())
            for index, a in enumerate(values):
                for b in values[index + 1 :]:
                    for record in compare_candidates(a, b):
                        digest = stable_hash(record)
                        connection.execute(
                            "INSERT OR IGNORE INTO metadata_comparisons(comparison_id,seed_id,source_id,provider_a,provider_b,field_name,classification,record_json,record_hash) VALUES (?,?,?,?,?,?,?,?,?)",
                            [
                                record.comparison_id,
                                record.seed_id,
                                record.source_id,
                                record.provider_a,
                                record.provider_b,
                                record.field_name,
                                record.classification,
                                stable_json(record),
                                digest,
                            ],
                        )
                        comparisons += 1
        _build_bibliographic_audits(connection, config_dir)
    typer.echo(f"Compared metadata: {comparisons} field comparisons")


def _build_bibliographic_audits(connection: duckdb.DuckDBPyConnection, config_dir: Path) -> None:
    conflicts = 0
    for seed in _seed_rows(config_dir):
        sid = str(seed["seed_id"])
        source_row = connection.execute(
            "SELECT source_id FROM seed_source_registry WHERE seed_id=?", [sid]
        ).fetchone()
        if not source_row:
            continue
        source_id = str(source_row[0])
        candidates = _load_candidates(connection, sid)
        requested = normalize_doi(str(seed["doi"]))
        matching = [c for c in candidates if normalize_doi(c.doi) == requested]
        material_row = connection.execute(
            "SELECT count(*) FROM metadata_comparisons WHERE seed_id=? AND classification IN ('material_conflict','identifier_conflict')",
            [sid],
        ).fetchone()
        material = int(material_row[0]) if material_row else 0
        success_row = connection.execute(
            "SELECT count(*) FROM source_retrieval_events WHERE source_id=? AND outcome='success'",
            [source_id],
        ).fetchone()
        successful_retrievals = int(success_row[0]) if success_row else 0
        status = (
            "metadata_conflict"
            if material
            else "metadata_verified"
            if matching
            else "identifier_not_found"
            if successful_retrievals
            else "retrieval_pending"
        )
        conflicts += int(bool(material))
        title = matching[0].title if matching else None
        relevance, rule = triage(title, str(seed["purpose"]))
        pmid = str(seed.get("pmid")) if seed.get("pmid") else None
        link = bool(
            pmid
            and any(
                c.pmid == pmid and normalize_doi(c.doi) == requested
                for c in candidates
                if c.provider in {"europe_pmc", "ncbi_pubmed"}
            )
        )
        open_values = [c.open_access for c in candidates if c.open_access is not None]
        record: dict[str, object] = {
            "seed_id": sid,
            "source_id": source_id,
            "status": status,
            "verified_doi": requested if status == "metadata_verified" else None,
            "verified_pmid": pmid if link else None,
            "doi_pmid_link_verified": link,
            "relevance_status": relevance,
            "relevance_rule": rule,
            "open_access": True if True in open_values else False if open_values else None,
            "licence": next((c.licence for c in candidates if c.licence), None),
            "manual_review_required": status != "metadata_verified"
            or relevance != "likely_relevant",
            "notes": [],
        }
        payload = json.dumps(record, sort_keys=True, separators=(",", ":"))
        connection.execute(
            "INSERT OR REPLACE INTO bibliographic_audits(seed_id,source_id,status,verified_doi,verified_pmid,doi_pmid_link_verified,relevance_status,open_access,manual_review_required,record_json,record_hash) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            [
                sid,
                source_id,
                status,
                record["verified_doi"],
                record["verified_pmid"],
                link,
                relevance,
                record["open_access"],
                record["manual_review_required"],
                payload,
                hashlib.sha256(payload.encode()).hexdigest(),
            ],
        )
    typer.echo(f"Bibliographic registry evaluated: {conflicts} seeds with metadata conflicts")


@app.command("verify-bibliographic-registry")
def verify_bibliographic_registry(
    path: Path = Path("data/evombl.duckdb"), config_dir: Path = Path("config")
) -> None:
    expected = {str(row["seed_id"]) for row in _seed_rows(config_dir)}
    with duckdb.connect(str(path), read_only=True) as connection:
        actual = {
            str(row[0])
            for row in connection.execute("SELECT seed_id FROM bibliographic_audits").fetchall()
        }
        orphan_row = connection.execute(
            "SELECT count(*) FROM metadata_candidates c LEFT JOIN source_retrieval_events e ON c.retrieval_event_id=e.retrieval_id WHERE e.retrieval_id IS NULL"
        ).fetchone()
        orphan_candidates = int(orphan_row[0]) if orphan_row else 0
    missing = sorted(expected - actual)
    if missing or orphan_candidates:
        if missing:
            typer.echo(f"Missing bibliographic audit rows: {', '.join(missing)}", err=True)
        if orphan_candidates:
            typer.echo(
                f"Metadata candidates without retrieval events: {orphan_candidates}", err=True
            )
        raise typer.Exit(1)
    typer.echo(f"Bibliographic registry valid ({len(actual)} seed audits; read-only)")


def _write_query_csv(connection: duckdb.DuckDBPyConnection, output: Path, query: str) -> int:
    result = connection.execute(query)
    rows = result.fetchall()
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow([column[0] for column in result.description])
        writer.writerows(rows)
    return len(rows)


@app.command("export-bibliographic-audit")
def export_bibliographic_audit(
    path: Path = Path("data/evombl.duckdb"),
    output_dir: Path = Path("reports/batch-2c1"),
    config_dir: Path = Path("config"),
) -> None:
    with duckdb.connect(str(path), read_only=True) as connection:
        queries = {
            "source-registry.csv": "SELECT seed_id,source_id,status,verified_doi,verified_pmid,doi_pmid_link_verified,relevance_status,open_access,manual_review_required FROM bibliographic_audits ORDER BY seed_id",
            "provider-metadata-candidates.csv": "SELECT candidate_id,seed_id,source_id,provider,doi,pmid,pmcid,title,publication_year,response_hash,retrieval_event_id FROM metadata_candidates ORDER BY seed_id,provider,candidate_id",
            "provider-comparison.csv": "SELECT comparison_id,seed_id,provider_a,provider_b,field_name,classification FROM metadata_comparisons ORDER BY seed_id,provider_a,provider_b,field_name",
            "identifier-conflicts.csv": "SELECT comparison_id,seed_id,provider_a,provider_b,field_name,classification FROM metadata_comparisons WHERE classification='identifier_conflict' ORDER BY seed_id,field_name",
            "retrieval-events.csv": "SELECT retrieval_id,source_id,provider,requested_identifier,request_timestamp,completion_timestamp,outcome,http_status,attempt_count,response_hash,response_path,offline,adapter_version,configuration_version FROM source_retrieval_events ORDER BY request_timestamp,retrieval_id",
            "legal-access-audit.csv": "SELECT seed_id,open_access,json_extract_string(record_json,'$.licence') licence,manual_review_required FROM bibliographic_audits ORDER BY seed_id",
            "purpose-relevance-triage.csv": "SELECT seed_id,relevance_status,json_extract_string(record_json,'$.relevance_rule') relevance_rule FROM bibliographic_audits ORDER BY seed_id",
            "manual-review-queue.csv": "SELECT seed_id,status,relevance_status FROM bibliographic_audits WHERE manual_review_required ORDER BY seed_id",
        }
        counts = {
            name: _write_query_csv(connection, output_dir / name, query)
            for name, query in queries.items()
        }
        provider_counts = dict(
            connection.execute(
                "SELECT provider,count(DISTINCT seed_id) FROM metadata_candidates GROUP BY provider"
            ).fetchall()
        )
        audit = connection.execute(
            "SELECT count(*),sum(CASE WHEN doi_pmid_link_verified THEN 1 ELSE 0 END),sum(CASE WHEN status='metadata_conflict' THEN 1 ELSE 0 END),sum(CASE WHEN status='identifier_not_found' THEN 1 ELSE 0 END),sum(CASE WHEN manual_review_required THEN 1 ELSE 0 END),sum(CASE WHEN open_access THEN 1 ELSE 0 END) FROM bibliographic_audits"
        ).fetchone()
    seeds = _seed_rows(config_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "source-audit.md").write_text(
        "# Batch 2C1 source audit\n\nAPI metadata is bibliographic evidence only, not scientific verification. Identifier conflicts remain unresolved. No bioactivity data were curated.\n\n"
        + "\n".join(
            f"- {row['seed_id']}: requested DOI {row['doi']}"
            + (f"; PMID {row['pmid']}" if row.get("pmid") else "")
            + f"; intended purpose: {row['purpose']}"
            for row in seeds
        )
        + "\n",
        encoding="utf-8",
    )
    total, links, conflicts, not_found, manual, open_count = audit or (0, 0, 0, 0, 0, 0)
    (output_dir / "readiness.md").write_text(
        f"# Batch 2C1 readiness\n\n- Seed candidates: {len(seeds)}\n- Resolved by Crossref: {provider_counts.get('crossref', 0)}\n- Resolved by Europe PMC: {provider_counts.get('europe_pmc', 0)}\n- Resolved by PubMed: {provider_counts.get('ncbi_pubmed', 0)}\n- Verified DOI–PMID links: {links or 0}\n- Metadata conflicts: {conflicts or 0}\n- Not found: {not_found or 0}\n- Manual review: {manual or 0}\n- Official open-full-text indication: {open_count or 0}\n- Ready for scientific full-text curation: {'yes' if total == len(seeds) and not conflicts and not not_found and not manual else 'no'}\n",
        encoding="utf-8",
    )
    typer.echo(
        f"Exported bibliographic audit to {output_dir} ({sum(counts.values())} tabular rows)"
    )


@app.command("verify-source-registry")
def verify_source_registry(
    path: Path = Path("data/evombl.duckdb"), json_output: bool = False
) -> None:
    errors: list[str] = []
    with duckdb.connect(str(path), read_only=True) as connection:
        duplicates = connection.execute(
            "SELECT scheme,value,count(*) FROM source_identifiers GROUP BY ALL HAVING count(*)>1"
        ).fetchall()
        errors.extend(f"duplicate identifier: {row[0]}:{row[1]}" for row in duplicates)
        orphans = connection.execute(
            "SELECT identifier_id FROM source_identifiers i LEFT JOIN evidence_sources s USING(source_id) WHERE s.source_id IS NULL"
        ).fetchall()
        errors.extend(f"orphan identifier: {row[0]}" for row in orphans)
    if json_output:
        typer.echo(json.dumps({"valid": not errors, "errors": errors}, sort_keys=True))
    elif errors:
        for error in errors:
            typer.echo(error, err=True)
    else:
        typer.echo("Source registry valid")
    if errors:
        raise typer.Exit(1)


@app.command("export-source-registry")
def export_source_registry(
    path: Path = Path("data/evombl.duckdb"),
    output: Path = Path("reports/batch-2/source-registry-export.csv"),
) -> None:
    with duckdb.connect(str(path), read_only=True) as connection:
        rows = connection.execute(
            "SELECT s.source_id,s.source_type,i.scheme,i.value FROM evidence_sources s LEFT JOIN source_identifiers i USING(source_id) ORDER BY s.source_id,i.scheme,i.value"
        ).fetchall()
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow(["source_id", "source_type", "identifier_scheme", "identifier_value"])
        writer.writerows(rows)
    typer.echo(f"Exported {len(rows)} source rows to {output}")


@app.command("init-db")
def init_db(path: Path = Path("data/evombl.duckdb")) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    initialize_database(path)
    typer.echo(f"Initialized {path}")


@app.command("validate-config")
def validate_config(config_dir: Path = Path("config")) -> None:
    errors = validate_configuration(config_dir)
    if errors:
        for error in errors:
            typer.echo(error, err=True)
        raise typer.Exit(1)
    typer.echo("Configuration valid")


@app.command("validate-compound")
def validate_compound(smiles: str) -> None:
    typer.echo(json.dumps(standardize_smiles(smiles).__dict__, indent=2))


@app.command("validate-protein")
def validate_protein(sequence: str) -> None:
    normalized = normalize_sequence(sequence)
    typer.echo(json.dumps({"length": len(normalized), "sha256": sequence_hash(normalized)}))


@app.command("export-schemas")
def export_schemas(output_dir: Path = Path("schemas")) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    models: dict[str, type[BaseModel]] = {
        "compound": CompoundRecord,
        "protein_variant": ProteinVariantRecord,
        "assay": AssayRecord,
        "measurement": MeasurementRecord,
        "evidence_source": EvidenceSourceRecord,
        "experimental_batch": ExperimentalBatchRecord,
    }
    for name, model in models.items():
        target = output_dir / f"{name}.schema.json"
        target.write_text(json.dumps(model.model_json_schema(), indent=2) + "\n", encoding="utf-8")
    typer.echo(f"Exported {len(models)} schemas")


@app.command("verify-data")
def verify_data(path: Path = Path("data/evombl.duckdb")) -> None:
    errors = verify_integrity(path)
    if errors:
        for error in errors:
            typer.echo(error, err=True)
        raise typer.Exit(1)
    typer.echo("Data integrity valid")


@app.command("create-manifest")
def create_manifest(root: Path = Path("."), output: Path = Path("manifest.json")) -> None:
    write_manifest(root.resolve(), output.resolve())
    typer.echo(f"Wrote {output}")
