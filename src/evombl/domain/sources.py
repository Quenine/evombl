import hashlib
import json
from datetime import date

from pydantic import BaseModel, ConfigDict, Field

from .enums import SourceType


class EvidenceSourceRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_id: str
    source_type: SourceType
    title: str | None = None
    authors: list[str] = Field(default_factory=list)
    year: int | None = None
    journal_or_authority: str | None = None
    doi: str | None = None
    pmid: str | None = None
    patent_number: str | None = None
    database_name: str | None = None
    database_record_id: str | None = None
    url: str | None = None
    access_date: date | None = None
    licence: str | None = None
    version: str | None = None
    file_hash: str | None = None
    notes: str | None = None


class SourceLocationRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_id: str
    location_type: str
    page: str | None = None
    section: str | None = None
    subsection: str | None = None
    object_label: str | None = None
    row_label: str | None = None
    panel: str | None = None
    verification_notes: str | None = None

    @property
    def location_id(self) -> str:
        payload = self.model_dump(mode="json", exclude={"location_id"}, exclude_none=True)
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:20]
        return f"EVO-LOC-{digest.upper()}"
