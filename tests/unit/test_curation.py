from evombl.curation.conflicts import find_conflicts
from evombl.curation.deduplication import group_duplicates

from .test_measurements import measurement


def test_duplicate_grouping_and_conflict_reporting() -> None:
    first = measurement(internal_measurement_id="SYNTHETIC_TEST_DATA-M1")
    second = measurement(internal_measurement_id="SYNTHETIC_TEST_DATA-M2", original_value=20.0)
    groups = group_duplicates([first, second])
    assert len(groups) == 1
    conflicts = find_conflicts([first, second])
    assert conflicts[0].measurement_ids == (
        "SYNTHETIC_TEST_DATA-M1",
        "SYNTHETIC_TEST_DATA-M2",
    )
