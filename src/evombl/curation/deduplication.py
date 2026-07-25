import hashlib
from collections import defaultdict
from collections.abc import Iterable

from evombl.domain.measurements import MeasurementRecord


def duplicate_key(record: MeasurementRecord) -> str:
    fields = (
        record.compound_id,
        record.assay_id,
        record.endpoint_type.value,
        record.evidence_source_id,
        record.evidence_location.strip(),
    )
    return hashlib.sha256("\x1f".join(fields).encode()).hexdigest()


def group_duplicates(
    records: Iterable[MeasurementRecord],
) -> dict[str, list[MeasurementRecord]]:
    groups: dict[str, list[MeasurementRecord]] = defaultdict(list)
    for record in records:
        groups[duplicate_key(record)].append(record)
    return {key: values for key, values in groups.items() if len(values) > 1}
