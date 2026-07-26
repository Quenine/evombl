import csv
from collections import Counter
from decimal import Decimal, InvalidOperation
from pathlib import Path

import pandas as pd  # type: ignore[import-untyped]
from pydantic import BaseModel, ConfigDict, field_validator, model_validator

MEASUREMENT_FIELDS = (
    "observation_id",
    "source_doi",
    "source_table",
    "source_row_label",
    "compound",
    "antibiotic_partner",
    "fixed_inhibitor_concentration",
    "fixed_inhibitor_concentration_unit",
    "enzyme_family",
    "enzyme_variant",
    "reference_variant",
    "variant_origin",
    "author_reported_mutation",
    "numbering_scheme",
    "organism",
    "strain",
    "biological_context",
    "assay_category",
    "assay_system",
    "protein_preparation",
    "endpoint",
    "relation",
    "value",
    "unit",
    "fitted_value",
    "replicate_count",
    "directness",
    "quality_flags",
    "curator_note",
)
EVIDENCE_FIELDS = (
    "observation_id",
    "source_doi",
    "source_table",
    "compound",
    "antibiotic_partner",
    "fixed_inhibitor_concentration",
    "fixed_inhibitor_concentration_unit",
    "enzyme_family",
    "enzyme_variant",
    "reference_variant",
    "author_reported_mutation",
    "numbering_scheme",
    "assay_category",
    "assay_system",
    "protein_preparation",
    "endpoint",
    "relation",
    "value",
    "unit",
    "fitted_value",
)
CENSORED = {">", ">=", "<", "<="}


class ScientificObservation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    observation_id: str
    source_doi: str
    source_table: str
    source_row_label: str | None = None
    compound: str | None = None
    antibiotic_partner: str | None = None
    fixed_inhibitor_concentration: str | None = None
    fixed_inhibitor_concentration_unit: str | None = None
    enzyme_family: str
    enzyme_variant: str
    reference_variant: str | None = None
    variant_origin: str
    author_reported_mutation: str | None = None
    numbering_scheme: str | None = None
    organism: str | None = None
    strain: str | None = None
    biological_context: str | None = None
    assay_category: str
    assay_system: str
    protein_preparation: str | None = None
    endpoint: str
    relation: str
    value: str
    unit: str
    fitted_value: str | None = None
    replicate_count: int | None = None
    directness: str | None = None
    quality_flags: str | None = None
    curator_note: str | None = None

    @field_validator("relation")
    @classmethod
    def valid_relation(cls, value: str) -> str:
        if value not in {"=", ">", ">=", "<", "<="}:
            raise ValueError(f"invalid relation: {value}")
        return value

    @field_validator("unit", "fixed_inhibitor_concentration_unit")
    @classmethod
    def valid_unit(cls, value: str | None) -> str | None:
        if value is not None and value not in {"uM", "ug/mL"}:
            raise ValueError(f"invalid unit: {value}")
        return value

    @field_validator("value", "fitted_value", "fixed_inhibitor_concentration")
    @classmethod
    def positive_value(cls, value: str | None) -> str | None:
        if value is None:
            return value
        try:
            if Decimal(value) <= 0:
                raise ValueError("concentration values must be positive")
        except InvalidOperation as exc:
            raise ValueError(f"invalid numeric value: {value}") from exc
        return value

    @model_validator(mode="after")
    def valid_context(self) -> "ScientificObservation":
        if not self.source_doi.strip() or not self.source_table.strip():
            raise ValueError("source DOI and source table are required")
        if self.fitted_value is not None and self.relation not in CENSORED:
            raise ValueError("fitted value requires a censored reported observation")
        if (self.fixed_inhibitor_concentration is None) != (
            self.fixed_inhibitor_concentration_unit is None
        ):
            raise ValueError("fixed inhibitor concentration and unit must appear together")
        valid = {
            ("biochemical_inhibition", "crude_extract", "IC50"),
            ("biochemical_inhibition", "purified_enzyme", "Ki"),
            ("antimicrobial_susceptibility", "whole_cell", "MIC"),
        }
        if (self.assay_category, self.assay_system, self.endpoint) not in valid:
            raise ValueError("incompatible endpoint and assay context")
        return self


def load_observations(path: Path) -> list[ScientificObservation]:
    with path.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        if tuple(reader.fieldnames or ()) != MEASUREMENT_FIELDS:
            raise ValueError("measurement columns do not match the required schema")
        rows = list(reader)
    counts = Counter(row["observation_id"] for row in rows)
    duplicates = sorted(key for key, count in counts.items() if count > 1)
    if duplicates:
        raise ValueError(f"duplicate observation IDs: {', '.join(duplicates)}")
    return [
        ScientificObservation.model_validate(
            {key: value if value != "" else None for key, value in row.items()}
        )
        for row in rows
    ]


def _rows(
    observations: list[ScientificObservation], fields: tuple[str, ...]
) -> list[dict[str, object]]:
    output = []
    for observation in observations:
        data = observation.model_dump(mode="python")
        output.append({field: "" if data[field] is None else data[field] for field in fields})
    return output


def _write_csv(path: Path, fields: tuple[str, ...], rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def validate_and_report(source: Path, parquet: Path, report: Path) -> int:
    observations = load_observations(source)
    parquet.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(_rows(observations, MEASUREMENT_FIELDS), columns=MEASUREMENT_FIELDS).astype(
        "string"
    ).to_parquet(parquet, index=False)
    _write_csv(
        report,
        ("observation_id", "validation_status", "quality_flags"),
        [
            {
                "observation_id": item.observation_id,
                "validation_status": "valid",
                "quality_flags": item.quality_flags or "",
            }
            for item in observations
        ],
    )
    return len(observations)


def build_outputs(source: Path, matrix: Path, summary: Path, readiness: Path) -> tuple[int, int]:
    observations = load_observations(source)
    _write_csv(matrix, EVIDENCE_FIELDS, _rows(observations, EVIDENCE_FIELDS))
    counts = Counter(
        (item.assay_category, item.assay_system, item.protein_preparation or "", item.endpoint)
        for item in observations
    )
    fields = (
        "assay_category",
        "assay_system",
        "protein_preparation",
        "endpoint",
        "observation_count",
    )
    _write_csv(
        summary,
        fields,
        [dict(zip(fields, (*key, count), strict=True)) for key, count in sorted(counts.items())],
    )
    readiness.parent.mkdir(parents=True, exist_ok=True)
    readiness.write_text(
        "# Batch 3A readiness\n\n"
        "- This is a 16-observation pilot.\n"
        "- This is not complete paper extraction.\n"
        "- This dataset is not ready for modelling.\n"
        "- Protein identities and mutations remain paper-reported, not independently verified.\n"
        "- No hit or lead claims are permitted.\n",
        encoding="utf-8",
    )
    return len(observations), len(EVIDENCE_FIELDS)
