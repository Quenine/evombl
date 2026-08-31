from collections import Counter
from pathlib import Path

from evombl.scientific_extraction import build_outputs, load_observations

SOURCE = Path("data/curated/pilot/papers-001-003/measurements.csv")
P2_DOI = "10.1128/aac.01570-23"
P3_DOI = "10.1128/aac.00297-25"
P3_VALUES = {
    "NDM-1": ("4.3", "3.0"),
    "NDM-1 S262G": (">200", ">250"),
    "IMP-1": ("2.7", ">250"),
    "IMP-6": ("180", ">250"),
    "IMP-10": ("73", ">250"),
    "IMP-19": ("7.5", ">250"),
    "IMP-14": (">250", ">250"),
    "IMP-14 S65G": ("140", ">250"),
    "IMP-14 H174N": ("182", ">250"),
    "IMP-14 N178S": ("180", ">250"),
    "IMP-14 D227Y": ("250", "204"),
    "IMP-14 N233Y": ("210", ">250"),
    "IMP-4": ("14.7", ">250"),
    "IMP-26": ("77", ">250"),
    "IMP-59": ("10.3", "7.0"),
}


def _panel(doi: str, table: str) -> list[object]:
    return [
        row
        for row in load_observations(SOURCE)
        if row.source_doi == doi and row.source_table == table
    ]


def test_final_count_and_complete_table4_values() -> None:
    assert len(load_observations(SOURCE)) == 142
    rows = _panel(P2_DOI, "Table 4")
    assert len(rows) == 8
    actual = {
        (row.enzyme_variant, row.compound): (
            row.relation,
            row.value,
            row.unit,
            row.reference_variant,
            row.author_reported_mutation,
            row.numbering_scheme,
        )
        for row in rows
    }
    assert actual == {
        ("NDM-1", "xeruborbactam"): ("=", "0.08", "uM", None, None, None),
        ("NDM-1", "taniborbactam"): ("=", "0.016", "uM", None, None, None),
        ("VIM-2", "xeruborbactam"): ("=", "0.002", "uM", None, None, None),
        ("VIM-2", "taniborbactam"): ("=", "0.01", "uM", None, None, None),
        ("IMP-1", "xeruborbactam"): ("=", "0.3", "uM", None, None, None),
        ("IMP-1", "taniborbactam"): (">", "20", "uM", None, None, None),
        ("IMP-10", "xeruborbactam"): ("=", "11.3", "uM", "IMP-1", "Val67Phe", "BBL"),
        ("IMP-10", "taniborbactam"): (">", "20", "uM", "IMP-1", "Val67Phe", "BBL"),
    }
    assert Counter(row.relation for row in rows) == {"=": 6, ">": 2}


def test_paper3_panel_is_paired_and_preserves_every_value() -> None:
    rows = _panel(P3_DOI, "Table 3")
    assert len(rows) == 30
    assert Counter(row.enzyme_variant for row in rows) == Counter(
        {variant: 2 for variant in P3_VALUES}
    )
    actual = {
        (row.enzyme_variant, row.compound): (f">{row.value}" if row.relation == ">" else row.value)
        for row in rows
    }
    expected = {
        (variant, compound): value
        for variant, pair in P3_VALUES.items()
        for compound, value in zip(("xeruborbactam", "taniborbactam"), pair, strict=True)
    }
    assert actual == expected
    assert Counter(row.relation for row in rows) == {"=": 16, ">": 14}


def test_imp14_censoring_fitted_value_and_mutation_warnings() -> None:
    rows = _panel(P3_DOI, "Table 3")
    baseline = next(
        row for row in rows if row.enzyme_variant == "IMP-14" and row.compound == "xeruborbactam"
    )
    assert (baseline.relation, baseline.value, baseline.fitted_value) == (">", "250", "680")
    mutants = [row for row in rows if row.enzyme_variant.startswith("IMP-14 ")]
    assert len(mutants) == 10
    assert {
        row.quality_flags
        for row in mutants
        if row.observation_id not in {"EVO-OBS-P3-024", "EVO-OBS-P3-025"}
    } == {"mutation_identity_adjudicated_from_table_s1"}
    assert {
        row.quality_flags
        for row in mutants
        if row.observation_id in {"EVO-OBS-P3-024", "EVO-OBS-P3-025"}
    } == {"source_mutation_label_conflict_adjudicated"}
    assert {
        row.author_reported_mutation
        for row in mutants
        if row.observation_id in {"EVO-OBS-P3-024", "EVO-OBS-P3-025"}
    } == {"N233Y"}


def test_prior_study_rows_are_explicitly_non_independent() -> None:
    rows = _panel(P3_DOI, "Table 3")
    republished = [
        row for row in rows if row.directness == "prior_study_value_republished_in_table"
    ]
    assert len(republished) == 10
    assert {row.enzyme_variant for row in republished} == {
        "NDM-1",
        "IMP-1",
        "IMP-10",
        "IMP-19",
        "IMP-4",
    }
    assert all(row.quality_flags == "source_table_marks_prior_study" for row in republished)
    assert all(
        "must not be treated as an independent experiment" in row.curator_note
        for row in republished
    )


def test_six_engineered_variants_and_no_duplicate_panel_records() -> None:
    rows = _panel(P3_DOI, "Table 3")
    engineered = {row.enzyme_variant for row in rows if row.variant_origin == "engineered"}
    assert engineered == {
        "NDM-1 S262G",
        "IMP-14 S65G",
        "IMP-14 H174N",
        "IMP-14 N178S",
        "IMP-14 D227Y",
        "IMP-14 N233Y",
    }
    keys = [(row.enzyme_variant, row.compound) for row in rows]
    assert len(keys) == len(set(keys)) == 30


def test_readiness_does_not_equate_source_rows_with_independent_experiments(
    tmp_path: Path,
) -> None:
    readiness = tmp_path / "readiness.md"
    assert build_outputs(SOURCE, tmp_path / "matrix.csv", tmp_path / "summary.csv", readiness) == (
        142,
        20,
    )
    text = readiness.read_text(encoding="utf-8")
    assert "30 source observations" in text
    assert "must not be described as 30 independent experiments" in text
    assert "Ten Paper 3 source observations" in text
