import csv
import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path

from evombl.proteins.sequences import normalize_source_sequence, sequence_hash

REGISTRY_FIELDS = (
    "variant_name",
    "enzyme_family",
    "preferred_protein_accession",
    "secondary_protein_accession",
    "source_nucleotide_accession",
    "secondary_nucleotide_accession",
    "sequence_status",
    "full_length_length",
    "full_length_sequence_sha256",
    "reference_variant",
    "paper_reported_mutation",
    "paper_numbering_scheme",
    "independently_observed_precursor_difference",
    "verification_status",
    "quality_flags",
    "curator_note",
)
PROVENANCE_FIELDS = (
    "variant_name",
    "claim_scope",
    "source_kind",
    "source_name",
    "source_locator",
    "source_doi",
    "accession",
    "accessed_date",
    "curator_note",
)
ENGINEERED_MUTANT_FIELDS = (
    "mutant_id",
    "reference_variant",
    "source_doi",
    "table2_bbl_label",
    "table3_bbl_label",
    "narrative_label",
    "supplement_label",
    "precursor_mutation",
    "adjudicated_bbl_label",
    "adjudication_status",
    "quality_flags",
    "curator_note",
)
PRIMER_FIELDS = (
    "mutant_id",
    "supplement_label",
    "forward_primer",
    "reverse_primer",
    "translated_mutant_window",
    "wild_type_window",
    "inferred_precursor_mutation",
    "source_doi",
    "source_locator",
    "evidence_status",
    "curator_note",
)
IMP14_MUTATION_IDS = {
    "IMP14-MUT-01",
    "IMP14-MUT-02",
    "IMP14-MUT-03",
    "IMP14-MUT-04",
    "IMP14-MUT-05",
}
IMP14_PRECURSOR_MUTATIONS = {"S47G", "H134N", "N137S", "D181Y", "Y185N"}
MEASUREMENT_METADATA_IDS = {f"EVO-OBS-P3-{number:03d}" for number in range(16, 26)}
NUMERIC_EVIDENCE_FIELDS = (
    "observation_id",
    "value",
    "relation",
    "fitted_value",
    "unit",
    "compound",
    "endpoint",
    "assay_system",
    "directness",
    "replicate_count",
    "fixed_inhibitor_concentration",
    "fixed_inhibitor_concentration_unit",
    "antibiotic_partner",
)
NUMERIC_EVIDENCE_HASH = "88e9ab488c7491f9fe64db8afd21719d1d793fc6e22e4de294c32a498478d5f6"
NON_TARGET_MEASUREMENTS_HASH = "6b8e0e4b25a46b049ccdfc5122abaac90a2196aa214457e66e8ba178e1cec333"
PENDING_SEQUENCE_STATUS = "accession_verified_sequence_payload_pending"
REFERENCE_SEQUENCE_MISSING_FLAG = "reference_sequence_not_in_pack"
VERIFIED_PRECURSOR_STATUS = "precursor_difference_verified"
RELATIONSHIP_TERMS = ("relationship", "comparison", "precursor difference")
CONTRADICTORY_NOTE_PATTERNS = (
    r"cannot be independently checked",
    r"cannot be checked",
    r"remains pending",
    r"remains unverified",
    r"has not been independently verified",
)
EXPECTED_VARIANTS = {
    "IMP-1",
    "IMP-2",
    "IMP-4",
    "IMP-6",
    "IMP-10",
    "IMP-14",
    "IMP-19",
    "IMP-26",
    "IMP-59",
}


@dataclass(frozen=True)
class FastaRecord:
    accession: str
    variant_name: str
    sequence: str


@dataclass(frozen=True)
class AuthorisedComparison:
    reference_variant: str
    variant: str
    expected_difference: str
    paper_reported_mutation: str


AUTHORISED_COMPARISONS = (
    AuthorisedComparison("IMP-1", "IMP-6", "S214G", "Ser262Gly"),
    AuthorisedComparison("IMP-1", "IMP-10", "V49F", "Val67Phe"),
    AuthorisedComparison("IMP-4", "IMP-26", "V49F", "Val67Phe"),
    AuthorisedComparison("IMP-2", "IMP-19", "R21A", "Arg38Ala"),
    AuthorisedComparison("IMP-4", "IMP-59", "N185Y", "Asn233Tyr"),
)


def read_fasta(path: Path) -> dict[str, FastaRecord]:
    records: dict[str, FastaRecord] = {}
    accessions: set[str] = set()
    header: str | None = None
    chunks: list[str] = []

    def store() -> None:
        if header is None:
            return
        parts = header.split("|")
        if len(parts) != 2 or not all(parts):
            raise ValueError(f"invalid FASTA header: {header}")
        accession, variant = parts
        if accession in accessions or variant in records:
            raise ValueError("duplicate FASTA accession or variant name")
        sequence, _ = normalize_source_sequence("".join(chunks))
        records[variant] = FastaRecord(accession, variant, sequence)
        accessions.add(accession)

    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith(">"):
            store()
            header = line[1:]
            chunks = []
        else:
            if header is None:
                raise ValueError("FASTA sequence precedes its header")
            chunks.append(line)
    store()
    return records


def read_registry(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        if tuple(reader.fieldnames or ()) != REGISTRY_FIELDS:
            raise ValueError("identity registry columns do not match the required schema")
        rows = list(reader)
    variants = [row["variant_name"] for row in rows]
    if len(variants) != len(set(variants)):
        raise ValueError("duplicate registry variant names")
    accessions = [
        row[field]
        for row in rows
        for field in (
            "preferred_protein_accession",
            "secondary_protein_accession",
            "source_nucleotide_accession",
            "secondary_nucleotide_accession",
        )
        if row[field]
    ]
    if len(accessions) != len(set(accessions)):
        raise ValueError("duplicate registry accessions")
    return rows


def read_source_provenance(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        if tuple(reader.fieldnames or ()) != PROVENANCE_FIELDS:
            raise ValueError("source provenance columns do not match the required schema")
        rows = list(reader)
    pack_expectations = {
        "sources_imp2_imp19.csv": (5, {"IMP-2", "IMP-19"}),
        "sources_imp59.csv": (4, {"IMP-59"}),
    }
    try:
        expected_count, expected_variants = pack_expectations[path.name]
    except KeyError as exc:
        raise ValueError(f"unsupported source provenance pack: {path.name}") from exc
    if len(rows) != expected_count or {row["variant_name"] for row in rows} != expected_variants:
        raise ValueError(f"source provenance pack has invalid cardinality or variants: {path.name}")
    seen: set[tuple[str, str, str, str]] = set()
    for row in rows:
        for field in (
            "variant_name",
            "claim_scope",
            "source_kind",
            "source_name",
            "source_locator",
            "accessed_date",
        ):
            if not row[field]:
                raise ValueError(f"source provenance record missing {field}")
        if row["source_kind"] in {"primary_article", "secondary_article"} and not row["source_doi"]:
            raise ValueError("article source provenance requires a DOI")
        if row["source_kind"] == "curated_database" and not row["source_locator"]:
            raise ValueError("database source provenance requires a stable locator")
        provenance_text = " ".join(row.values()).lower()
        if "immutable raw" in provenance_text and "not an immutable raw" not in provenance_text:
            raise ValueError("source provenance must not claim immutable raw capture")
        identity = (
            row["variant_name"],
            row["claim_scope"],
            row["source_kind"],
            row["source_locator"],
        )
        if identity in seen:
            raise ValueError("duplicate source provenance record")
        seen.add(identity)
    return rows


def _read_required_csv(path: Path, fields: tuple[str, ...]) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        if tuple(reader.fieldnames or ()) != fields:
            raise ValueError(f"{path.name}: columns do not match the required schema")
        rows = list(reader)
    if any(not all(value is not None for value in row.values()) for row in rows):
        raise ValueError(f"{path.name}: row has unexpected fields")
    return rows


def read_imp14_engineered_mutants(path: Path) -> list[dict[str, str]]:
    rows = _read_required_csv(path, ENGINEERED_MUTANT_FIELDS)
    if {row["mutant_id"] for row in rows} != IMP14_MUTATION_IDS or len(rows) != 5:
        raise ValueError("IMP-14 engineered-mutant dataset must contain five unique rows")
    if any(row["reference_variant"] != "IMP-14" for row in rows):
        raise ValueError("IMP-14 engineered mutants must reference IMP-14")
    if any(row["source_doi"] != "10.1128/aac.00297-25" for row in rows):
        raise ValueError("IMP-14 engineered mutants have an unexpected source DOI")
    return rows


def read_imp14_mutagenesis_primers(path: Path) -> list[dict[str, str]]:
    rows = _read_required_csv(path, PRIMER_FIELDS)
    if {row["mutant_id"] for row in rows} != IMP14_MUTATION_IDS or len(rows) != 5:
        raise ValueError("IMP-14 primer dataset must contain five unique rows")
    if any(row["source_doi"] != "10.1128/aac.00297-25.SuF3" for row in rows):
        raise ValueError("IMP-14 primers have an unexpected source DOI")
    if any(row["source_locator"] != "Table S1" for row in rows):
        raise ValueError("IMP-14 primers must be located in Table S1")
    return rows


def _validate_imp14_mutagenesis(
    mutants: list[dict[str, str]], primers: list[dict[str, str]], imp14_sequence: str
) -> list[dict[str, object]]:
    by_id = {row["mutant_id"]: row for row in mutants}
    primer_by_id = {row["mutant_id"]: row for row in primers}
    if set(by_id) != set(primer_by_id):
        raise ValueError("IMP-14 adjudication and primer mutant IDs disagree")
    qc_rows: list[dict[str, object]] = []
    inferred: set[str] = set()
    for mutant_id in sorted(IMP14_MUTATION_IDS):
        primer = primer_by_id[mutant_id]
        mutant = by_id[mutant_id]
        wild_type = primer["wild_type_window"]
        translated = primer["translated_mutant_window"]
        start = imp14_sequence.find(wild_type)
        if start < 0 or imp14_sequence.find(wild_type, start + 1) >= 0:
            raise ValueError(f"{mutant_id}: wild-type window is not uniquely present in IMP-14")
        differences = [
            index
            for index, (left, right) in enumerate(zip(wild_type, translated, strict=True))
            if left != right
        ]
        if len(wild_type) != len(translated) or len(differences) != 1:
            raise ValueError(f"{mutant_id}: primer window must encode exactly one substitution")
        difference = differences[0]
        precursor = f"{wild_type[difference]}{start + difference + 1}{translated[difference]}"
        if (
            precursor != primer["inferred_precursor_mutation"]
            or precursor != mutant["precursor_mutation"]
        ):
            raise ValueError(
                f"{mutant_id}: primer-derived precursor mutation disagrees with curation"
            )
        inferred.add(precursor)
        qc_rows.append(
            {
                "mutant_id": mutant_id,
                "wild_type_residue": wild_type[difference],
                "wild_type_window": wild_type,
                "translated_mutant_window": translated,
                "difference_count": 1,
                "inferred_precursor_mutation": precursor,
                "validation_status": "valid",
            }
        )
    if inferred != IMP14_PRECURSOR_MUTATIONS:
        raise ValueError("IMP-14 primer-derived precursor mutation set is incorrect")
    mut03 = by_id["IMP14-MUT-03"]
    if (mut03["table2_bbl_label"], mut03["table3_bbl_label"], mut03["narrative_label"]) != (
        "N178S",
        "N178S",
        "Asn177Ser",
    ):
        raise ValueError("IMP14-MUT-03 source discrepancy must be preserved")
    mut05 = by_id["IMP14-MUT-05"]
    if (
        mut05["table2_bbl_label"],
        mut05["table3_bbl_label"],
        mut05["supplement_label"],
        mut05["precursor_mutation"],
    ) != ("Y233N", "N233Y", "IMP-14 N185Y", "Y185N"):
        raise ValueError("IMP14-MUT-05 source labels or primer adjudication were altered")
    return qc_rows


def _measurement_hash(rows: list[dict[str, str]]) -> str:
    canonical = json.dumps(rows, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def _validate_measurement_metadata(path: Path) -> list[dict[str, object]]:
    with path.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    if len(rows) != 142:
        raise ValueError("scientific measurement count must remain 142")
    numeric = [{field: row[field] for field in NUMERIC_EVIDENCE_FIELDS} for row in rows]
    if _measurement_hash(numeric) != NUMERIC_EVIDENCE_HASH:
        raise ValueError("scientific numeric evidence changed")
    non_target = [row for row in rows if row["observation_id"] not in MEASUREMENT_METADATA_IDS]
    if _measurement_hash(non_target) != NON_TARGET_MEASUREMENTS_HASH:
        raise ValueError("a non-target scientific measurement row changed")
    target = {
        row["observation_id"]: row
        for row in rows
        if row["observation_id"] in MEASUREMENT_METADATA_IDS
    }
    if set(target) != MEASUREMENT_METADATA_IDS:
        raise ValueError("IMP-14 measurement metadata target rows are incomplete")
    for observation_id, row in target.items():
        expected_label = {
            "EVO-OBS-P3-016": "S65G",
            "EVO-OBS-P3-017": "S65G",
            "EVO-OBS-P3-018": "H174N",
            "EVO-OBS-P3-019": "H174N",
            "EVO-OBS-P3-020": "N178S",
            "EVO-OBS-P3-021": "N178S",
            "EVO-OBS-P3-022": "D227Y",
            "EVO-OBS-P3-023": "D227Y",
            "EVO-OBS-P3-024": "N233Y",
            "EVO-OBS-P3-025": "N233Y",
        }[observation_id]
        if (
            row["source_row_label"] != f"IMP-14 {expected_label}"
            or row["author_reported_mutation"] != expected_label
        ):
            raise ValueError(f"{observation_id}: literal Table 3 mutation label changed")
        if observation_id in {"EVO-OBS-P3-024", "EVO-OBS-P3-025"}:
            if row["quality_flags"] != "source_mutation_label_conflict_adjudicated":
                raise ValueError(f"{observation_id}: source-label conflict flag is required")
            if (
                row["source_row_label"] != "IMP-14 N233Y"
                or row["author_reported_mutation"] != "N233Y"
            ):
                raise ValueError(f"{observation_id}: Table 3 source text must be retained")
            for phrase in (
                "Table S1 row label literally reports N185Y",
                "encodes Y185N",
                "Table 2 reports Y233N",
            ):
                if phrase not in row["curator_note"]:
                    raise ValueError(
                        f"{observation_id}: source conflict adjudication is incomplete"
                    )
        elif row["quality_flags"] != "mutation_identity_adjudicated_from_table_s1":
            raise ValueError(f"{observation_id}: Table S1 adjudication flag is required")
    for observation_id in ("EVO-OBS-P3-020", "EVO-OBS-P3-021"):
        for phrase in ("N137S", "N178S", "Asn177Ser", "conflict is preserved"):
            if phrase not in target[observation_id]["curator_note"]:
                raise ValueError(f"{observation_id}: N178S/N177S conflict note is incomplete")
    return [
        {
            "observation_count_before": 142,
            "observation_count_after": 142,
            "allowed_metadata_changes": 10,
            "numeric_value_relation_fitted_unit_compound_endpoint_changes": 0,
            "non_target_row_changes": 0,
            "validation_status": "valid",
        }
    ]


def _normalise_note(note: str) -> str:
    return re.sub(r"\s+", " ", note.casefold()).strip()


def _verified_note_contradicts_status(note: str) -> bool:
    normalized = _normalise_note(note)
    if not normalized:
        return False
    relation_pattern = "|".join(re.escape(term) for term in RELATIONSHIP_TERMS)
    contradiction_pattern = "|".join(CONTRADICTORY_NOTE_PATTERNS)
    return bool(
        re.search(
            rf"(?:{relation_pattern}).{{0,100}}(?:{contradiction_pattern})|"
            rf"(?:{contradiction_pattern}).{{0,100}}(?:{relation_pattern})",
            normalized,
        )
    )


def _validate_metadata_relationships(
    registry: list[dict[str, str]], fasta: dict[str, FastaRecord]
) -> None:
    by_variant = {row["variant_name"]: row for row in registry}
    for row in registry:
        flags = row["quality_flags"].split("|") if row["quality_flags"] else []
        reference = by_variant.get(row["reference_variant"])
        if (
            any(REFERENCE_SEQUENCE_MISSING_FLAG in flag for flag in flags)
            and reference is not None
            and reference["sequence_status"] == "sequence_captured"
            and reference["variant_name"] in fasta
        ):
            raise ValueError(
                f"{row['variant_name']}: reference sequence missing flag contradicts captured reference"
            )
        if VERIFIED_PRECURSOR_STATUS in row[
            "verification_status"
        ] and _verified_note_contradicts_status(row["curator_note"]):
            raise ValueError(
                f"{row['variant_name']}: curator note contradicts verified precursor difference"
            )


def direct_precursor_differences(reference: str, comparison: str) -> list[str]:
    if len(reference) != len(comparison):
        raise ValueError("authorised precursor sequences have different lengths")
    return [
        f"{left}{position}{right}"
        for position, (left, right) in enumerate(zip(reference, comparison, strict=True), 1)
        if left != right
    ]


def _write_csv(path: Path, fields: tuple[str, ...], rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def verify_identity_registry(
    registry_path: Path, fasta_path: Path, report_dir: Path
) -> tuple[int, int, int]:
    registry = read_registry(registry_path)
    fasta = read_fasta(fasta_path)
    provenance = read_source_provenance(registry_path.parent / "sources_imp2_imp19.csv")
    provenance.extend(read_source_provenance(registry_path.parent / "sources_imp59.csv"))
    by_variant = {row["variant_name"]: row for row in registry}
    if set(by_variant) != EXPECTED_VARIANTS or len(fasta) != 9:
        raise ValueError("identity pack must contain nine registry rows and nine sequences")
    _validate_metadata_relationships(registry, fasta)
    mutants = read_imp14_engineered_mutants(registry_path.parent / "imp14_engineered_mutants.csv")
    primers = read_imp14_mutagenesis_primers(registry_path.parent / "imp14_mutagenesis_primers.csv")
    primer_qc = _validate_imp14_mutagenesis(mutants, primers, fasta["IMP-14"].sequence)
    measurement_qc = _validate_measurement_metadata(
        Path("data/curated/pilot/papers-001-003/measurements.csv")
    )
    qc_rows: list[dict[str, object]] = []
    for row in registry:
        variant = row["variant_name"]
        record = fasta.get(variant)
        if not row["preferred_protein_accession"] or row["enzyme_family"] != "IMP":
            raise ValueError(f"{variant}: required identity metadata is missing")
        pending = row["sequence_status"] == PENDING_SEQUENCE_STATUS
        if record is None:
            if not pending or row["full_length_length"] or row["full_length_sequence_sha256"]:
                raise ValueError(f"{variant}: missing sequence is not valid for this status")
            computed_length: int | str = ""
            computed_hash = ""
        else:
            if pending:
                raise ValueError(f"{variant}: pending status cannot have a sequence")
            if record.accession != row["preferred_protein_accession"]:
                raise ValueError(f"{variant}: FASTA and registry accessions disagree")
            computed_length = len(record.sequence)
            computed_hash = sequence_hash(record.sequence)
            if computed_length != 246:
                raise ValueError(f"{variant}: expected a 246-residue full precursor")
            if row["full_length_length"] != str(computed_length):
                raise ValueError(f"{variant}: recorded sequence length disagrees")
            if row["full_length_sequence_sha256"] != computed_hash:
                raise ValueError(f"{variant}: recorded sequence hash disagrees")
        qc_rows.append(
            {
                "variant_name": variant,
                "accession_presence": "present",
                "sequence_presence": "present" if record else "pending",
                "normalized_length": computed_length,
                "computed_hash": computed_hash,
                "metadata_consistency": "consistent",
                "validation_status": "valid",
                "quality_flags": row["quality_flags"],
            }
        )
    if set(fasta) != {
        row["variant_name"] for row in registry if row["sequence_status"] != PENDING_SEQUENCE_STATUS
    }:
        raise ValueError("FASTA variants do not match captured registry variants")

    difference_rows: list[dict[str, object]] = []
    for comparison in AUTHORISED_COMPARISONS:
        reference = fasta.get(comparison.reference_variant)
        comparison_record = fasta.get(comparison.variant)
        if reference is None or comparison_record is None:
            raise ValueError("authorised comparison sequence is missing")
        differences = direct_precursor_differences(reference.sequence, comparison_record.sequence)
        if differences != [comparison.expected_difference]:
            raise ValueError(
                f"{comparison.reference_variant}/{comparison.variant}: expected {comparison.expected_difference}, observed {differences}"
            )
        metadata = by_variant[comparison.variant]
        if (
            metadata["paper_reported_mutation"] != comparison.paper_reported_mutation
            or metadata["paper_numbering_scheme"] != "BBL"
            or metadata["independently_observed_precursor_difference"]
            != comparison.expected_difference
        ):
            raise ValueError("paper label and precursor difference metadata disagree")
        difference_rows.append(
            {
                "reference_variant": comparison.reference_variant,
                "comparison_variant": comparison.variant,
                "difference_count": 1,
                "observed_difference": comparison.expected_difference,
                "coordinate_system": "full_length_precursor_1_based",
                "paper_reported_mutation": metadata["paper_reported_mutation"],
                "paper_numbering_scheme": metadata["paper_numbering_scheme"],
                "verification_result": "verified",
            }
        )

    if report_dir.name == "batch-3c1c":
        mutagenesis_report_rows: list[dict[str, object]] = [
            {field: row[field] for field in ENGINEERED_MUTANT_FIELDS} for row in mutants
        ]
        _write_csv(
            report_dir / "imp14-mutagenesis-adjudication.csv",
            ENGINEERED_MUTANT_FIELDS,
            mutagenesis_report_rows,
        )
        _write_csv(
            report_dir / "imp14-primer-qc.csv",
            (
                "mutant_id",
                "wild_type_residue",
                "wild_type_window",
                "translated_mutant_window",
                "difference_count",
                "inferred_precursor_mutation",
                "validation_status",
            ),
            primer_qc,
        )
        _write_csv(
            report_dir / "measurement-metadata-qc.csv",
            (
                "observation_count_before",
                "observation_count_after",
                "allowed_metadata_changes",
                "numeric_value_relation_fitted_unit_compound_endpoint_changes",
                "non_target_row_changes",
                "validation_status",
            ),
            measurement_qc,
        )
        (report_dir / "readiness.md").write_text(
            "# Batch 3C1C IMP-14 mutagenesis readiness\n\n"
            "- All five IMP-14 engineered precursor mutations are adjudicated.\n"
            "- S47G, H134N, N137S, D181Y, and Y185N are the primer-supported full-length precursor changes.\n"
            "- Table-supported BBL labels are S65G, H174N, N178S, D227Y, and Y233N.\n"
            "- N178S versus narrative N177S remains documented as a source discrepancy.\n"
            "- Table 3 N233Y and supplement-label N185Y remain preserved as source discrepancies.\n"
            "- The Mutant 5 primer supports Y185N.\n"
            "- No universal BBL mapping was inferred.\n"
            "- 142 measurement observations remain and numerical IC50 evidence is unchanged.\n"
            "- IMP-14 is suitable for mutation-aware descriptive analysis with documented provenance caveats.\n"
            "- Structural or mechanistic causal claims remain unauthorised.\n",
            encoding="utf-8",
        )
        return len(registry), len(fasta), len(difference_rows)

    _write_csv(
        report_dir / "identity-qc.csv",
        (
            "variant_name",
            "accession_presence",
            "sequence_presence",
            "normalized_length",
            "computed_hash",
            "metadata_consistency",
            "validation_status",
            "quality_flags",
        ),
        qc_rows,
    )
    _write_csv(
        report_dir / "pairwise-differences.csv",
        (
            "reference_variant",
            "comparison_variant",
            "difference_count",
            "observed_difference",
            "coordinate_system",
            "paper_reported_mutation",
            "paper_numbering_scheme",
            "verification_result",
        ),
        difference_rows,
    )
    source_qc: list[dict[str, object]] = [
        {
            "variant_name": row["variant_name"],
            "claim_scope": row["claim_scope"],
            "source_kind": row["source_kind"],
            "locator_presence": "present",
            "doi_presence": "present" if row["source_doi"] else "not_applicable",
            "validation_status": "valid",
            "curator_note": row["curator_note"],
        }
        for row in provenance
    ]
    _write_csv(
        report_dir / "source-qc.csv",
        (
            "variant_name",
            "claim_scope",
            "source_kind",
            "locator_presence",
            "doi_presence",
            "validation_status",
            "curator_note",
        ),
        source_qc,
    )
    (report_dir / "readiness.md").write_text(
        "# Batch 3C1B2 identity readiness\n\n"
        "- Nine identity records exist.\n"
        "- Nine full-length precursor sequences are captured.\n"
        "- Five authorised precursor relationships are independently verified.\n"
        "- IMP-2 to IMP-19 is R21A in precursor coordinates; the paper relationship remains Arg38Ala in BBL coordinates.\n"
        "- IMP-4 to IMP-59 is N185Y in full-length precursor coordinates; the corresponding published relationship remains Asn233Tyr in BBL coordinates.\n"
        "- Precursor and BBL numbering remain separate.\n"
        "- IMP-59 is no longer sequence-pending.\n"
        "- IMP-14 numbering remains unresolved.\n"
        "- Source provenance remains incomplete for the other escape-core variants.\n"
        "- No general BBL mapping has been inferred.\n"
        "- Modelling and structural, hit, or lead claims remain unauthorised.\n",
        encoding="utf-8",
    )
    return len(registry), len(fasta), len(difference_rows)
