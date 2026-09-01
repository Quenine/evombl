"""Bounded validation for the NDM/VIM escape-critical identity pack.

Paper BBL labels are deliberately stored, never converted.  Each curated
precursor relationship is independently checked from the supplied sequences.
"""

import csv
from dataclasses import dataclass
from pathlib import Path

from evombl.proteins.identity_registry import FastaRecord, direct_precursor_differences, read_fasta
from evombl.proteins.sequences import sequence_hash

REGISTRY_FIELDS = (
    "variant_name",
    "enzyme_family",
    "preferred_protein_accession",
    "secondary_protein_accession",
    "sequence_source_nucleotide_accession",
    "original_discovery_nucleotide_accession",
    "sequence_status",
    "full_length_length",
    "full_length_sequence_sha256",
    "reference_variant",
    "paper_reported_mutation",
    "paper_numbering_scheme",
    "precursor_mutation",
    "precursor_coordinate_system",
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
EXPECTED_HASHES = {
    "NDM-1": (270, "e789dada59f2ab0f7f8922804e2c42c298767cdee2e7523abe368dfb9b0b3a69"),
    "NDM-9": (270, "54c53eddc565c27f4b9feeb24d09ef91024026bc35c536a9f7a709cbd2a7a0f1"),
    "NDM-30": (270, "4b3c956a0c75e0f9314e260593e3f2308baa47bf80162b285081f55ec5ef3ceb"),
    "VIM-1": (266, "daf734d2eac5704af1d0a758f7a698256cff5fd18deb042dce053c1f04ad7bac"),
    "VIM-83": (266, "26ae1bfcd8cc5260f6bdc9881bcd679363f1460174d0ea40ae7050f3f3bab9c1"),
    "VIM-2": (266, "f732ee050e8475e296aa3926d805d3d4007cbb748a3e355238455dd45ce0fbf3"),
}


@dataclass(frozen=True)
class AuthorisedComparison:
    reference_variant: str
    variant: str
    paper_mutation: str
    precursor_mutation: str


AUTHORISED_COMPARISONS = (
    AuthorisedComparison("NDM-1", "NDM-9", "E149K", "E152K"),
    AuthorisedComparison("NDM-1", "NDM-30", "D236Y", "D223Y"),
    AuthorisedComparison("VIM-1", "VIM-83", "E149K", "E146K"),
)


def _read_csv(path: Path, fields: tuple[str, ...]) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        if tuple(reader.fieldnames or ()) != fields:
            raise ValueError(f"{path.name}: columns do not match the required schema")
        rows = list(reader)
    if any(None in row for row in rows):
        raise ValueError(f"{path.name}: row has unexpected fields")
    return rows


def read_ndm_vim_registry(path: Path) -> list[dict[str, str]]:
    rows = _read_csv(path, REGISTRY_FIELDS)
    names = [row["variant_name"] for row in rows]
    if set(names) != set(EXPECTED_HASHES) or len(rows) != 6:
        raise ValueError("identity pack must contain exactly six registry variants")
    if len(names) != len(set(names)):
        raise ValueError("duplicate registry variant names")
    return rows


def read_ndm_vim_provenance(path: Path) -> list[dict[str, str]]:
    rows = _read_csv(path, PROVENANCE_FIELDS)
    seen: set[tuple[str, str, str, str]] = set()
    for row in rows:
        for field in ("variant_name", "claim_scope", "source_kind", "source_locator", "accession"):
            if not row[field]:
                raise ValueError(f"source provenance record missing {field}")
        key = (row["variant_name"], row["claim_scope"], row["source_kind"], row["accession"])
        if key in seen:
            raise ValueError("duplicate source provenance semantic key")
        seen.add(key)
    return rows


def _write_csv(path: Path, fields: tuple[str, ...], rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def verify_ndm_vim_identity_registry(
    registry_path: Path, fasta_path: Path, report_dir: Path
) -> tuple[int, int, int]:
    registry = read_ndm_vim_registry(registry_path)
    fasta: dict[str, FastaRecord] = read_fasta(fasta_path)
    provenance = read_ndm_vim_provenance(registry_path.parent / "source_provenance.csv")
    by_name = {row["variant_name"]: row for row in registry}
    if set(fasta) != set(EXPECTED_HASHES) or len(fasta) != 6:
        raise ValueError(
            "identity pack must contain exactly six FASTA records matching the registry"
        )
    qc: list[dict[str, object]] = []
    for name, (expected_length, expected_hash) in EXPECTED_HASHES.items():
        row, record = by_name[name], fasta[name]
        computed_hash = sequence_hash(record.sequence)
        if record.accession != row["preferred_protein_accession"]:
            raise ValueError(f"{name}: FASTA and registry accessions disagree")
        if len(record.sequence) != expected_length or computed_hash != expected_hash:
            raise ValueError(f"{name}: curated sequence length or hash disagrees")
        if (
            row["full_length_length"] != str(expected_length)
            or row["full_length_sequence_sha256"] != expected_hash
        ):
            raise ValueError(f"{name}: registry length or hash disagrees")
        qc.append(
            {
                "variant_name": name,
                "preferred_protein_accession": record.accession,
                "normalized_length": expected_length,
                "computed_hash": computed_hash,
                "validation_status": "valid",
                "quality_flags": row["quality_flags"],
            }
        )
    rows: list[dict[str, object]] = []
    for item in AUTHORISED_COMPARISONS:
        metadata = by_name[item.variant]
        observed = direct_precursor_differences(
            fasta[item.reference_variant].sequence, fasta[item.variant].sequence
        )
        if observed != [item.precursor_mutation]:
            raise ValueError(
                f"{item.reference_variant}/{item.variant}: expected {item.precursor_mutation}, observed {observed}"
            )
        if (
            metadata["reference_variant"],
            metadata["paper_reported_mutation"],
            metadata["paper_numbering_scheme"],
            metadata["precursor_mutation"],
            metadata["precursor_coordinate_system"],
        ) != (
            item.reference_variant,
            item.paper_mutation,
            "BBL",
            item.precursor_mutation,
            "full_length_precursor_1_based",
        ):
            raise ValueError(f"{item.variant}: paper and precursor numbering metadata disagree")
        rows.append(
            {
                "reference_variant": item.reference_variant,
                "comparison_variant": item.variant,
                "difference_count": 1,
                "observed_precursor_difference": item.precursor_mutation,
                "coordinate_system": "full_length_precursor_1_based",
                "paper_reported_mutation": item.paper_mutation,
                "paper_numbering_scheme": "BBL",
                "verification_result": "verified",
            }
        )
    vim2 = by_name["VIM-2"]
    if vim2["reference_variant"] or "not_a_simple_vim1_derivative" not in vim2["quality_flags"]:
        raise ValueError("VIM-2 must not have a simple VIM-1 relationship")
    vim_differences = direct_precursor_differences(fasta["VIM-1"].sequence, fasta["VIM-2"].sequence)
    if len(vim_differences) != 25:
        raise ValueError("VIM-1/VIM-2 must differ at exactly 25 precursor residues")
    _write_csv(
        report_dir / "identity-qc.csv",
        (
            "variant_name",
            "preferred_protein_accession",
            "normalized_length",
            "computed_hash",
            "validation_status",
            "quality_flags",
        ),
        qc,
    )
    _write_csv(
        report_dir / "sequence-comparisons.csv",
        (
            "reference_variant",
            "comparison_variant",
            "difference_count",
            "observed_precursor_difference",
            "coordinate_system",
            "paper_reported_mutation",
            "paper_numbering_scheme",
            "verification_result",
        ),
        rows,
    )
    _write_csv(
        report_dir / "source-qc.csv",
        (
            "variant_name",
            "claim_scope",
            "source_kind",
            "source_locator",
            "accession",
            "validation_status",
            "curator_note",
        ),
        [
            {
                "variant_name": x["variant_name"],
                "claim_scope": x["claim_scope"],
                "source_kind": x["source_kind"],
                "source_locator": x["source_locator"],
                "accession": x["accession"],
                "validation_status": "valid",
                "curator_note": x["curator_note"],
            }
            for x in provenance
        ],
    )
    (report_dir / "readiness.md").write_text(
        """# Batch 3E1 NDM/VIM identity readiness

- Six full-length precursor identities are captured; three simple natural relationships are sequence-verified.
- NDM-9 paper E149K corresponds to precursor E152K; NDM-30 paper D236Y corresponds to precursor D223Y; VIM-83 paper E149K corresponds to precursor E146K.
- These mappings are position-specific. No universal BBL-to-precursor transform was inferred.
- VIM-2 differs from VIM-1 at 25 precursor residues and is retained only as a comparator.
- NDM-30 MW306748.1 is retained as discovery provenance and was not independently translated or compared in this batch.
- No mechanistic interpretation follows merely from sequence difference. Structural analysis, predictive modelling, docking, hits, and lead claims remain unauthorised.
""",
        encoding="utf-8",
    )
    return len(registry), len(fasta), len(rows)
