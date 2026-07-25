from pydantic import BaseModel, ConfigDict, Field, model_validator

from evombl.proteins.sequences import normalize_source_sequence, sequence_hash

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
    normalized_sequence: str | None = None
    source_had_terminal_stop: bool = False
    mature_sequence: str | None = None
    sequence_accession: str | None = None
    nucleotide_accession: str | None = None
    organism: str | None = None
    signal_peptide_start: int | None = None
    signal_peptide_end: int | None = None
    numbering_scheme: str
    mutation_list: list[MutationRecord] = Field(default_factory=list)
    sequence_hash: str
    structure_ids: list[str] = Field(default_factory=list)
    evidence_source_ids: list[str] = Field(default_factory=list)
    verification_status: VerificationStatus
    curation_notes: str | None = None

    @model_validator(mode="after")
    def validate_sequence_integrity(self) -> "ProteinVariantRecord":
        normalized, had_stop = normalize_source_sequence(self.raw_sequence)
        if self.normalized_sequence is not None and self.normalized_sequence != normalized:
            raise ValueError("normalized sequence does not match raw sequence")
        if self.source_had_terminal_stop != had_stop:
            raise ValueError("terminal stop provenance does not match raw sequence")
        if self.sequence_hash != sequence_hash(normalized):
            raise ValueError("sequence hash does not match normalized raw sequence")
        if (self.signal_peptide_start is None) != (self.signal_peptide_end is None):
            raise ValueError("both signal peptide coordinates are required")
        if self.signal_peptide_start is not None and self.signal_peptide_end is not None:
            if self.signal_peptide_start < 1 or self.signal_peptide_end < self.signal_peptide_start:
                raise ValueError("invalid signal peptide coordinates")
            if self.signal_peptide_end > len(normalized):
                raise ValueError("signal peptide coordinates exceed sequence length")
            expected = normalized[self.signal_peptide_end :]
            if self.mature_sequence is not None and self.mature_sequence != expected:
                raise ValueError("mature sequence does not match explicit signal-peptide rule")
        elif self.mature_sequence is not None:
            raise ValueError("mature sequence requires explicit signal-peptide coordinates")
        object.__setattr__(self, "normalized_sequence", normalized)
        return self
