from datetime import date

from pydantic import BaseModel, ConfigDict, model_validator

from .enums import (
    CensoringStatus,
    EndpointType,
    ExclusionStatus,
    ExtractionMethod,
    MeasurementRelation,
    VerificationStatus,
)

CONCENTRATION_ENDPOINTS = {
    EndpointType.IC50,
    EndpointType.KI,
    EndpointType.KD,
    EndpointType.MIC,
    EndpointType.SOLUBILITY,
}
CONCENTRATION_UNITS = {"M", "mM", "uM", "µM", "nM", "pM", "mg/L", "ug/mL", "µg/mL"}


class MeasurementRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")
    internal_measurement_id: str
    compound_id: str
    assay_id: str
    endpoint_type: EndpointType
    original_value: float
    original_units: str
    relation: MeasurementRelation = MeasurementRelation.EQ
    standard_value: float | None = None
    standard_units: str | None = None
    transformed_value: float | None = None
    transform_definition: str | None = None
    replicate_count: int | None = None
    standard_deviation: float | None = None
    standard_error: float | None = None
    lower_bound: float | None = None
    upper_bound: float | None = None
    censoring_status: CensoringStatus = CensoringStatus.NONE
    evidence_source_id: str
    evidence_location: str
    source_location_id: str
    extraction_method: ExtractionMethod
    curator: str
    extraction_date: date
    verification_status: VerificationStatus
    exclusion_status: ExclusionStatus = ExclusionStatus.INCLUDED
    exclusion_reason: str | None = None

    @model_validator(mode="after")
    def validate_semantics(self) -> "MeasurementRecord":
        expected = {
            MeasurementRelation.LT: CensoringStatus.LEFT,
            MeasurementRelation.LE: CensoringStatus.LEFT,
            MeasurementRelation.GT: CensoringStatus.RIGHT,
            MeasurementRelation.GE: CensoringStatus.RIGHT,
        }.get(self.relation)
        if expected and self.censoring_status != expected:
            raise ValueError("measurement relation and censoring status disagree")
        if not expected and self.censoring_status not in {
            CensoringStatus.NONE,
            CensoringStatus.INTERVAL,
        }:
            raise ValueError("uncensored relation requires none or interval censoring")
        if self.censoring_status == CensoringStatus.INTERVAL and (
            self.lower_bound is None or self.upper_bound is None
        ):
            raise ValueError("interval censoring requires both bounds")
        if (
            self.lower_bound is not None
            and self.upper_bound is not None
            and self.lower_bound > self.upper_bound
        ):
            raise ValueError("lower bound cannot exceed upper bound")
        if (
            self.endpoint_type in CONCENTRATION_ENDPOINTS
            and self.original_units not in CONCENTRATION_UNITS
        ):
            raise ValueError("concentration endpoint requires concentration-compatible units")
        if self.endpoint_type in CONCENTRATION_ENDPOINTS and self.original_value <= 0:
            raise ValueError("concentration values must be positive")
        if (
            self.endpoint_type in {EndpointType.PERCENT_INHIBITION, EndpointType.RESIDUAL_ACTIVITY}
            and not 0 <= self.original_value <= 100
        ):
            raise ValueError("percentage values must be between 0 and 100")
        if (
            self.endpoint_type in {EndpointType.MIC_FOLD_CHANGE, EndpointType.FIC}
            and self.original_value <= 0
        ):
            raise ValueError("ratio values must be positive")
        if self.exclusion_status == ExclusionStatus.EXCLUDED and not self.exclusion_reason:
            raise ValueError("excluded measurements require a reason")
        if self.exclusion_status == ExclusionStatus.INCLUDED and self.exclusion_reason:
            raise ValueError("included measurements cannot have an exclusion reason")
        if (self.standard_value is None) != (self.standard_units is None):
            raise ValueError("standard value and units must appear together")
        if self.transformed_value is not None and not self.transform_definition:
            raise ValueError("transformed value requires a transform definition")
        if self.replicate_count is not None and self.replicate_count < 1:
            raise ValueError("replicate count must be positive")
        if self.standard_deviation is not None and self.standard_deviation < 0:
            raise ValueError("standard deviation cannot be negative")
        if self.standard_error is not None and self.standard_error < 0:
            raise ValueError("standard error cannot be negative")
        return self
