import csv
import shutil
from pathlib import Path

import pytest

from evombl.proteins.identity_registry import (
    _validate_imp14_mutagenesis,
    read_fasta,
    read_imp14_engineered_mutants,
    read_imp14_mutagenesis_primers,
    verify_identity_registry,
)

ROOT = Path("data/curated/identities/imp_escape_core")
REGISTRY = ROOT / "identity_registry.csv"
FASTA = ROOT / "sequences.fasta"
MUTANTS = ROOT / "imp14_engineered_mutants.csv"
PRIMERS = ROOT / "imp14_mutagenesis_primers.csv"
MEASUREMENTS = Path("data/curated/pilot/papers-001-003/measurements.csv")


def test_imp14_primer_adjudications_are_complete_and_sequence_derived() -> None:
    mutants = read_imp14_engineered_mutants(MUTANTS)
    primers = read_imp14_mutagenesis_primers(PRIMERS)
    qc = _validate_imp14_mutagenesis(mutants, primers, read_fasta(FASTA)["IMP-14"].sequence)
    assert {row["precursor_mutation"] for row in mutants} == {
        "S47G",
        "H134N",
        "N137S",
        "D181Y",
        "Y185N",
    }
    assert {(row["wild_type_residue"], row["inferred_precursor_mutation"]) for row in qc} == {
        ("S", "S47G"),
        ("H", "H134N"),
        ("N", "N137S"),
        ("D", "D181Y"),
        ("Y", "Y185N"),
    }


def test_imp14_source_conflicts_are_preserved() -> None:
    by_id = {row["mutant_id"]: row for row in read_imp14_engineered_mutants(MUTANTS)}
    assert (
        by_id["IMP14-MUT-03"]["table2_bbl_label"],
        by_id["IMP14-MUT-03"]["table3_bbl_label"],
        by_id["IMP14-MUT-03"]["narrative_label"],
    ) == ("N178S", "N178S", "Asn177Ser")
    assert (
        by_id["IMP14-MUT-05"]["table2_bbl_label"],
        by_id["IMP14-MUT-05"]["table3_bbl_label"],
        by_id["IMP14-MUT-05"]["supplement_label"],
        by_id["IMP14-MUT-05"]["precursor_mutation"],
    ) == ("Y233N", "N233Y", "IMP-14 N185Y", "Y185N")


def test_mut05_wrong_direction_fails_sequence_validation(tmp_path: Path) -> None:
    primers = tmp_path / "imp14_mutagenesis_primers.csv"
    shutil.copyfile(PRIMERS, primers)
    text = primers.read_text(encoding="utf-8").replace(
        ",Y185N,10.1128/aac.00297-25.SuF3,", ",N185Y,10.1128/aac.00297-25.SuF3,"
    )
    primers.write_text(text, encoding="utf-8")
    with pytest.raises(ValueError, match="primer-derived precursor mutation disagrees"):
        _validate_imp14_mutagenesis(
            read_imp14_engineered_mutants(MUTANTS),
            read_imp14_mutagenesis_primers(primers),
            read_fasta(FASTA)["IMP-14"].sequence,
        )


def test_imp14_measurement_metadata_and_reports_are_valid(tmp_path: Path) -> None:
    report_dir = tmp_path / "batch-3c1c"
    assert verify_identity_registry(REGISTRY, FASTA, report_dir) == (9, 9, 5)
    second_dir = tmp_path / "second" / "batch-3c1c"
    assert verify_identity_registry(REGISTRY, FASTA, second_dir) == (9, 9, 5)
    assert {path.name for path in report_dir.iterdir()} == {
        "imp14-mutagenesis-adjudication.csv",
        "imp14-primer-qc.csv",
        "measurement-metadata-qc.csv",
        "readiness.md",
    }
    rows = {
        row["observation_id"]: row for row in csv.DictReader(MEASUREMENTS.open(encoding="utf-8"))
    }
    assert rows["EVO-OBS-P3-024"]["source_row_label"] == "IMP-14 N233Y"
    assert rows["EVO-OBS-P3-024"]["author_reported_mutation"] == "N233Y"
    assert rows["EVO-OBS-P3-024"]["quality_flags"] == "source_mutation_label_conflict_adjudicated"
    assert rows["EVO-OBS-P3-020"]["quality_flags"] == "mutation_identity_adjudicated_from_table_s1"
    for name in (
        "imp14-mutagenesis-adjudication.csv",
        "imp14-primer-qc.csv",
        "measurement-metadata-qc.csv",
        "readiness.md",
    ):
        assert (report_dir / name).read_bytes() == (second_dir / name).read_bytes()
