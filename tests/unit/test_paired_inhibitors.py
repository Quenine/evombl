import csv
import shutil
from pathlib import Path

import pandas as pd
import pytest

from evombl.analysis.paired_inhibitors import (
    PAIR_COLUMNS,
    run_paired_ic50_analysis,
)

SOURCE = Path("data/curated/pilot/papers-001-003/measurements.csv")
ADJUDICATION = Path("data/curated/identities/imp_escape_core/imp14_engineered_mutants.csv")


def _run(tmp_path: Path) -> Path:
    report = tmp_path / "reports"
    assert run_paired_ic50_analysis(SOURCE, ADJUDICATION, report) == (100, 50, 5)
    return report


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


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


def test_selected_pairs_and_censor_classes_by_paper(tmp_path: Path) -> None:
    report = _run(tmp_path)
    rows = _rows(report / "paired-ic50-analysis.csv")
    assert len(rows) == 50
    assert {row["source_doi"] for row in rows} == {
        "10.1128/aac.01570-23",
        "10.1128/aac.00297-25",
    }
    for doi, expected in {
        "10.1128/aac.01570-23": {
            "exact": 21,
            "lower_bound": 11,
            "upper_bound": 1,
            "indeterminate": 2,
        },
        "10.1128/aac.00297-25": {
            "exact": 3,
            "lower_bound": 10,
            "upper_bound": 0,
            "indeterminate": 2,
        },
    }.items():
        assert {
            category: sum(
                row["ratio_class"] == category for row in rows if row["source_doi"] == doi
            )
            for category in expected
        } == expected


def test_direction_counts_and_sentinels(tmp_path: Path) -> None:
    report = _run(tmp_path)
    rows = _rows(report / "paired-ic50-analysis.csv")
    for doi, expected in {
        "10.1128/aac.01570-23": {
            "tan_ic50_gt_xer_supported": 24,
            "tan_ic50_lt_xer_supported": 9,
            "direction_unresolved": 2,
        },
        "10.1128/aac.00297-25": {
            "tan_ic50_gt_xer_supported": 10,
            "tan_ic50_lt_xer_supported": 3,
            "direction_unresolved": 2,
        },
    }.items():
        assert {
            category: sum(
                row["direction_class"] == category for row in rows if row["source_doi"] == doi
            )
            for category in expected
        } == expected
    by_variant = {(row["source_doi"], row["enzyme_variant"]): row for row in rows}
    assert by_variant[("10.1128/aac.01570-23", "NDM-9")]["ratio_exact"] == "24.074074"
    assert by_variant[("10.1128/aac.01570-23", "IMP-1")]["ratio_lower_bound"] == "37.037037"
    assert by_variant[("10.1128/aac.01570-23", "SPM-1")]["ratio_upper_bound"] == "0.027000"
    for key in (("10.1128/aac.01570-23", "PFM-1"), ("10.1128/aac.00297-25", "IMP-14")):
        assert by_variant[key]["ratio_class"] == "indeterminate"
        assert not any(
            by_variant[key][field]
            for field in ("ratio_exact", "ratio_lower_bound", "ratio_upper_bound")
        )
    assert by_variant[("10.1128/aac.00297-25", "IMP-14")]["xer_fitted_value"] == "680"
    assert by_variant[("10.1128/aac.00297-25", "IMP-14")]["ratio_class"] == "indeterminate"
    assert by_variant[("10.1128/aac.00297-25", "IMP-14 D227Y")]["ratio_exact"] == "0.816000"


def test_imp14_enrichment_and_republication_audit(tmp_path: Path) -> None:
    report = _run(tmp_path)
    rows = _rows(report / "paired-ic50-analysis.csv")
    engineered = {
        row["enzyme_variant"]: row for row in rows if row["enzyme_variant"].startswith("IMP-14 ")
    }
    assert {row["adjudicated_precursor_mutation"] for row in engineered.values()} == {
        "S47G",
        "H134N",
        "N137S",
        "D181Y",
        "Y185N",
    }
    n233y = engineered["IMP-14 N233Y"]
    assert n233y["author_reported_mutation"] == "N233Y"
    assert n233y["adjudicated_precursor_mutation"] == "Y185N"
    audit = _rows(report / "republished-pair-audit.csv")
    assert len(audit) == 5
    assert {row["xer_comparison_class"] for row in audit} == {"exact_relation_and_value_match"}
    assert (
        sum(
            row["tan_comparison_class"] == "same_censor_direction_threshold_changed"
            for row in audit
        )
        == 4
    )
    assert (
        sum(row["tan_comparison_class"] == "exact_relation_and_value_match" for row in audit) == 1
    )
    assert sum(row["pair_directness_class"] == "prior_study_republication" for row in rows) == 5
    assert all(row["pair_directness_class"] != "independent_experiment" for row in rows)


def test_family_summary_is_paper_specific_and_count_only(tmp_path: Path) -> None:
    report = _run(tmp_path)
    summary = _rows(report / "family-summary.csv")
    assert len(summary) == 11
    assert {row["source_doi"] for row in summary} == {
        "10.1128/aac.01570-23",
        "10.1128/aac.00297-25",
    }
    assert not any("mean" in field or "median" in field for field in summary[0])


def test_csv_and_parquet_are_semantically_equal_and_deterministic(tmp_path: Path) -> None:
    first = _run(tmp_path / "first")
    second = _run(tmp_path / "second")
    for name in (
        "paired-ic50-analysis.csv",
        "republished-pair-audit.csv",
        "family-summary.csv",
        "readiness.md",
    ):
        assert (first / name).read_bytes() == (second / name).read_bytes()
    csv_rows = _rows(first / "paired-ic50-analysis.csv")
    parquet_rows = (
        pd.read_parquet(first / "paired-ic50-analysis.parquet")
        .fillna("")
        .astype(str)
        .to_dict("records")
    )
    assert list(pd.read_parquet(first / "paired-ic50-analysis.parquet").columns) == list(
        PAIR_COLUMNS
    )
    assert parquet_rows == csv_rows


@pytest.mark.parametrize(
    "mutate",
    [
        lambda rows: next(row for row in rows if row["observation_id"] == "EVO-OBS-P2-002").update(
            relation=">="
        ),
        lambda rows: next(row for row in rows if row["observation_id"] == "EVO-OBS-P2-002").update(
            unit="ug/mL"
        ),
        lambda rows: next(row for row in rows if row["observation_id"] == "EVO-OBS-P2-002").update(
            compound="xeruborbactam"
        ),
    ],
)
def test_invalid_selected_pair_inputs_fail(tmp_path: Path, mutate: object) -> None:
    source = _mutated_source(tmp_path, mutate)
    with pytest.raises(ValueError):
        run_paired_ic50_analysis(source, ADJUDICATION, tmp_path / "reports")


def test_missing_partner_and_mixed_directness_fail(tmp_path: Path) -> None:
    def remove_partner(rows: list[dict[str, str]]) -> None:
        rows[:] = [row for row in rows if row["observation_id"] != "EVO-OBS-P2-002"]

    with pytest.raises(ValueError, match="100 selected observations"):
        run_paired_ic50_analysis(
            _mutated_source(tmp_path / "missing", remove_partner),
            ADJUDICATION,
            tmp_path / "reports",
        )

    def mix_directness(rows: list[dict[str, str]]) -> None:
        next(row for row in rows if row["observation_id"] == "EVO-OBS-P3-005")["directness"] = (
            "direct_table_value"
        )

    with pytest.raises(ValueError, match="directness/republication"):
        run_paired_ic50_analysis(
            _mutated_source(tmp_path / "mixed", mix_directness), ADJUDICATION, tmp_path / "reports"
        )
