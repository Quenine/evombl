import csv
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
