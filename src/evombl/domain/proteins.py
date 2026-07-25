from pydantic import BaseModel, ConfigDict

from .enums import MBLFamily, VerificationStatus


class MutationRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")
    author_reported_mutation: str
    author_numbering_scheme: str
    standardised_bbl_numbering: str | None = None
    reference_sequence_used: str
    verification_status: VerificationStatus


class ProteinVariantRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")
    internal_variant_id: str
    family: MBLFamily
    variant_name: str
    reference_variant: str | None = None
    raw_sequence: str
    mature_sequence: str | None = None
    sequence_accession: str | None = None
    nucleotide_accession: str | None = None
    organism: str | None = None
    signal_peptide_start: int | None = None
    signal_peptide_end: int | None = None
    numbering_scheme: str
    mutation_list: list[MutationRecord] = []
    sequence_hash: str
    structure_ids: list[str] = []
    evidence_source_ids: list[str] = []
    verification_status: VerificationStatus
    curation_notes: str | None = None
