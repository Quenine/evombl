import csv
import hashlib
import json
from pathlib import Path

import duckdb
import typer
import yaml
from pydantic import BaseModel

from evombl.chemistry.standardize import standardize_smiles
from evombl.configuration import validate_configuration
from evombl.domain import (
    AssayRecord,
    CompoundRecord,
    EvidenceSourceRecord,
    ExperimentalBatchRecord,
    MeasurementRecord,
    ProteinVariantRecord,
)
from evombl.domain.enums import SourceType
from evombl.proteins.sequences import normalize_sequence, sequence_hash
from evombl.provenance.manifests import write_manifest
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
from evombl.storage.repositories import EvidenceSourceRepository

app = typer.Typer(help="EvoMBL evidence infrastructure.")


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
            source_id = "EVO-SRC-" + hashlib.sha256(doi.lower().encode()).hexdigest()[:16].upper()
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
    typer.echo(f"Registered {len(entries)} seed sources ({inserted} new)")


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
