from datetime import date

from pydantic import BaseModel, ConfigDict

from .enums import SourceType


class EvidenceSourceRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_id: str
    source_type: SourceType
    title: str | None = None
    authors: list[str] = []
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
