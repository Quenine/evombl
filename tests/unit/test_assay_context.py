import csv
import shutil
from pathlib import Path

import pandas as pd
import pytest

from evombl.analysis.assay_context import BRIDGE_COLUMNS, run_assay_context_bridge

SOURCE = Path("data/curated/pilot/papers-001-003/measurements.csv")


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def _run(tmp_path: Path) -> Path:
    report = tmp_path / "reports"
    assert run_assay_context_bridge(SOURCE, report) == (16, 4, 4)
    return report


def _mutated_source(tmp_path: Path, mutate: object) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    target = tmp_path / "measurements.csv"
    shutil.copyfile(SOURCE, target)
    rows = _rows(target)
    mutate(rows)
    with target.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=rows[0].keys(), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    return target


def test_bridge_counts_ratios_and_concordance(tmp_path: Path) -> None:
    report = _run(tmp_path)
    rows = _rows(report / "assay-context-bridge.csv")
    assert len(rows) == 4
    assert {row["enzyme_variant"] for row in rows} == {"NDM-1", "VIM-2", "IMP-1", "IMP-10"}
    assert {row["direction_concordance"] for row in rows} == {"direction_concordant"}
    by_variant = {row["enzyme_variant"]: row for row in rows}
    assert by_variant["NDM-1"]["crude_ratio_exact"] == "0.697674"
    assert by_variant["NDM-1"]["ki_ratio_exact"] == "0.200000"
    assert by_variant["VIM-2"]["crude_ratio_exact"] == "5.000000"
    assert by_variant["VIM-2"]["ki_ratio_exact"] == "5.000000"
    assert by_variant["IMP-1"]["crude_ratio_lower_bound"] == "37.037037"
    assert by_variant["IMP-1"]["ki_ratio_lower_bound"] == "66.666667"
    assert by_variant["IMP-10"]["crude_ratio_lower_bound"] == "1.369863"
    assert by_variant["IMP-10"]["ki_ratio_lower_bound"] == "1.769912"
    assert all(row["quantitative_cross_endpoint_comparison"] == "not_performed" for row in rows)


def test_bridge_has_no_cross_endpoint_numeric_schema_and_is_deterministic(tmp_path: Path) -> None:
    first = _run(tmp_path / "first")
    second = _run(tmp_path / "second")
    for name in ("assay-context-bridge.csv", "context-summary.csv", "readiness.md"):
        assert (first / name).read_bytes() == (second / name).read_bytes()
    rows = _rows(first / "assay-context-bridge.csv")
    forbidden = {
        "ic50_over_ki",
        "ki_over_ic50",
        "cross_endpoint_fold_change",
        "cross_endpoint_log_fold_change",
        "cross_endpoint_effect_size",
        "correlation",
    }
    assert not forbidden.intersection(rows[0])
    parquet = pd.read_parquet(first / "assay-context-bridge.parquet").fillna("").astype(str)
    assert list(parquet.columns) == list(BRIDGE_COLUMNS)
    assert parquet.to_dict("records") == rows


@pytest.mark.parametrize(
    "mutate",
    [
        lambda rows: next(row for row in rows if row["observation_id"] == "EVO-OBS-P2-073").update(
            unit="ug/mL"
        ),
        lambda rows: next(row for row in rows if row["observation_id"] == "EVO-OBS-P2-073").update(
            compound="taniborbactam"
        ),
        lambda rows: next(row for row in rows if row["observation_id"] == "EVO-OBS-P2-073").update(
            relation=">="
        ),
    ],
)
def test_invalid_bridge_pair_inputs_fail(tmp_path: Path, mutate: object) -> None:
    with pytest.raises(ValueError):
        run_assay_context_bridge(_mutated_source(tmp_path, mutate), tmp_path / "reports")


def test_missing_partner_and_wrong_context_fail(tmp_path: Path) -> None:
    def remove_partner(rows: list[dict[str, str]]) -> None:
        rows[:] = [row for row in rows if row["observation_id"] != "EVO-OBS-P2-074"]

    with pytest.raises(ValueError, match="expected 16 observations"):
        run_assay_context_bridge(
            _mutated_source(tmp_path / "missing", remove_partner), tmp_path / "reports"
        )

    def wrong_context(rows: list[dict[str, str]]) -> None:
        next(row for row in rows if row["observation_id"] == "EVO-OBS-P2-073")["endpoint"] = "IC50"

    with pytest.raises(ValueError):
        run_assay_context_bridge(
            _mutated_source(tmp_path / "context", wrong_context), tmp_path / "reports"
        )


def test_source_observation_ids_are_the_curated_records(tmp_path: Path) -> None:
    rows = _rows(_run(tmp_path) / "assay-context-bridge.csv")
    assert {row["crude_xer_observation_id"] for row in rows} == {
        "EVO-OBS-P2-007",
        "EVO-OBS-P2-037",
        "EVO-OBS-P2-003",
        "EVO-OBS-P2-004",
    }
    assert {row["ki_xer_observation_id"] for row in rows} == {
        "EVO-OBS-P2-073",
        "EVO-OBS-P2-075",
        "EVO-OBS-P2-005",
        "EVO-OBS-P2-006",
    }
