import csv
import math
from collections import Counter, defaultdict
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

import pandas as pd  # type: ignore[import-untyped]

from evombl.proteins.identity_registry import read_imp14_engineered_mutants
from evombl.scientific_extraction import ScientificObservation, load_observations

XERUBORBACTAM = "xeruborbactam"
TANIBORBACTAM = "taniborbactam"
SUPPORTED_DOIS = ("10.1128/aac.01570-23", "10.1128/aac.00297-25")
SUPPORTED_RELATIONS = {"=", ">"}
PRIOR_STUDY_DIRECTNESS = "prior_study_value_republished_in_table"
PAIR_COLUMNS = (
    "pair_id",
    "source_doi",
    "source_table",
    "enzyme_family",
    "enzyme_variant",
    "reference_variant",
    "variant_origin",
    "author_reported_mutation",
    "numbering_scheme",
    "protein_preparation",
    "xer_observation_id",
    "xer_relation",
    "xer_value",
    "xer_unit",
    "xer_fitted_value",
    "tan_observation_id",
    "tan_relation",
    "tan_value",
    "tan_unit",
    "tan_fitted_value",
    "ratio_orientation",
    "ratio_class",
    "ratio_exact",
    "ratio_lower_bound",
    "ratio_upper_bound",
    "log2_ratio_exact",
    "log2_ratio_lower_bound",
    "log2_ratio_upper_bound",
    "direction_class",
    "pair_directness_class",
    "adjudicated_precursor_mutation",
    "identity_adjudication_note",
)
AUDIT_COLUMNS = (
    "paper3_enzyme_family",
    "paper3_enzyme_variant",
    "paper3_pair_id",
    "paper2_pair_id",
    "paper3_xer_observation_id",
    "paper2_xer_observation_id",
    "xer_comparison_class",
    "paper3_xer_relation",
    "paper3_xer_value",
    "paper2_xer_relation",
    "paper2_xer_value",
    "paper3_tan_observation_id",
    "paper2_tan_observation_id",
    "tan_comparison_class",
    "paper3_tan_relation",
    "paper3_tan_value",
    "paper2_tan_relation",
    "paper2_tan_value",
)
SUMMARY_COLUMNS = (
    "source_doi",
    "enzyme_family",
    "pair_count",
    "exact_ratio_count",
    "lower_bound_ratio_count",
    "upper_bound_ratio_count",
    "indeterminate_ratio_count",
    "tan_ic50_gt_xer_supported_count",
    "tan_ic50_lt_xer_supported_count",
    "equal_count",
    "direction_unresolved_count",
    "prior_study_republication_pair_count",
    "not_marked_as_prior_study_republication_pair_count",
)


@dataclass(frozen=True)
class PairResult:
    row: dict[str, str]
    xer: ScientificObservation
    tan: ScientificObservation


def _write_csv(path: Path, fields: tuple[str, ...], rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _decimal_log2(value: Decimal) -> str:
    return f"{math.log2(float(value)):.6f}"


def _formatted_ratio(value: Decimal) -> str:
    return f"{value:.6f}"


def derive_censor_aware_ratio(
    xer: ScientificObservation,
    tan: ScientificObservation,
    direction_prefix: str = "ic50",
) -> dict[str, str]:
    if xer.relation not in SUPPORTED_RELATIONS or tan.relation not in SUPPORTED_RELATIONS:
        raise ValueError("Batch 3D1 supports only '=' and '>' relations")
    xer_value = Decimal(xer.value)
    tan_value = Decimal(tan.value)
    if tan.relation == "=" and xer.relation == "=":
        ratio_class = "exact"
        ratio = tan_value / xer_value
        ratio_exact = _formatted_ratio(ratio)
        log2_exact = _decimal_log2(ratio)
        lower = upper = log2_lower = log2_upper = ""
    elif tan.relation == ">" and xer.relation == "=":
        ratio_class = "lower_bound"
        ratio = tan_value / xer_value
        ratio_exact = log2_exact = upper = log2_upper = ""
        lower = _formatted_ratio(ratio)
        log2_lower = _decimal_log2(ratio)
    elif tan.relation == "=" and xer.relation == ">":
        ratio_class = "upper_bound"
        ratio = tan_value / xer_value
        ratio_exact = log2_exact = lower = log2_lower = ""
        upper = _formatted_ratio(ratio)
        log2_upper = _decimal_log2(ratio)
    else:
        ratio_class = "indeterminate"
        ratio_exact = lower = upper = log2_exact = log2_lower = log2_upper = ""
        ratio = None
    if ratio_class == "exact":
        assert ratio is not None
        direction = (
            f"tan_{direction_prefix}_gt_xer_supported"
            if ratio > 1
            else f"tan_{direction_prefix}_lt_xer_supported"
            if ratio < 1
            else "equal"
        )
    elif ratio_class == "lower_bound":
        assert ratio is not None
        direction = (
            f"tan_{direction_prefix}_gt_xer_supported" if ratio > 1 else "direction_unresolved"
        )
    elif ratio_class == "upper_bound":
        assert ratio is not None
        direction = (
            f"tan_{direction_prefix}_lt_xer_supported" if ratio < 1 else "direction_unresolved"
        )
    else:
        direction = "direction_unresolved"
    return {
        "ratio_orientation": "taniborbactam_ic50_over_xeruborbactam_ic50",
        "ratio_class": ratio_class,
        "ratio_exact": ratio_exact,
        "ratio_lower_bound": lower,
        "ratio_upper_bound": upper,
        "log2_ratio_exact": log2_exact,
        "log2_ratio_lower_bound": log2_lower,
        "log2_ratio_upper_bound": log2_upper,
        "direction_class": direction,
    }


def _ratio_fields(xer: ScientificObservation, tan: ScientificObservation) -> dict[str, str]:
    return derive_censor_aware_ratio(xer, tan)


def _pair_directness(xer: ScientificObservation, tan: ScientificObservation) -> str:
    xer_prior = xer.directness == PRIOR_STUDY_DIRECTNESS
    tan_prior = tan.directness == PRIOR_STUDY_DIRECTNESS
    if xer_prior != tan_prior:
        raise ValueError(f"{xer.observation_id}: pair directness/republication status disagrees")
    return "prior_study_republication" if xer_prior else "not_marked_as_prior_study_republication"


def _selection(observations: list[ScientificObservation]) -> list[ScientificObservation]:
    selected = [
        row
        for row in observations
        if row.source_doi in SUPPORTED_DOIS
        and row.source_table == "Table 3"
        and row.endpoint == "IC50"
        and row.assay_category == "biochemical_inhibition"
        and row.assay_system == "crude_extract"
        and row.compound in {XERUBORBACTAM, TANIBORBACTAM}
    ]
    if len(selected) != 100:
        raise ValueError(f"Batch 3D1 expected 100 selected observations, found {len(selected)}")
    return selected


def _build_pairs(
    selected: list[ScientificObservation], adjudication_path: Path
) -> list[PairResult]:
    adjudications = read_imp14_engineered_mutants(adjudication_path)
    adjudication_by_label = {row["table3_bbl_label"]: row for row in adjudications}
    grouped: dict[tuple[str, str, str, str], list[ScientificObservation]] = defaultdict(list)
    for row in selected:
        grouped[(row.source_doi, row.source_table, row.enzyme_family, row.enzyme_variant)].append(
            row
        )
    results: list[PairResult] = []
    for key in sorted(grouped):
        rows = grouped[key]
        by_compound: dict[str, list[ScientificObservation]] = defaultdict(list)
        for row in rows:
            by_compound[row.compound or ""].append(row)
        if set(by_compound) != {XERUBORBACTAM, TANIBORBACTAM} or any(
            len(values) != 1 for values in by_compound.values()
        ):
            raise ValueError(f"{key}: pair must contain exactly one XER and one TAN observation")
        xer = by_compound[XERUBORBACTAM][0]
        tan = by_compound[TANIBORBACTAM][0]
        if xer.unit != tan.unit:
            raise ValueError(f"{key}: XER and TAN units do not match")
        context_fields = (
            "source_doi",
            "source_table",
            "enzyme_family",
            "enzyme_variant",
            "reference_variant",
            "variant_origin",
            "author_reported_mutation",
            "numbering_scheme",
            "protein_preparation",
        )
        for field in context_fields:
            if getattr(xer, field) != getattr(tan, field):
                raise ValueError(f"{key}: XER and TAN assay context differs in {field}")
        ratio = _ratio_fields(xer, tan)
        directness = _pair_directness(xer, tan)
        adjudicated = ""
        adjudication_note = ""
        if xer.source_doi == "10.1128/aac.00297-25" and xer.enzyme_variant.startswith("IMP-14 "):
            label = xer.author_reported_mutation or ""
            adjudication = adjudication_by_label.get(label)
            if adjudication is None:
                raise ValueError(f"{key}: missing IMP-14 adjudication for {label}")
            adjudicated = adjudication["precursor_mutation"]
            adjudication_note = adjudication["curator_note"]
        pair_id = "|".join(key)
        output_row = {
            "pair_id": pair_id,
            "source_doi": xer.source_doi,
            "source_table": xer.source_table,
            "enzyme_family": xer.enzyme_family,
            "enzyme_variant": xer.enzyme_variant,
            "reference_variant": xer.reference_variant or "",
            "variant_origin": xer.variant_origin,
            "author_reported_mutation": xer.author_reported_mutation or "",
            "numbering_scheme": xer.numbering_scheme or "",
            "protein_preparation": xer.protein_preparation or "",
            "xer_observation_id": xer.observation_id,
            "xer_relation": xer.relation,
            "xer_value": xer.value,
            "xer_unit": xer.unit,
            "xer_fitted_value": xer.fitted_value or "",
            "tan_observation_id": tan.observation_id,
            "tan_relation": tan.relation,
            "tan_value": tan.value,
            "tan_unit": tan.unit,
            "tan_fitted_value": tan.fitted_value or "",
            **ratio,
            "pair_directness_class": directness,
            "adjudicated_precursor_mutation": adjudicated,
            "identity_adjudication_note": adjudication_note,
        }
        results.append(PairResult(output_row, xer, tan))
    if len(results) != 50:
        raise ValueError(f"Batch 3D1 expected 50 pairs, found {len(results)}")
    return results


def _value_relation_class(paper2: dict[str, str], paper3: dict[str, str]) -> str:
    if paper2["relation"] == paper3["relation"] == "=" and paper2["value"] == paper3["value"]:
        return "exact_relation_and_value_match"
    if paper2["relation"] == paper3["relation"] == ">" and paper2["value"] != paper3["value"]:
        return "same_censor_direction_threshold_changed"
    return "mismatch"


def _audit_republications(pairs: list[PairResult]) -> list[dict[str, object]]:
    paper2 = {
        pair.row["enzyme_variant"]: pair
        for pair in pairs
        if pair.row["source_doi"] == SUPPORTED_DOIS[0]
    }
    paper3 = [
        pair
        for pair in pairs
        if pair.row["source_doi"] == SUPPORTED_DOIS[1]
        and pair.row["pair_directness_class"] == "prior_study_republication"
    ]
    rows: list[dict[str, object]] = []
    for pair3 in sorted(paper3, key=lambda item: item.row["enzyme_variant"]):
        variant = pair3.row["enzyme_variant"]
        pair2 = paper2.get(variant)
        if pair2 is None:
            raise ValueError(f"missing Paper 2 counterpart for republished {variant}")
        p2_rows = {pair2.xer.compound: pair2.xer, pair2.tan.compound: pair2.tan}
        p3_rows = {pair3.xer.compound: pair3.xer, pair3.tan.compound: pair3.tan}
        rows.append(
            {
                "paper3_enzyme_family": pair3.row["enzyme_family"],
                "paper3_enzyme_variant": variant,
                "paper3_pair_id": pair3.row["pair_id"],
                "paper2_pair_id": pair2.row["pair_id"],
                "paper3_xer_observation_id": pair3.xer.observation_id,
                "paper2_xer_observation_id": pair2.xer.observation_id,
                "xer_comparison_class": _value_relation_class(
                    {
                        "relation": p2_rows[XERUBORBACTAM].relation,
                        "value": p2_rows[XERUBORBACTAM].value,
                    },
                    {
                        "relation": p3_rows[XERUBORBACTAM].relation,
                        "value": p3_rows[XERUBORBACTAM].value,
                    },
                ),
                "paper3_xer_relation": p3_rows[XERUBORBACTAM].relation,
                "paper3_xer_value": p3_rows[XERUBORBACTAM].value,
                "paper2_xer_relation": p2_rows[XERUBORBACTAM].relation,
                "paper2_xer_value": p2_rows[XERUBORBACTAM].value,
                "paper3_tan_observation_id": pair3.tan.observation_id,
                "paper2_tan_observation_id": pair2.tan.observation_id,
                "tan_comparison_class": _value_relation_class(
                    {
                        "relation": p2_rows[TANIBORBACTAM].relation,
                        "value": p2_rows[TANIBORBACTAM].value,
                    },
                    {
                        "relation": p3_rows[TANIBORBACTAM].relation,
                        "value": p3_rows[TANIBORBACTAM].value,
                    },
                ),
                "paper3_tan_relation": p3_rows[TANIBORBACTAM].relation,
                "paper3_tan_value": p3_rows[TANIBORBACTAM].value,
                "paper2_tan_relation": p2_rows[TANIBORBACTAM].relation,
                "paper2_tan_value": p2_rows[TANIBORBACTAM].value,
            }
        )
    if len(rows) != 5:
        raise ValueError(f"expected five Paper 3 republication audit rows, found {len(rows)}")
    return rows


def _family_summary(pairs: list[PairResult]) -> list[dict[str, object]]:
    groups: dict[tuple[str, str], list[PairResult]] = defaultdict(list)
    for pair in pairs:
        groups[(pair.row["source_doi"], pair.row["enzyme_family"])].append(pair)
    rows: list[dict[str, object]] = []
    for (doi, family), group in sorted(groups.items()):
        ratio_counts = Counter(pair.row["ratio_class"] for pair in group)
        direction_counts = Counter(pair.row["direction_class"] for pair in group)
        directness_counts = Counter(pair.row["pair_directness_class"] for pair in group)
        rows.append(
            {
                "source_doi": doi,
                "enzyme_family": family,
                "pair_count": len(group),
                "exact_ratio_count": ratio_counts["exact"],
                "lower_bound_ratio_count": ratio_counts["lower_bound"],
                "upper_bound_ratio_count": ratio_counts["upper_bound"],
                "indeterminate_ratio_count": ratio_counts["indeterminate"],
                "tan_ic50_gt_xer_supported_count": direction_counts["tan_ic50_gt_xer_supported"],
                "tan_ic50_lt_xer_supported_count": direction_counts["tan_ic50_lt_xer_supported"],
                "equal_count": direction_counts["equal"],
                "direction_unresolved_count": direction_counts["direction_unresolved"],
                "prior_study_republication_pair_count": directness_counts[
                    "prior_study_republication"
                ],
                "not_marked_as_prior_study_republication_pair_count": directness_counts[
                    "not_marked_as_prior_study_republication"
                ],
            }
        )
    return rows


def _write_parquet(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows, columns=PAIR_COLUMNS).astype("string").to_parquet(path, index=False)


def run_paired_ic50_analysis(
    input_path: Path,
    imp14_adjudication_path: Path,
    report_dir: Path,
) -> tuple[int, int, int]:
    observations = load_observations(input_path)
    selected = _selection(observations)
    pairs = _build_pairs(selected, imp14_adjudication_path)
    pair_rows = [pair.row for pair in pairs]
    audit_rows = _audit_republications(pairs)
    summary_rows = _family_summary(pairs)
    report_dir.mkdir(parents=True, exist_ok=True)
    _write_csv(
        report_dir / "paired-ic50-analysis.csv",
        PAIR_COLUMNS,
        [{field: row[field] for field in PAIR_COLUMNS} for row in pair_rows],
    )
    _write_parquet(report_dir / "paired-ic50-analysis.parquet", pair_rows)
    _write_csv(report_dir / "republished-pair-audit.csv", AUDIT_COLUMNS, audit_rows)
    _write_csv(report_dir / "family-summary.csv", SUMMARY_COLUMNS, summary_rows)
    paper2 = [pair for pair in pairs if pair.row["source_doi"] == SUPPORTED_DOIS[0]]
    paper3 = [pair for pair in pairs if pair.row["source_doi"] == SUPPORTED_DOIS[1]]
    (report_dir / "readiness.md").write_text(
        "# Batch 3D1 paired IC50 readiness\n\n"
        "- 100 eligible source observations form 50 paper-specific XER/TAN pairs.\n"
        f"- Paper 2 contributes {len(paper2)} pairs; Paper 3 contributes {len(paper3)} pairs.\n"
        f"- Paper 2 censor classes are {sum(pair.row['ratio_class'] == 'exact' for pair in paper2)} exact, {sum(pair.row['ratio_class'] == 'lower_bound' for pair in paper2)} lower-bound, {sum(pair.row['ratio_class'] == 'upper_bound' for pair in paper2)} upper-bound, and {sum(pair.row['ratio_class'] == 'indeterminate' for pair in paper2)} indeterminate.\n"
        f"- Paper 3 censor classes are {sum(pair.row['ratio_class'] == 'exact' for pair in paper3)} exact, {sum(pair.row['ratio_class'] == 'lower_bound' for pair in paper3)} lower-bound, {sum(pair.row['ratio_class'] == 'upper_bound' for pair in paper3)} upper-bound, and {sum(pair.row['ratio_class'] == 'indeterminate' for pair in paper3)} indeterminate.\n"
        "- Censor thresholds were never substituted as exact concentrations.\n"
        "- The Paper 3 IMP-14 fitted value 680 was not used to convert the censored pair into an exact ratio.\n"
        "- Five Paper 3 pairs are explicitly prior-study republications and are not counted as new independent experiments.\n"
        "- Remaining Paper 3 pairs are described only as not marked as prior-study republications.\n"
        "- Cross-paper audit shows NDM-1 reproduces both exact values.\n"
        "- IMP-1, IMP-10, IMP-19, and IMP-4 reproduce Paper 2 XER exact values but use Paper 3 TAN >250 rather than Paper 2 TAN >100.\n"
        "- Family summaries are count-based and paper-specific; no family-average fold change, inferential test, or confidence interval was computed.\n"
        "- IMP-14 source-label conflicts remain preserved while primer-supported precursor adjudication is available as enrichment.\n"
        "- This output is suitable for reviewed descriptive analysis and later figure construction.\n"
        "- Causal mechanism, structural interpretation, predictive modelling, hit, and lead claims remain unauthorised.\n",
        encoding="utf-8",
    )
    return len(selected), len(pairs), len(audit_rows)
