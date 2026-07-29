import csv
from pathlib import Path

import pandas as pd
import pytest
from pydantic import ValidationError

from evombl.scientific_extraction import (
    MEASUREMENT_FIELDS,
    ScientificObservation,
    build_outputs,
    load_observations,
    validate_and_report,
)

SOURCE = Path("data/curated/pilot/papers-001-003/measurements.csv")


def test_all_pilot_records_validate_and_contexts_remain_separate() -> None:
    rows = load_observations(SOURCE)
    assert len(rows) == 109
    censored = next(row for row in rows if row.observation_id == "EVO-OBS-P1-004")
    fitted = next(row for row in rows if row.observation_id == "EVO-OBS-P3-002")
    assert (censored.relation, censored.value) == (">", "100")
    assert (fitted.relation, fitted.value, fitted.fitted_value) == (">", "250", "680")
    assert {row.endpoint for row in rows if row.enzyme_variant == "IMP-1"} == {"IC50", "Ki"}
    assert {row.assay_system for row in rows if row.enzyme_variant == "IMP-1"} == {
        "crude_extract",
        "purified_enzyme",
    }
    mic = [row for row in rows if row.endpoint == "MIC"]
    assert len(mic) == 2
    assert {row.compound for row in mic} == {None, "taniborbactam"}


def test_csv_parquet_round_trip_preserves_scientific_strings(tmp_path: Path) -> None:
    parquet = tmp_path / "measurements.parquet"
    validate_and_report(SOURCE, parquet, tmp_path / "qc.csv")
    frame = pd.read_parquet(parquet).fillna("")
    original = pd.read_csv(SOURCE, dtype=str, keep_default_na=False)
    assert frame.to_dict("records") == original.to_dict("records")


def _record(**changes: object) -> dict[str, object]:
    row = load_observations(SOURCE)[0].model_dump()
    row.update(changes)
    return row


@pytest.mark.parametrize(
    "changes",
    [
        {"relation": "~"},
        {"fitted_value": "2"},
        {"source_doi": ""},
        {"source_table": ""},
    ],
)
def test_invalid_observations_fail(changes: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        ScientificObservation.model_validate(_record(**changes))


def test_duplicate_ids_fail(tmp_path: Path) -> None:
    rows = list(csv.DictReader(SOURCE.open(encoding="utf-8")))
    rows.append(rows[0])
    target = tmp_path / "duplicate.csv"
    with target.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=MEASUREMENT_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    with pytest.raises(ValueError, match="duplicate observation IDs"):
        load_observations(target)


def test_matrix_is_deterministic_and_performs_no_averaging(tmp_path: Path) -> None:
    first = tmp_path / "first.csv"
    second = tmp_path / "second.csv"
    args = (tmp_path / "summary.csv", tmp_path / "readiness.md")
    assert build_outputs(SOURCE, first, *args) == (109, 20)
    assert build_outputs(SOURCE, second, *args) == (109, 20)
    assert first.read_bytes() == second.read_bytes()
    rows = list(csv.DictReader(first.open(encoding="utf-8")))
    ndm9_tan = [
        row
        for row in rows
        if row["enzyme_variant"] == "NDM-9"
        and row["compound"] == "taniborbactam"
        and row["endpoint"] == "IC50"
    ]
    assert [(row["source_doi"], row["value"]) for row in ndm9_tan] == [
        ("10.1128/aac.00991-23", "53"),
        ("10.1128/aac.01570-23", "130"),
    ]
