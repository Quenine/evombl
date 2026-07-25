from pydantic import BaseModel, ConfigDict

from .enums import StereoStatus


class CompoundRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")
    internal_compound_id: str
    source_compound_ids: dict[str, str] = {}
    original_smiles: str
    canonical_smiles: str | None = None
    isomeric_smiles: str | None = None
    standard_inchi: str | None = None
    standard_inchikey: str | None = None
    parent_inchikey: str | None = None
    stereochemistry_status: StereoStatus = StereoStatus.UNSPECIFIED
    salt_status: str | None = None
    molecular_formula: str | None = None
    molecular_weight: float | None = None
    scaffold_smiles: str | None = None
    inhibitor_class: str | None = None
    metal_binding_motif: str | None = None
    source_record_id: str
    curation_status: str
    curation_notes: str | None = None
