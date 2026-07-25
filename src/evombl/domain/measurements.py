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
        if (
            self.endpoint_type in CONCENTRATION_ENDPOINTS
            and self.original_units not in CONCENTRATION_UNITS
        ):
            raise ValueError("concentration endpoint requires concentration-compatible units")
        if self.exclusion_status == ExclusionStatus.EXCLUDED and not self.exclusion_reason:
            raise ValueError("excluded measurements require a reason")
        return self
