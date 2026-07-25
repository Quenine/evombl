import pytest

from evombl.domain.compounds import CompoundRecord
from evombl.domain.sources import EvidenceSourceRecord, SourceLocationRecord
from evombl.proteins.sequences import sequence_hash
from evombl.units import convert, reverse


def test_mutable_defaults_are_isolated() -> None:
    common = dict(
        original_smiles="C", source_record_id="SYNTHETIC_TEST_DATA-S", curation_status="new"
    )
    first = CompoundRecord(internal_compound_id="SYNTHETIC_TEST_DATA-C1", **common)
    second = CompoundRecord(internal_compound_id="SYNTHETIC_TEST_DATA-C2", **common)
    first.source_compound_ids["x"] = "y"
    assert second.source_compound_ids == {}
    source1 = EvidenceSourceRecord(source_id="SYNTHETIC_TEST_DATA-S1", source_type="other")
    source2 = EvidenceSourceRecord(source_id="SYNTHETIC_TEST_DATA-S2", source_type="other")
    source1.authors.append("SYNTHETIC_TEST_DATA")
    assert source2.authors == []


def test_unit_aliases_and_reversibility() -> None:
    result = convert(1, "uM", "nM")
    assert result.standard_value == pytest.approx(1000)
    assert reverse(result) == pytest.approx(1)
    with pytest.raises(ValueError, match="incompatible"):
        convert(1, "mg/L", "uM")


def test_location_id_is_deterministic() -> None:
    location = SourceLocationRecord(
        source_id="SYNTHETIC_TEST_DATA-S", location_type="table", object_label="1"
    )
    assert location.location_id == location.model_copy().location_id


def test_hash_utility() -> None:
    assert len(sequence_hash("ACDE")) == 64
