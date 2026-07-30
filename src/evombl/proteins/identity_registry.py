import csv
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
PENDING_SEQUENCE_STATUS = "accession_verified_sequence_payload_pending"
EXPECTED_VARIANTS = {"IMP-1", "IMP-4", "IMP-6", "IMP-10", "IMP-14", "IMP-19", "IMP-26", "IMP-59"}


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
    by_variant = {row["variant_name"]: row for row in registry}
    if set(by_variant) != EXPECTED_VARIANTS or len(fasta) != 7:
        raise ValueError("identity pack must contain eight registry rows and seven sequences")
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
                "accession_presence": "present"
                if row["preferred_protein_accession"]
                else "missing",
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
                f"{comparison.reference_variant}/{comparison.variant}: expected "
                f"{comparison.expected_difference}, observed {differences}"
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
    (report_dir / "readiness.md").write_text(
        "# Batch 3C1A identity readiness\n\n"
        "- Eight identity records exist.\n"
        "- Seven authoritative full-length precursor sequence payloads were captured.\n"
        "- IMP-59 remains accession-only; its sequence payload is pending.\n"
        "- Three authorised precursor relationships were independently reproduced.\n"
        "- Full-length precursor coordinates and paper BBL coordinates remain separate.\n"
        "- IMP-14 numbering remains unresolved.\n"
        "- IMP-19 versus IMP-2 remains unverified.\n"
        "- IMP-59 versus IMP-4 remains paper-supported only.\n"
        "- Sequence identity verification remains incomplete.\n"
        "- Modelling, structural claims, hit claims, and lead claims remain unauthorised.\n",
        encoding="utf-8",
    )
    return len(registry), len(fasta), len(difference_rows)
