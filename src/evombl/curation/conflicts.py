from dataclasses import dataclass

from evombl.domain.measurements import MeasurementRecord

from .deduplication import group_duplicates


@dataclass(frozen=True)
class MeasurementConflict:
    duplicate_key: str
    measurement_ids: tuple[str, ...]
    reported_values: tuple[tuple[str, float, str], ...]


def find_conflicts(records: list[MeasurementRecord]) -> list[MeasurementConflict]:
    conflicts = []
    for key, group in group_duplicates(records).items():
        values = {(r.relation.value, r.original_value, r.original_units) for r in group}
        if len(values) > 1:
            conflicts.append(
                MeasurementConflict(
                    key,
                    tuple(sorted(r.internal_measurement_id for r in group)),
                    tuple(sorted(values)),
                )
            )
    return conflicts
