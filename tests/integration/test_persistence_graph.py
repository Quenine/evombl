from datetime import date, datetime
from pathlib import Path

import duckdb
import pytest

from evombl.domain import (
    AssayRecord,
    CompoundRecord,
    EvidenceSourceRecord,
    MeasurementRecord,
    ProteinVariantRecord,
)
from evombl.domain.persistence import (
    CurationEventRecord,
    ProtocolRecord,
    SourceDocumentRecord,
    SourceFileRecord,
)
from evombl.domain.sources import SourceLocationRecord
from evombl.proteins.sequences import sequence_hash
from evombl.storage.database import migrate
from evombl.storage.evidence_graph import EvidenceGraph, insert_evidence_graph
from evombl.storage.repositories import ConflictingRecordError, EvidenceSourceRepository


def synthetic_graph() -> EvidenceGraph:
    source = EvidenceSourceRecord(source_id="SYNTHETIC_TEST_DATA-S", source_type="other")
    location = SourceLocationRecord(
        source_id=source.source_id, location_type="table", object_label="SYNTHETIC_TEST_DATA-T1"
    )
    variant = ProteinVariantRecord(
        internal_variant_id="SYNTHETIC_TEST_DATA-V",
        family="OTHER",
        variant_name="SYNTHETIC_TEST_DATA-V",
        raw_sequence="ACDE",
        numbering_scheme="SYNTHETIC_TEST_DATA",
        sequence_hash=sequence_hash("ACDE"),
        evidence_source_ids=[source.source_id],
        verification_status="unverified",
    )
    assay = AssayRecord(
        internal_assay_id="SYNTHETIC_TEST_DATA-A",
        assay_category="BIOCHEMICAL",
        assay_format="SYNTHETIC_TEST_DATA",
        endpoint_type="IC50",
        enzyme_variant_id=variant.internal_variant_id,
        source_id=source.source_id,
        source_location="SYNTHETIC_TEST_DATA",
        assay_comparability_group="SYNTHETIC_TEST_DATA",
        curation_confidence="low",
    )
    measurement = MeasurementRecord(
        internal_measurement_id="SYNTHETIC_TEST_DATA-M",
        compound_id="SYNTHETIC_TEST_DATA-C",
        assay_id=assay.internal_assay_id,
        endpoint_type="IC50",
        original_value=1,
        original_units="uM",
        evidence_source_id=source.source_id,
        evidence_location="deprecated synthetic",
        source_location_id=location.location_id,
        extraction_method="manual",
        curator="SYNTHETIC_TEST_DATA",
        extraction_date=date(2026, 1, 1),
        verification_status="unverified",
    )
    return EvidenceGraph(
        source,
        SourceDocumentRecord(
            document_id="SYNTHETIC_TEST_DATA-D",
            source_id=source.source_id,
            document_type="synthetic",
            record_hash="0" * 64,
        ),
        SourceFileRecord(
            file_id="SYNTHETIC_TEST_DATA-F",
            document_id="SYNTHETIC_TEST_DATA-D",
            path=Path("SYNTHETIC_TEST_DATA.json"),
            sha256="1" * 64,
        ),
        location,
        CompoundRecord(
            internal_compound_id="SYNTHETIC_TEST_DATA-C",
            original_smiles="C",
            source_record_id=source.source_id,
            curation_status="synthetic",
        ),
        variant,
        ProtocolRecord(
            protocol_id="SYNTHETIC_TEST_DATA-P",
            source_id=source.source_id,
            description="SYNTHETIC_TEST_DATA",
        ),
        assay,
        measurement,
        CurationEventRecord(
            event_id="SYNTHETIC_TEST_DATA-E",
            entity_type="graph",
            entity_id="SYNTHETIC_TEST_DATA-M",
            event_type="create",
            occurred_at=datetime(2026, 1, 1),
            actor="SYNTHETIC_TEST_DATA",
            details={"rule": "synthetic"},
        ),
    )


def test_complete_graph_and_rollback(tmp_path: Path) -> None:
    path = tmp_path / "SYNTHETIC_TEST_DATA.duckdb"
    migrate(path)
    with duckdb.connect(str(path)) as connection:
        graph = synthetic_graph()
        insert_evidence_graph(connection, graph)
        assert connection.execute(
            "SELECT count(*) FROM biochemical_measurement_matrix"
        ).fetchone() == (1,)
    bad = synthetic_graph().model_copy() if False else synthetic_graph()
    bad = EvidenceGraph(
        **{
            **bad.__dict__,
            "measurement": bad.measurement.model_copy(update={"endpoint_type": "Ki"}),
            "event": bad.event.model_copy(update={"event_id": "SYNTHETIC_TEST_DATA-E2"}),
        }
    )
    with duckdb.connect(str(path)) as connection:
        before = connection.execute("SELECT count(*) FROM curation_events").fetchone()
        with pytest.raises(ValueError):
            insert_evidence_graph(connection, bad)
        assert connection.execute("SELECT count(*) FROM curation_events").fetchone() == before


def test_repository_idempotency_and_conflict(tmp_path: Path) -> None:
    path = tmp_path / "SYNTHETIC_TEST_DATA-repo.duckdb"
    migrate(path)
    with duckdb.connect(str(path)) as connection:
        repo = EvidenceSourceRepository()
        record = synthetic_graph().source
        assert repo.insert(connection, record)
        assert not repo.insert(connection, record)
        with pytest.raises(ConflictingRecordError):
            repo.insert(connection, record.model_copy(update={"notes": "changed"}))
