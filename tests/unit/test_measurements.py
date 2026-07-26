from datetime import date

import pytest
from pydantic import ValidationError

from evombl.domain.enums import CensoringStatus, EndpointType
from evombl.domain.measurements import MeasurementRecord


def measurement(**changes: object) -> MeasurementRecord:
    values: dict[str, object] = {
        "internal_measurement_id": "SYNTHETIC_TEST_DATA-M1",
        "compound_id": "SYNTHETIC_TEST_DATA-C1",
        "assay_id": "SYNTHETIC_TEST_DATA-A1",
        "endpoint_type": "IC50",
        "original_value": 10.0,
        "original_units": "uM",
        "relation": "=",
        "censoring_status": "none",
        "evidence_source_id": "SYNTHETIC_TEST_DATA-S1",
        "evidence_location": "synthetic row 1",
        "source_location_id": "SYNTHETIC_TEST_DATA-LOC1",
        "extraction_method": "manual",
        "curator": "SYNTHETIC_TEST_DATA",
        "extraction_date": date(2026, 1, 1),
        "verification_status": "unverified",
    }
    values.update(changes)
    return MeasurementRecord.model_validate(values)


def test_valid_censored_measurement() -> None:
    record = measurement(relation=">", censoring_status="right")
    assert record.censoring_status is CensoringStatus.RIGHT


def test_relation_censoring_disagreement_is_invalid() -> None:
    with pytest.raises(ValidationError):
        measurement(relation=">", censoring_status="left")


def test_invalid_relation_and_incompatible_units() -> None:
    with pytest.raises(ValidationError):
        measurement(relation="!=")
    with pytest.raises(ValidationError, match="concentration-compatible"):
        measurement(original_units="%")


def test_endpoints_remain_distinguishable() -> None:
    assert EndpointType.IC50 != EndpointType.KI != EndpointType.MIC
