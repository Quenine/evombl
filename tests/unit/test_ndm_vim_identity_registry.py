import csv
import shutil
from pathlib import Path

import pytest

from evombl.proteins.identity_registry import direct_precursor_differences, read_fasta
from evombl.proteins.ndm_vim_identity_registry import (
    AUTHORISED_COMPARISONS,
    EXPECTED_HASHES,
    read_ndm_vim_provenance,
    read_ndm_vim_registry,
    verify_ndm_vim_identity_registry,
)

ROOT = Path("data/curated/identities/ndm_vim_escape_core")


def test_pack_has_expected_sequences_hashes_and_relationships(tmp_path: Path) -> None:
    registry = {
        row["variant_name"]: row for row in read_ndm_vim_registry(ROOT / "identity_registry.csv")
    }
    fasta = read_fasta(ROOT / "sequences.fasta")
    assert len(registry) == len(fasta) == 6
    assert {
        name: (
            len(record.sequence),
            __import__("hashlib").sha256(record.sequence.encode()).hexdigest(),
        )
        for name, record in fasta.items()
    } == EXPECTED_HASHES
    assert [
        (
            item.reference_variant,
            item.variant,
            direct_precursor_differences(
                fasta[item.reference_variant].sequence, fasta[item.variant].sequence
            ),
        )
        for item in AUTHORISED_COMPARISONS
    ] == [
        ("NDM-1", "NDM-9", ["E152K"]),
        ("NDM-1", "NDM-30", ["D223Y"]),
        ("VIM-1", "VIM-83", ["E146K"]),
    ]
    assert [
        (
            registry[x.variant]["paper_reported_mutation"],
            registry[x.variant]["paper_numbering_scheme"],
        )
        for x in AUTHORISED_COMPARISONS
    ] == [("E149K", "BBL"), ("D236Y", "BBL"), ("E149K", "BBL")]
    assert len(direct_precursor_differences(fasta["VIM-1"].sequence, fasta["VIM-2"].sequence)) == 25


def test_vim2_and_ndm30_provenance_semantics() -> None:
    rows = {
        row["variant_name"]: row for row in read_ndm_vim_registry(ROOT / "identity_registry.csv")
    }
    assert rows["VIM-2"]["reference_variant"] == ""
    assert rows["NDM-30"]["sequence_source_nucleotide_accession"] == "NG_071206.1"
    assert rows["NDM-30"]["original_discovery_nucleotide_accession"] == "MW306748.1"
    assert "not independently translated or compared" in rows["NDM-30"]["curator_note"]


def test_verifier_reports_are_deterministic(tmp_path: Path) -> None:
    first, second = tmp_path / "one", tmp_path / "two"
    assert verify_ndm_vim_identity_registry(
        ROOT / "identity_registry.csv", ROOT / "sequences.fasta", first
    ) == (6, 6, 3)
    assert verify_ndm_vim_identity_registry(
        ROOT / "identity_registry.csv", ROOT / "sequences.fasta", second
    ) == (6, 6, 3)
    for name in ("identity-qc.csv", "sequence-comparisons.csv", "source-qc.csv", "readiness.md"):
        assert (first / name).read_bytes() == (second / name).read_bytes()


def test_missing_sequence_wrong_residue_and_duplicate_provenance_fail(tmp_path: Path) -> None:
    registry, fasta, provenance = (
        tmp_path / "identity_registry.csv",
        tmp_path / "sequences.fasta",
        tmp_path / "source_provenance.csv",
    )
    for source, target in (
        (ROOT / "identity_registry.csv", registry),
        (ROOT / "sequences.fasta", fasta),
        (ROOT / "source_provenance.csv", provenance),
    ):
        shutil.copyfile(source, target)
    fasta.write_text(
        fasta.read_text(encoding="utf-8").replace(">AAF61483.1|VIM-2\n", ""), encoding="utf-8"
    )
    with pytest.raises(ValueError, match="six FASTA"):
        verify_ndm_vim_identity_registry(registry, fasta, tmp_path / "reports")
    with provenance.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
        fields = tuple(rows[0])
    rows.append(rows[0].copy())
    with provenance.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    with pytest.raises(ValueError, match="duplicate source provenance semantic key"):
        read_ndm_vim_provenance(provenance)
