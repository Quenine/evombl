from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict


class ImmutableRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class SourceDocumentRecord(ImmutableRecord):
    document_id: str
    source_id: str
    document_type: str
    record_hash: str


class SourceFileRecord(ImmutableRecord):
    file_id: str
    document_id: str
    path: Path
    sha256: str
    immutable: bool = True


class SourceIdentifierRecord(ImmutableRecord):
    identifier_id: str
    source_id: str
    scheme: str
    value: str


class SourceRetrievalEventRecord(ImmutableRecord):
    retrieval_id: str
    source_id: str
    provider: str
    accessed_at: datetime
    outcome: str = "success"
    response_hash: str | None = None
    response_path: Path | None = None
    error_type: str | None = None
    error_message: str | None = None


class SourceRevisionRecord(ImmutableRecord):
    revision_id: str
    source_id: str
    predecessor_revision_id: str | None = None
    previous_content_hash: str | None = None
    new_content_hash: str
    revision_reason: str
    detected_at: datetime
    actor: str
    retrieval_event_id: str
    verification_status: str
    notes: str | None = None


class CompoundAliasRecord(ImmutableRecord):
    alias_id: str
    compound_id: str
    alias: str
    source_id: str | None = None


class CompoundSourceLinkRecord(ImmutableRecord):
    compound_id: str
    source_id: str


class ProteinSequenceRecord(ImmutableRecord):
    sequence_id: str
    variant_id: str
    source_id: str
    sequence_kind: str
    sequence_hash: str
    sequence: str


class VariantAliasRecord(ImmutableRecord):
    alias_id: str
    variant_id: str
    alias: str
    source_id: str | None = None


class VariantSourceLinkRecord(ImmutableRecord):
    variant_id: str
    source_id: str


class VariantAccessionRecord(ImmutableRecord):
    accession_id: str
    variant_id: str
    accession: str
    accession_type: str
    source_database: str
    verification_status: str


class MutationObservationRecord(ImmutableRecord):
    observation_id: str
    variant_id: str
    reference_sequence_hash: str
    author_mutation: str
    author_numbering: str
    bbl_numbering: str | None = None
    verification_status: str


class NumberingMappingRecord(ImmutableRecord):
    mapping_id: str
    observation_id: str
    method: str
    verified: bool = False


class ProteinStructureRecord(ImmutableRecord):
    structure_id: str
    variant_id: str | None = None
    source_id: str
    database_id: str
    verification_status: str


class StructureChainRecord(ImmutableRecord):
    chain_id: str
    structure_id: str
    chain_label: str
    construct_start: int | None = None
    construct_end: int | None = None
    sequence_hash: str | None = None


class ProtocolRecord(ImmutableRecord):
    protocol_id: str
    source_id: str
    description: str


class AssayConditionRecord(ImmutableRecord):
    condition_id: str
    assay_id: str
    condition_type: str
    original_value: str | None = None
    original_units: str | None = None


class CurationEventRecord(ImmutableRecord):
    event_id: str
    entity_type: str
    entity_id: str
    event_type: str
    occurred_at: datetime
    actor: str
    details: dict[str, str]


class DataReleaseRecord(ImmutableRecord):
    release_id: str
    created_at: datetime
    manifest_hash: str
    manifest: dict[str, str]
