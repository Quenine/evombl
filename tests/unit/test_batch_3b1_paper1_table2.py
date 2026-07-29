from collections import Counter
from pathlib import Path

from evombl.scientific_extraction import load_observations

SOURCE = Path("data/curated/pilot/papers-001-003/measurements.csv")
DOI = "10.1128/aac.00991-23"
EXPECTED_LABELS = {
    "NDM-1",
    "NDM-2",
    "NDM-4",
    "NDM-5",
    "NDM-7",
    "NDM-9",
    "NDM-14",
    "NDM-19",
    "NDM-30",
    "NDM-35",
    "NDM-47",
    "VIM-1",
    "VIM-4",
    "VIM-5",
    "VIM-19",
    "VIM-1-Ala148Val",
    "VIM-2",
    "VIM-6",
    "VIM-53",
    "VIM-2-Val148Ala",
    "VIM-2-Glu149Lys",
    "VIM-83",
    "IMP-1",
    "IMP-2",
    "IMP-4",
    "IMP-13",
    "SIM-1",
    "SPM-1",
    "DIM-1",
    "GIM-1",
    "PFM-1",
    "AIM-1",
}


def _table2() -> list[object]:
    return [
        row
        for row in load_observations(SOURCE)
        if row.source_doi == DOI and row.source_table == "Table 2"
    ]


def test_paper1_table2_is_complete_and_each_variant_occurs_once() -> None:
    rows = _table2()
    assert len(load_observations(SOURCE)) == 142
    assert len(rows) == 32
    assert Counter(row.source_row_label for row in rows) == Counter(EXPECTED_LABELS)
    assert all(row.directness == "direct_table_value" for row in rows)


def test_table2_censoring_and_exact_values_are_preserved() -> None:
    rows = _table2()
    censored = [row for row in rows if row.relation == ">"]
    exact = [row for row in rows if row.relation == "="]
    assert len(censored) == 7
    assert all((row.value, row.unit) == ("100", "uM") for row in censored)
    assert len(exact) == 25
    assert all(row.unit == "uM" for row in exact)


def test_engineered_variants_retain_supplied_metadata() -> None:
    rows = {row.source_row_label: row for row in _table2() if row.variant_origin == "engineered"}
    assert {
        label: (row.reference_variant, row.author_reported_mutation, row.numbering_scheme)
        for label, row in rows.items()
    } == {
        "VIM-1-Ala148Val": ("VIM-1", "Ala148Val", "BBL"),
        "VIM-2-Val148Ala": ("VIM-2", "Val148Ala", "BBL"),
        "VIM-2-Glu149Lys": ("VIM-2", "Glu149Lys", "BBL"),
    }


def test_existing_non_table2_observations_remain_unchanged() -> None:
    original_ids = {
        "EVO-OBS-P1-006",
        "EVO-OBS-P1-007",
        "EVO-OBS-P2-001",
        "EVO-OBS-P2-002",
        "EVO-OBS-P2-003",
        "EVO-OBS-P2-004",
        "EVO-OBS-P2-005",
        "EVO-OBS-P2-006",
        "EVO-OBS-P3-001",
        "EVO-OBS-P3-002",
        "EVO-OBS-P3-003",
    }
    rows = {
        row.observation_id: (
            row.source_doi,
            row.source_table,
            row.compound,
            row.antibiotic_partner,
            row.assay_system,
            row.endpoint,
            row.relation,
            row.value,
            row.unit,
            row.fitted_value,
        )
        for row in load_observations(SOURCE)
        if row.observation_id in original_ids
    }
    assert rows == {
        "EVO-OBS-P1-006": (
            DOI,
            "Table 1",
            None,
            "cefepime",
            "whole_cell",
            "MIC",
            "=",
            "16",
            "ug/mL",
            None,
        ),
        "EVO-OBS-P1-007": (
            DOI,
            "Table 1",
            "taniborbactam",
            "cefepime",
            "whole_cell",
            "MIC",
            "=",
            "16",
            "ug/mL",
            None,
        ),
        "EVO-OBS-P2-001": (
            "10.1128/aac.01570-23",
            "Table 3",
            "xeruborbactam",
            None,
            "crude_extract",
            "IC50",
            "=",
            "5.4",
            "uM",
            None,
        ),
        "EVO-OBS-P2-002": (
            "10.1128/aac.01570-23",
            "Table 3",
            "taniborbactam",
            None,
            "crude_extract",
            "IC50",
            "=",
            "130",
            "uM",
            None,
        ),
        "EVO-OBS-P2-003": (
            "10.1128/aac.01570-23",
            "Table 3",
            "xeruborbactam",
            None,
            "crude_extract",
            "IC50",
            "=",
            "2.7",
            "uM",
            None,
        ),
        "EVO-OBS-P2-004": (
            "10.1128/aac.01570-23",
            "Table 3",
            "xeruborbactam",
            None,
            "crude_extract",
            "IC50",
            "=",
            "73",
            "uM",
            None,
        ),
        "EVO-OBS-P2-005": (
            "10.1128/aac.01570-23",
            "Table 4",
            "xeruborbactam",
            None,
            "purified_enzyme",
            "Ki",
            "=",
            "0.3",
            "uM",
            None,
        ),
        "EVO-OBS-P2-006": (
            "10.1128/aac.01570-23",
            "Table 4",
            "xeruborbactam",
            None,
            "purified_enzyme",
            "Ki",
            "=",
            "11.3",
            "uM",
            None,
        ),
        "EVO-OBS-P3-001": (
            "10.1128/aac.00297-25",
            "Table 3",
            "xeruborbactam",
            None,
            "crude_extract",
            "IC50",
            "=",
            "180",
            "uM",
            None,
        ),
        "EVO-OBS-P3-002": (
            "10.1128/aac.00297-25",
            "Table 3",
            "xeruborbactam",
            None,
            "crude_extract",
            "IC50",
            ">",
            "250",
            "uM",
            "680",
        ),
        "EVO-OBS-P3-003": (
            "10.1128/aac.00297-25",
            "Table 3",
            "taniborbactam",
            None,
            "crude_extract",
            "IC50",
            "=",
            "7.0",
            "uM",
            None,
        ),
    }
