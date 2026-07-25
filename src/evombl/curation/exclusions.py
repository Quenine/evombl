from evombl.domain.enums import ExclusionStatus
from evombl.domain.measurements import MeasurementRecord


def exclude(record: MeasurementRecord, reason: str) -> MeasurementRecord:
    if not reason.strip():
        raise ValueError("an exclusion reason is required")
    return record.model_copy(
        update={"exclusion_status": ExclusionStatus.EXCLUDED, "exclusion_reason": reason}
    )
