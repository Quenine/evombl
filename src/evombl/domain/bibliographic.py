from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

MetadataStatus = Literal[
    "seed_unchecked",
    "retrieval_pending",
    "retrieved_single_provider",
    "retrieved_multiple_providers",
    "metadata_verified",
    "metadata_conflict",
    "identifier_not_found",
    "manual_review_required",
]
ComparisonClass = Literal[
    "exact_agreement",
    "formatting_only_difference",
    "compatible_partial_metadata",
    "material_conflict",
    "identifier_conflict",
    "provider_missing",
    "unresolved",
]
RelevanceStatus = Literal[
    "likely_relevant",
    "possibly_relevant",
    "likely_not_relevant",
    "insufficient_metadata",
    "manual_review_required",
]


class MetadataCandidateRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    candidate_id: str
    seed_id: str
    source_id: str
    provider: str
    doi: str | None = None
    pmid: str | None = None
    pmcid: str | None = None
    title: str | None = None
    subtitle: str | None = None
    authors: list[str] = Field(default_factory=list)
    journal: str | None = None
    publisher: str | None = None
    publication_year: int | None = None
    electronic_publication_date: date | None = None
    issue_publication_date: date | None = None
    volume: str | None = None
    issue: str | None = None
    article_number: str | None = None
    pagination: str | None = None
    article_type: str | None = None
    publication_types: list[str] = Field(default_factory=list)
    abstract_available: bool | None = None
    update_indicators: list[str] = Field(default_factory=list)
    open_access: bool | None = None
    licence: str | None = None
    full_text_location: str | None = None
    supplementary_material: bool | None = None
    provider_record_id: str | None = None
    provider_version: str | None = None
    response_hash: str
    retrieval_event_id: str
    raw_provider_values: dict[str, Any] = Field(default_factory=dict)


class MetadataComparisonRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    comparison_id: str
    seed_id: str
    source_id: str
    provider_a: str
    provider_b: str
    field_name: str
    classification: ComparisonClass
    value_a: str | None = None
    value_b: str | None = None
    notes: str | None = None


class BibliographicAuditRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    seed_id: str
    source_id: str
    status: MetadataStatus
    verified_doi: str | None = None
    verified_pmid: str | None = None
    doi_pmid_link_verified: bool = False
    relevance_status: RelevanceStatus = "insufficient_metadata"
    relevance_rule: str
    open_access: bool | None = None
    licence: str | None = None
    manual_review_required: bool = True
    notes: list[str] = Field(default_factory=list)
