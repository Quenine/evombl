from collections import Counter
from pathlib import Path

from evombl.scientific_extraction import load_observations

SOURCE = Path("data/curated/pilot/papers-001-003/measurements.csv")
DOI = "10.1128/aac.01570-23"
SUPPLIED = {
    "NDM-1": ("4.3", "3.0"),
    "NDM-2": ("3.5", "2.0"),
    "NDM-4": ("2.0", "4.7"),
    "NDM-5": ("2.2", "5.2"),
    "NDM-7": ("2.3", "2.2"),
    "NDM-9": ("5.4", "130"),
    "NDM-14": ("2.4", "0.9"),
    "NDM-19": ("7.4", "4.0"),
    "NDM-30": ("1.6", "34"),
    "NDM-35": ("5.6", "8.6"),
    "NDM-47": ("9.2", "3.8"),
    "VIM-1": ("0.5", "0.8"),
    "VIM-4": ("0.05", "0.2"),
    "VIM-5": ("0.9", "1.4"),
    "VIM-19": ("0.2", "0.4"),
    "VIM-83": ("0.2", "55"),
    "VIM-2": ("0.1", "0.5"),
    "VIM-6": ("0.01", "0.5"),
    "VIM-53": ("0.14", "1.4"),
    "IMP-1": ("2.7", ">100"),
    "IMP-4": ("14.7", ">100"),
    "IMP-5": ("3.6", ">100"),
    "IMP-8": ("13.5", ">100"),
    "IMP-10": ("73", ">100"),
    "IMP-11": ("15.8", ">100"),
    "IMP-13": ("15.0", ">100"),
    "IMP-15": ("4.1", ">100"),
    "IMP-18": ("20.7", ">100"),
    "IMP-19": ("7.5", ">100"),
    "SIM-1": ("93", ">100"),
    "SPM-1": (">100", "2.7"),
    "DIM-1": ("11.4", "3.9"),
    "GIM-1": ("7.9", "1.3"),
    "PFM-1": (">100", ">100"),
    "AIM-1": (">100", ">100"),
}


def _table3() -> list[object]:
    return [
        row
        for row in load_observations(SOURCE)
        if row.source_doi == DOI and row.source_table == "Table 3"
    ]


def test_table3_has_complete_paired_variant_coverage() -> None:
    rows = _table3()
    assert len(load_observations(SOURCE)) == 142
    assert len(rows) == 70
    assert {row.enzyme_variant for row in rows} == set(SUPPLIED)
    assert Counter(row.enzyme_variant for row in rows) == Counter(
        {variant: 2 for variant in SUPPLIED}
    )
    assert all(
        {row.compound for row in rows if row.enzyme_variant == variant}
        == {"xeruborbactam", "taniborbactam"}
        for variant in SUPPLIED
    )


def test_all_table3_values_and_relations_match_supplied_table() -> None:
    actual = {
        (row.enzyme_variant, row.compound): (f">{row.value}" if row.relation == ">" else row.value)
        for row in _table3()
    }
    expected = {
        (variant, compound): value
        for variant, pair in SUPPLIED.items()
        for compound, value in zip(("xeruborbactam", "taniborbactam"), pair, strict=True)
    }
    assert actual == expected
    censored = [row for row in _table3() if row.relation == ">"]
    exact = [row for row in _table3() if row.relation == "="]
    assert len(censored) == 16
    assert all((row.value, row.unit) == ("100", "uM") for row in censored)
    assert len(exact) == 54


def test_existing_table3_rows_are_unique_and_metadata_is_preserved() -> None:
    rows = _table3()
    for variant, compound in [
        ("NDM-9", "xeruborbactam"),
        ("NDM-9", "taniborbactam"),
        ("IMP-1", "xeruborbactam"),
        ("IMP-10", "xeruborbactam"),
    ]:
        assert sum(row.enzyme_variant == variant and row.compound == compound for row in rows) == 1
    imp10 = [row for row in rows if row.enzyme_variant == "IMP-10"]
    assert {
        (row.reference_variant, row.author_reported_mutation, row.numbering_scheme) for row in imp10
    } == {("IMP-1", "Val67Phe", "BBL")}


def test_imipenem_footnote_is_preserved_for_both_pairs() -> None:
    rows = [row for row in _table3() if row.enzyme_variant in {"IMP-18", "PFM-1"}]
    assert len(rows) == 4
    assert all(row.quality_flags == "assay_substrate_imipenem" for row in rows)
    assert all(
        row.curator_note
        == "Table 3 footnote states that imipenem was used because cephalothin was not "
        "hydrolyzed by this enzyme."
        for row in rows
    )


def test_table4_ki_and_other_papers_remain_separate() -> None:
    rows = load_observations(SOURCE)
    table4 = {
        row.observation_id: (row.enzyme_variant, row.endpoint, row.relation, row.value, row.unit)
        for row in rows
        if row.observation_id in {"EVO-OBS-P2-005", "EVO-OBS-P2-006"}
    }
    assert table4 == {
        "EVO-OBS-P2-005": ("IMP-1", "Ki", "=", "0.3", "uM"),
        "EVO-OBS-P2-006": ("IMP-10", "Ki", "=", "11.3", "uM"),
    }
    assert sum(row.source_doi == "10.1128/aac.00991-23" for row in rows) == 34
    paper3 = {
        row.observation_id: (row.relation, row.value, row.fitted_value)
        for row in rows
        if row.observation_id in {"EVO-OBS-P3-001", "EVO-OBS-P3-002", "EVO-OBS-P3-003"}
    }
    assert paper3 == {
        "EVO-OBS-P3-001": ("=", "180", None),
        "EVO-OBS-P3-002": (">", "250", "680"),
        "EVO-OBS-P3-003": ("=", "7.0", None),
    }
