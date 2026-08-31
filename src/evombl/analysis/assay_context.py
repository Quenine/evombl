import csv
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

import pandas as pd  # type: ignore[import-untyped]

from evombl.analysis.paired_inhibitors import derive_censor_aware_ratio
from evombl.scientific_extraction import ScientificObservation, load_observations

SOURCE_DOI = "10.1128/aac.01570-23"
BRIDGE_VARIANTS = ("NDM-1", "VIM-2", "IMP-1", "IMP-10")
COMPOUNDS = {"xeruborbactam", "taniborbactam"}
BRIDGE_COLUMNS = (
    "enzyme_family",
    "enzyme_variant",
    "reference_variant",
    "author_reported_mutation",
    "numbering_scheme",
    "crude_xer_observation_id",
    "crude_xer_relation",
    "crude_xer_value",
    "crude_xer_unit",
    "crude_tan_observation_id",
    "crude_tan_relation",
    "crude_tan_value",
    "crude_tan_unit",
    "crude_ratio_class",
    "crude_ratio_exact",
    "crude_ratio_lower_bound",
    "crude_ratio_upper_bound",
    "crude_direction_class",
    "ki_xer_observation_id",
    "ki_xer_relation",
    "ki_xer_value",
    "ki_xer_unit",
    "ki_tan_observation_id",
    "ki_tan_relation",
    "ki_tan_value",
    "ki_tan_unit",
    "ki_ratio_class",
    "ki_ratio_exact",
    "ki_ratio_lower_bound",
    "ki_ratio_upper_bound",
    "ki_direction_class",
    "direction_concordance",
    "quantitative_cross_endpoint_comparison",
    "interpretation_guardrail",
)
SUMMARY_COLUMNS = (
    "source_doi",
    "variant_count",
    "source_observation_count",
    "crude_pair_count",
    "ki_pair_count",
    "crude_exact_ratio_count",
    "crude_lower_bound_ratio_count",
    "ki_exact_ratio_count",
    "ki_lower_bound_ratio_count",
    "direction_concordant_count",
    "direction_discordant_count",
    "direction_unresolved_count",
    "cross_endpoint_ratio_count",
    "inferential_test_count",
)
EXPECTED_SOURCE_IDS = {
    "EVO-OBS-P2-003",
    "EVO-OBS-P2-004",
    "EVO-OBS-P2-005",
    "EVO-OBS-P2-006",
    "EVO-OBS-P2-007",
    "EVO-OBS-P2-008",
    "EVO-OBS-P2-037",
    "EVO-OBS-P2-038",
    "EVO-OBS-P2-073",
    "EVO-OBS-P2-074",
    "EVO-OBS-P2-075",
    "EVO-OBS-P2-076",
    "EVO-OBS-P2-077",
    "EVO-OBS-P2-078",
    "EVO-OBS-P2-043",
    "EVO-OBS-P2-050",
}


@dataclass(frozen=True)
class ContextPair:
    xer: ScientificObservation
    tan: ScientificObservation
    ratio: dict[str, str]


def _write_csv(path: Path, fields: tuple[str, ...], rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def _neutral_direction(direction: str) -> str:
    return {
        "tan_endpoint_gt_xer_supported": "tan_gt_xer_supported",
        "tan_endpoint_lt_xer_supported": "tan_lt_xer_supported",
        "direction_unresolved": "direction_unresolved",
        "equal": "equal",
    }[direction]


def _select_context(
    observations: list[ScientificObservation], assay_system: str, endpoint: str
) -> list[ScientificObservation]:
    rows = [
        row
        for row in observations
        if (
            row.source_doi == SOURCE_DOI
            and row.source_table == "Table 3"
            and assay_system == "crude_extract"
            and row.assay_category == "biochemical_inhibition"
            and row.assay_system == assay_system
            and row.endpoint == endpoint
            and row.enzyme_variant in BRIDGE_VARIANTS
            and row.compound in COMPOUNDS
        )
    ]
    return rows


def _select_ki(observations: list[ScientificObservation]) -> list[ScientificObservation]:
    return [
        row
        for row in observations
        if row.source_doi == SOURCE_DOI
        and row.source_table == "Table 4"
        and row.assay_category == "biochemical_inhibition"
        and row.assay_system == "purified_enzyme"
        and row.endpoint == "Ki"
        and row.enzyme_variant in BRIDGE_VARIANTS
        and row.compound in COMPOUNDS
    ]


def _pair_context(rows: list[ScientificObservation], label: str) -> dict[str, ContextPair]:
    grouped: dict[str, list[ScientificObservation]] = defaultdict(list)
    for row in rows:
        grouped[row.enzyme_variant].append(row)
    if set(grouped) != set(BRIDGE_VARIANTS) or any(len(group) != 2 for group in grouped.values()):
        raise ValueError(
            f"{label} bridge selection must contain exactly four two-observation variants"
        )
    pairs: dict[str, ContextPair] = {}
    for variant in BRIDGE_VARIANTS:
        group = grouped[variant]
        by_compound: dict[str, list[ScientificObservation]] = defaultdict(list)
        for row in group:
            by_compound[row.compound or ""].append(row)
        if set(by_compound) != COMPOUNDS or any(len(items) != 1 for items in by_compound.values()):
            raise ValueError(f"{label} {variant}: requires one XER and one TAN observation")
        xer = by_compound["xeruborbactam"][0]
        tan = by_compound["taniborbactam"][0]
        if xer.unit != tan.unit:
            raise ValueError(f"{label} {variant}: XER and TAN units differ")
        for field in (
            "enzyme_family",
            "reference_variant",
            "author_reported_mutation",
            "numbering_scheme",
            "protein_preparation",
        ):
            if getattr(xer, field) != getattr(tan, field):
                raise ValueError(f"{label} {variant}: context differs in {field}")
        ratio = derive_censor_aware_ratio(xer, tan, direction_prefix="endpoint")
        ratio["direction_class"] = _neutral_direction(ratio["direction_class"])
        pairs[variant] = ContextPair(xer, tan, ratio)
    return pairs


def _ratio_output(prefix: str, pair: ContextPair) -> dict[str, str]:
    ratio = pair.ratio
    return {
        f"{prefix}_ratio_class": ratio["ratio_class"],
        f"{prefix}_ratio_exact": ratio["ratio_exact"],
        f"{prefix}_ratio_lower_bound": ratio["ratio_lower_bound"],
        f"{prefix}_ratio_upper_bound": ratio["ratio_upper_bound"],
        f"{prefix}_direction_class": ratio["direction_class"],
    }


def _build_rows(
    crude: dict[str, ContextPair], ki: dict[str, ContextPair]
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for variant in BRIDGE_VARIANTS:
        crude_pair = crude[variant]
        ki_pair = ki[variant]
        crude_direction = crude_pair.ratio["direction_class"]
        ki_direction = ki_pair.ratio["direction_class"]
        concordance = (
            "direction_concordant"
            if crude_direction == ki_direction and crude_direction != "direction_unresolved"
            else "direction_unresolved"
            if "direction_unresolved" in {crude_direction, ki_direction}
            else "direction_discordant"
        )
        row: dict[str, object] = {
            "enzyme_family": crude_pair.xer.enzyme_family,
            "enzyme_variant": variant,
            "reference_variant": crude_pair.xer.reference_variant or "",
            "author_reported_mutation": crude_pair.xer.author_reported_mutation or "",
            "numbering_scheme": crude_pair.xer.numbering_scheme or "",
            "crude_xer_observation_id": crude_pair.xer.observation_id,
            "crude_xer_relation": crude_pair.xer.relation,
            "crude_xer_value": crude_pair.xer.value,
            "crude_xer_unit": crude_pair.xer.unit,
            "crude_tan_observation_id": crude_pair.tan.observation_id,
            "crude_tan_relation": crude_pair.tan.relation,
            "crude_tan_value": crude_pair.tan.value,
            "crude_tan_unit": crude_pair.tan.unit,
            "ki_xer_observation_id": ki_pair.xer.observation_id,
            "ki_xer_relation": ki_pair.xer.relation,
            "ki_xer_value": ki_pair.xer.value,
            "ki_xer_unit": ki_pair.xer.unit,
            "ki_tan_observation_id": ki_pair.tan.observation_id,
            "ki_tan_relation": ki_pair.tan.relation,
            "ki_tan_value": ki_pair.tan.value,
            "ki_tan_unit": ki_pair.tan.unit,
            "direction_concordance": concordance,
            "quantitative_cross_endpoint_comparison": "not_performed",
            "interpretation_guardrail": "IC50 and Ki are distinct endpoints; only within-endpoint TAN/XER direction is compared.",
        }
        row.update(_ratio_output("crude", crude_pair))
        row.update(_ratio_output("ki", ki_pair))
        rows.append(row)
    return rows


def _write_parquet(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows, columns=BRIDGE_COLUMNS).astype("string").to_parquet(path, index=False)


def run_assay_context_bridge(input_path: Path, report_dir: Path) -> tuple[int, int, int]:
    observations = load_observations(input_path)
    crude = _select_context(observations, "crude_extract", "IC50")
    ki = _select_ki(observations)
    if (
        len(crude) != 8
        or len(ki) != 8
        or {row.observation_id for row in crude + ki} != EXPECTED_SOURCE_IDS
    ):
        raise ValueError("assay-context bridge must select exactly the expected 16 observations")
    crude_pairs = _pair_context(crude, "crude IC50")
    ki_pairs = _pair_context(ki, "purified Ki")
    rows = _build_rows(crude_pairs, ki_pairs)
    if len(rows) != 4:
        raise ValueError("assay-context bridge must produce four variants")
    report_dir.mkdir(parents=True, exist_ok=True)
    _write_csv(report_dir / "assay-context-bridge.csv", BRIDGE_COLUMNS, rows)
    _write_parquet(report_dir / "assay-context-bridge.parquet", rows)
    summary = {
        "source_doi": SOURCE_DOI,
        "variant_count": 4,
        "source_observation_count": 16,
        "crude_pair_count": 4,
        "ki_pair_count": 4,
        "crude_exact_ratio_count": sum(row["crude_ratio_class"] == "exact" for row in rows),
        "crude_lower_bound_ratio_count": sum(
            row["crude_ratio_class"] == "lower_bound" for row in rows
        ),
        "ki_exact_ratio_count": sum(row["ki_ratio_class"] == "exact" for row in rows),
        "ki_lower_bound_ratio_count": sum(row["ki_ratio_class"] == "lower_bound" for row in rows),
        "direction_concordant_count": sum(
            row["direction_concordance"] == "direction_concordant" for row in rows
        ),
        "direction_discordant_count": sum(
            row["direction_concordance"] == "direction_discordant" for row in rows
        ),
        "direction_unresolved_count": sum(
            row["direction_concordance"] == "direction_unresolved" for row in rows
        ),
        "cross_endpoint_ratio_count": 0,
        "inferential_test_count": 0,
    }
    _write_csv(report_dir / "context-summary.csv", SUMMARY_COLUMNS, [summary])
    (report_dir / "readiness.md").write_text(
        "# Batch 3D2 assay-context bridge readiness\n\n"
        "- Sixteen curated Paper 2 observations form four crude IC50 XER/TAN pairs and four purified Ki XER/TAN pairs.\n"
        "- The four bridge variants are NDM-1, VIM-2, IMP-1, and IMP-10.\n"
        "- IC50 and Ki remain explicitly distinct assay endpoints.\n"
        "- No IC50-to-Ki conversion or IC50/Ki fold quotient was calculated.\n"
        "- Censor thresholds were not treated as exact concentrations.\n"
        "- NDM-1 has TAN/XER <1 in both contexts; VIM-2 has TAN/XER >1 in both contexts.\n"
        "- IMP-1 and IMP-10 have TAN/XER >1 supported by lower bounds in both contexts.\n"
        "- Direction is concordant across contexts for all four selected variants.\n"
        "- This is descriptive directional concordance, not proof of quantitative equivalence between crude IC50 and purified Ki.\n"
        "- No correlation, p-value, confidence interval, regression, or mechanistic inference was performed.\n"
        "- Structural, causal, predictive, hit, and lead claims remain unauthorised.\n",
        encoding="utf-8",
    )
    return 16, 4, sum(row["direction_concordance"] == "direction_concordant" for row in rows)
