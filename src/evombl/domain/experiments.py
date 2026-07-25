from datetime import date

from pydantic import BaseModel, ConfigDict, Field


class ExperimentalBatchRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")
    batch_id: str
    protocol_id: str
    laboratory: str
    operator: str
    date: date
    compound_batch: str
    protein_batch: str
    plate_or_run_id: str
    controls: list[str]
    raw_data_path: str
    processed_data_path: str | None = None
    analysis_version: str | None = None
    quality_status: str
    deviations: list[str] = Field(default_factory=list)
    signed_report_path: str | None = None
