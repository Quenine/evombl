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
    verify_identity_registry,
)
from evombl.proteins.sequences import sequence_hash

ROOT = Path("data/curated/identities/imp_escape_core")
REGISTRY = ROOT / "identity_registry.csv"
FASTA = ROOT / "sequences.fasta"


def test_registry_and_fasta_counts_accessions_lengths_and_hashes() -> None:
    registry = read_registry(REGISTRY)
    fasta = read_fasta(FASTA)
    assert len(registry) == 8
    assert len(fasta) == 7
    by_variant = {row["variant_name"]: row for row in registry}
    for variant, record in fasta.items():
        assert record.accession == by_variant[variant]["preferred_protein_accession"]
        assert len(record.sequence) == 246
        assert sequence_hash(record.sequence) == by_variant[variant]["full_length_sequence_sha256"]
        assert len(sequence_hash(record.sequence)) == 64


def test_imp59_is_the_only_explicitly_pending_sequence() -> None:
    registry = {row["variant_name"]: row for row in read_registry(REGISTRY)}
    fasta = read_fasta(FASTA)
    assert "IMP-59" not in fasta
    assert registry["IMP-59"]["sequence_status"] == ("accession_verified_sequence_payload_pending")
    assert registry["IMP-59"]["full_length_length"] == ""
    assert registry["IMP-59"]["full_length_sequence_sha256"] == ""
    assert all(
        row["sequence_status"] == "sequence_captured"
        for variant, row in registry.items()
        if variant != "IMP-59"
    )


def test_only_authorised_precursor_differences_are_reproduced() -> None:
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
    }


def test_paper_labels_remain_separate_from_precursor_coordinates(tmp_path: Path) -> None:
    verify_identity_registry(REGISTRY, FASTA, tmp_path)
    rows = list(csv.DictReader((tmp_path / "pairwise-differences.csv").open(encoding="utf-8")))
    assert len(rows) == 3
    assert {row["comparison_variant"] for row in rows} == {"IMP-6", "IMP-10", "IMP-26"}
    assert {row["paper_reported_mutation"] for row in rows} == {"Ser262Gly", "Val67Phe"}
    assert {row["observed_difference"] for row in rows} == {"S214G", "V49F"}
    assert all(row["paper_numbering_scheme"] == "BBL" for row in rows)
    assert not {"IMP-14", "IMP-19", "IMP-59"} & {row["comparison_variant"] for row in rows}


def _copy_pack(tmp_path: Path) -> tuple[Path, Path]:
    registry = tmp_path / "identity_registry.csv"
    fasta = tmp_path / "sequences.fasta"
    shutil.copyfile(REGISTRY, registry)
    shutil.copyfile(FASTA, fasta)
    return registry, fasta


def test_missing_captured_sequence_fails(tmp_path: Path) -> None:
    registry, fasta = _copy_pack(tmp_path)
    text = fasta.read_text(encoding="utf-8")
    start = text.index(">AAT49068.1|IMP-14")
    end = text.index(">", start + 1)
    fasta.write_text(text[:start] + text[end:], encoding="utf-8")
    with pytest.raises(ValueError, match="eight registry rows and seven sequences"):
        verify_identity_registry(registry, fasta, tmp_path / "reports")


def test_changed_comparison_residue_fails_verification(tmp_path: Path) -> None:
    registry_path, fasta_path = _copy_pack(tmp_path)
    fasta = read_fasta(fasta_path)
    imp6 = fasta["IMP-6"].sequence
    changed = imp6[:213] + "S" + imp6[214:]
    fasta_path.write_text(
        fasta_path.read_text(encoding="utf-8").replace(imp6, changed),
        encoding="utf-8",
    )
    with registry_path.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        fields = reader.fieldnames
        rows = list(reader)
    for row in rows:
        if row["variant_name"] == "IMP-6":
            row["full_length_sequence_sha256"] = sequence_hash(changed)
    with registry_path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    with pytest.raises(ValueError, match="expected S214G"):
        verify_identity_registry(registry_path, fasta_path, tmp_path / "reports")


@pytest.mark.parametrize("duplicate_field", ["variant_name", "preferred_protein_accession"])
def test_duplicate_registry_names_or_accessions_fail(tmp_path: Path, duplicate_field: str) -> None:
    registry, _ = _copy_pack(tmp_path)
    with registry.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        fields = reader.fieldnames
        rows = list(reader)
    rows[1][duplicate_field] = rows[0][duplicate_field]
    with registry.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    with pytest.raises(ValueError, match="duplicate registry"):
        read_registry(registry)


def test_malformed_or_ambiguous_sequence_fails(tmp_path: Path) -> None:
    _, fasta = _copy_pack(tmp_path)
    fasta.write_text(
        fasta.read_text(encoding="utf-8").replace(
            "MSKLSVFFIFLFCSIATAAE", "MSKLSVFFIFLFCSIATAAX", 1
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="unsupported symbols"):
        read_fasta(fasta)


def test_reports_are_deterministic_and_measurements_are_unchanged(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    assert verify_identity_registry(REGISTRY, FASTA, first) == (8, 7, 3)
    assert verify_identity_registry(REGISTRY, FASTA, second) == (8, 7, 3)
    for name in ("identity-qc.csv", "pairwise-differences.csv", "readiness.md"):
        assert (first / name).read_bytes() == (second / name).read_bytes()
    measurements = Path("data/curated/pilot/papers-001-003")
    assert hashlib.sha256((measurements / "measurements.csv").read_bytes()).hexdigest() == (
        "e44ff1f49d95ad32160b721345445b6f271ebf46327c022b74cc0a5a05ba6b1c"
    )
    assert (
        hashlib.sha256((measurements / "measurements.parquet").read_bytes()).hexdigest()
        == "df72f529f885d8d4df382f8ffeac63e26c79e33dbd10e0315cbe59f2d2f42a86"
    )
