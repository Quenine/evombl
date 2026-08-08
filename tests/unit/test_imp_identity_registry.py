import csv
import hashlib
import shutil
from pathlib import Path

import pytest

from evombl.proteins.identity_registry import (
    AUTHORISED_COMPARISONS,
    direct_precursor_differences,
    read_fasta,
    read_registry,
    read_source_provenance,
    verify_identity_registry,
)
from evombl.proteins.sequences import sequence_hash

ROOT = Path("data/curated/identities/imp_escape_core")
REGISTRY = ROOT / "identity_registry.csv"
FASTA = ROOT / "sequences.fasta"
SOURCES = ROOT / "sources_imp2_imp19.csv"


def test_registry_fasta_counts_and_imp2_payload() -> None:
    registry = {row["variant_name"]: row for row in read_registry(REGISTRY)}
    fasta = read_fasta(FASTA)
    assert len(registry) == 9
    assert len(fasta) == 8
    imp2 = fasta["IMP-2"]
    assert (imp2.accession, len(imp2.sequence), sequence_hash(imp2.sequence)) == (
        "CAB94707.1",
        246,
        "84008f00361f521de08c43e271588240f30be987960a0db4f8a1db59a60bad26",
    )
    assert registry["IMP-2"]["full_length_sequence_sha256"] == sequence_hash(imp2.sequence)
    for variant, record in fasta.items():
        assert record.accession == registry[variant]["preferred_protein_accession"]
        assert len(record.sequence) == 246


def test_imp59_remains_the_only_pending_sequence() -> None:
    registry = {row["variant_name"]: row for row in read_registry(REGISTRY)}
    assert "IMP-59" not in read_fasta(FASTA)
    assert registry["IMP-59"]["sequence_status"] == "accession_verified_sequence_payload_pending"
    assert registry["IMP-59"]["full_length_length"] == ""
    assert registry["IMP-59"]["full_length_sequence_sha256"] == ""


def test_corrected_imp14_and_imp19_metadata_passes(tmp_path: Path) -> None:
    registry = {row["variant_name"]: row for row in read_registry(REGISTRY)}
    assert registry["IMP-14"]["quality_flags"] == "imp14_numbering_discrepancy_unresolved"
    assert "imp2_reference_sequence_not_in_pack" not in registry["IMP-14"]["quality_flags"]
    assert registry["IMP-19"]["curator_note"] == (
        "The IMP-2 relationship was independently reproduced as R21A in full-length "
        "precursor coordinates; the paper-reported Arg38Ala BBL label is retained separately."
    )
    assert verify_identity_registry(REGISTRY, FASTA, tmp_path / "reports") == (9, 8, 4)


def test_captured_reference_missing_flag_fails(tmp_path: Path) -> None:
    registry, fasta, _ = _copy_pack(tmp_path)
    with registry.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        fields = reader.fieldnames
        rows = list(reader)
    for row in rows:
        if row["variant_name"] == "IMP-14":
            row["quality_flags"] = "imp2_reference_sequence_not_in_pack"
    with registry.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    with pytest.raises(ValueError, match="reference sequence missing flag"):
        verify_identity_registry(registry, fasta, tmp_path / "reports")


def test_reference_missing_flag_is_allowed_when_reference_is_pending(tmp_path: Path) -> None:
    registry, fasta, _ = _copy_pack(tmp_path)
    with registry.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        fields = reader.fieldnames
        rows = list(reader)
    for row in rows:
        if row["variant_name"] == "IMP-59":
            row["reference_variant"] = "IMP-59"
            row["quality_flags"] = "reference_sequence_not_in_pack"
    with registry.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    assert verify_identity_registry(registry, fasta, tmp_path / "reports") == (9, 8, 4)


def test_verified_precursor_note_contradiction_fails(tmp_path: Path) -> None:
    registry, fasta, _ = _copy_pack(tmp_path)
    with registry.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        fields = reader.fieldnames
        rows = list(reader)
    for row in rows:
        if row["variant_name"] == "IMP-19":
            row["curator_note"] = "The relationship cannot be independently checked."
    with registry.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    with pytest.raises(ValueError, match="curator note contradicts"):
        verify_identity_registry(registry, fasta, tmp_path / "reports")


def test_protected_sequences_and_sources_are_unchanged() -> None:
    assert hashlib.sha256(FASTA.read_bytes()).hexdigest() == (
        "2c5308fb21b4318292cf177559f8cdcebbe63c14b872b743bb4474fbce007b30"
    )
    assert hashlib.sha256(SOURCES.read_bytes()).hexdigest() == (
        "8f698692c0d3ebf91c65793ce086816c45d63516f3d897b7cdc05741b3aacbfa"
    )


def test_all_four_authorised_differences_and_paper_labels_are_separate() -> None:
    fasta = read_fasta(FASTA)
    observed = {
        (item.reference_variant, item.variant): direct_precursor_differences(
            fasta[item.reference_variant].sequence, fasta[item.variant].sequence
        )
        for item in AUTHORISED_COMPARISONS
    }
    assert observed == {
        ("IMP-1", "IMP-6"): ["S214G"],
        ("IMP-1", "IMP-10"): ["V49F"],
        ("IMP-4", "IMP-26"): ["V49F"],
        ("IMP-2", "IMP-19"): ["R21A"],
    }
    imp19 = {row["variant_name"]: row for row in read_registry(REGISTRY)}["IMP-19"]
    assert (
        imp19["paper_reported_mutation"],
        imp19["paper_numbering_scheme"],
        imp19["independently_observed_precursor_difference"],
    ) == ("Arg38Ala", "BBL", "R21A")


def test_reports_include_only_authorised_comparisons(tmp_path: Path) -> None:
    assert verify_identity_registry(REGISTRY, FASTA, tmp_path) == (9, 8, 4)
    rows = list(csv.DictReader((tmp_path / "pairwise-differences.csv").open(encoding="utf-8")))
    assert len(rows) == 4
    assert {
        (row["reference_variant"], row["comparison_variant"], row["observed_difference"])
        for row in rows
    } == {
        ("IMP-1", "IMP-6", "S214G"),
        ("IMP-1", "IMP-10", "V49F"),
        ("IMP-4", "IMP-26", "V49F"),
        ("IMP-2", "IMP-19", "R21A"),
    }
    assert not {"IMP-14", "IMP-59"} & {row["comparison_variant"] for row in rows}
    assert "Arg38Ala" in {row["paper_reported_mutation"] for row in rows}


def test_partial_provenance_pack_validates_and_is_reported(tmp_path: Path) -> None:
    sources = read_source_provenance(SOURCES)
    assert len(sources) == 5
    assert {row["variant_name"] for row in sources} == {"IMP-2", "IMP-19"}
    verify_identity_registry(REGISTRY, FASTA, tmp_path)
    qc = list(csv.DictReader((tmp_path / "source-qc.csv").open(encoding="utf-8")))
    assert len(qc) == 5
    assert {row["validation_status"] for row in qc} == {"valid"}


def _copy_pack(tmp_path: Path) -> tuple[Path, Path, Path]:
    registry = tmp_path / "identity_registry.csv"
    fasta = tmp_path / "sequences.fasta"
    sources = tmp_path / "sources_imp2_imp19.csv"
    shutil.copyfile(REGISTRY, registry)
    shutil.copyfile(FASTA, fasta)
    shutil.copyfile(SOURCES, sources)
    return registry, fasta, sources


@pytest.mark.parametrize(
    ("row_index", "field", "match"),
    [
        (0, "source_doi", "primary source provenance requires a DOI"),
        (1, "source_locator", "source provenance record missing source_locator"),
    ],
)
def test_invalid_provenance_fails(tmp_path: Path, row_index: int, field: str, match: str) -> None:
    _, _, sources = _copy_pack(tmp_path)
    with sources.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        fields = reader.fieldnames
        rows = list(reader)
    rows[row_index][field] = ""
    with sources.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    with pytest.raises(ValueError, match=match):
        read_source_provenance(sources)


def test_altered_imp2_sequence_causes_verification_failure(tmp_path: Path) -> None:
    registry, fasta_path, _ = _copy_pack(tmp_path)
    fasta = read_fasta(fasta_path)
    original = fasta["IMP-2"].sequence
    altered = "A" + original[1:]
    fasta_path.write_text(
        fasta_path.read_text(encoding="utf-8").replace(original, altered), encoding="utf-8"
    )
    with registry.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        fields = reader.fieldnames
        rows = list(reader)
    for row in rows:
        if row["variant_name"] == "IMP-2":
            row["full_length_sequence_sha256"] = sequence_hash(altered)
    with registry.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    with pytest.raises(ValueError, match="expected R21A"):
        verify_identity_registry(registry, fasta_path, tmp_path / "reports")


def test_reports_are_deterministic_and_measurements_are_unchanged(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    assert verify_identity_registry(REGISTRY, FASTA, first) == (9, 8, 4)
    assert verify_identity_registry(REGISTRY, FASTA, second) == (9, 8, 4)
    for name in ("identity-qc.csv", "pairwise-differences.csv", "source-qc.csv", "readiness.md"):
        assert (first / name).read_bytes() == (second / name).read_bytes()
    measurements = Path("data/curated/pilot/papers-001-003")
    assert (
        hashlib.sha256((measurements / "measurements.csv").read_bytes()).hexdigest()
        == "e44ff1f49d95ad32160b721345445b6f271ebf46327c022b74cc0a5a05ba6b1c"
    )
    assert (
        hashlib.sha256((measurements / "measurements.parquet").read_bytes()).hexdigest()
        == "df72f529f885d8d4df382f8ffeac63e26c79e33dbd10e0315cbe59f2d2f42a86"
    )


@pytest.mark.parametrize("field", ["variant_name", "preferred_protein_accession"])
def test_duplicate_registry_variant_or_accession_fails(tmp_path: Path, field: str) -> None:
    registry, _, _ = _copy_pack(tmp_path)
    with registry.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        fields = reader.fieldnames
        rows = list(reader)
    rows[1][field] = rows[0][field]
    with registry.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    with pytest.raises(ValueError, match="duplicate registry"):
        read_registry(registry)


def test_malformed_amino_acid_sequence_fails(tmp_path: Path) -> None:
    _, fasta, _ = _copy_pack(tmp_path)
    fasta.write_text(
        fasta.read_text(encoding="utf-8").replace(
            "MSKLSVFFIFLFCSIATAAE", "MSKLSVFFIFLFCSIATAAX", 1
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="unsupported symbols"):
        read_fasta(fasta)
