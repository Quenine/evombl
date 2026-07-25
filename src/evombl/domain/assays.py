from pydantic import BaseModel, ConfigDict, Field

from .enums import AssayCategory, EndpointType


class AssayRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")
    internal_assay_id: str
    assay_category: AssayCategory
    assay_format: str
    endpoint_type: EndpointType
    enzyme_variant_id: str | None = None
    substrate: str | None = None
    beta_lactam_partner: str | None = None
    zinc_concentration: float | None = None
    zinc_units: str | None = None
    buffer: str | None = None
    pH: float | None = Field(default=None, ge=0, le=14)
    temperature: float | None = None
    incubation_time: str | None = None
    expression_host: str | None = None
    bacterial_species: str | None = None
    bacterial_strain: str | None = None
    efflux_status: str | None = None
    permeability_status: str | None = None
    source_id: str
    source_location: str
    assay_comparability_group: str
    curation_confidence: str
