import builtins
import hashlib
import json

import duckdb
from pydantic import BaseModel

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
    SourceRetrievalEventRecord,
    SourceRevisionRecord,
)
from evombl.domain.sources import SourceLocationRecord


class RecordNotFoundError(LookupError):
    pass


class ConflictingRecordError(ValueError):
    pass


def stable_json(record: BaseModel) -> str:
    return json.dumps(
        record.model_dump(mode="json"), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )


def stable_hash(record: BaseModel) -> str:
    return hashlib.sha256(stable_json(record).encode()).hexdigest()


class JsonRepository[T: BaseModel]:
    select_sql: str
    list_sql: str
    insert_sql: str
    model: type[T]

    def get(self, connection: duckdb.DuckDBPyConnection, identifier: str) -> T:
        row = connection.execute(self.select_sql, [identifier]).fetchone()
        if row is None:
            raise RecordNotFoundError(identifier)
        return self.model.model_validate_json(row[0])

    def insert(self, connection: duckdb.DuckDBPyConnection, record: T) -> bool:
        identifier = self.identifier(record)
        try:
            existing = self.get(connection, identifier)
        except RecordNotFoundError:
            existing = None
        if existing is not None:
            if stable_hash(existing) == stable_hash(record):
                return False
            raise ConflictingRecordError(f"changed immutable record: {identifier}")
        connection.execute(self.insert_sql, self.values(record))
        return True

    def exists(self, connection: duckdb.DuckDBPyConnection, identifier: str) -> bool:
        try:
            self.get(connection, identifier)
            return True
        except RecordNotFoundError:
            return False

    def list(self, connection: duckdb.DuckDBPyConnection) -> builtins.list[T]:
        return [
            self.model.model_validate_json(row[0])
            for row in connection.execute(self.list_sql).fetchall()
        ]

    def identifier(self, record: T) -> str:
        raise NotImplementedError

    def values(self, record: T) -> builtins.list[object]:
        raise NotImplementedError


class EvidenceSourceRepository(JsonRepository[EvidenceSourceRecord]):
    model = EvidenceSourceRecord
    select_sql = "SELECT record_json FROM evidence_sources WHERE source_id=?"
    list_sql = "SELECT record_json FROM evidence_sources ORDER BY source_id"
    insert_sql = "INSERT INTO evidence_sources(source_id,source_type,record_json) VALUES (?,?,?)"

    def identifier(self, r: EvidenceSourceRecord) -> str:
        return r.source_id

    def values(self, r: EvidenceSourceRecord) -> list[object]:
        return [r.source_id, r.source_type.value, stable_json(r)]


class CompoundRepository(JsonRepository[CompoundRecord]):
    model = CompoundRecord
    select_sql = "SELECT record_json FROM compounds WHERE internal_compound_id=?"
    list_sql = "SELECT record_json FROM compounds ORDER BY internal_compound_id"
    insert_sql = "INSERT INTO compounds(internal_compound_id,source_record_id,original_smiles,record_json) VALUES (?,?,?,?)"

    def identifier(self, r: CompoundRecord) -> str:
        return r.internal_compound_id

    def values(self, r: CompoundRecord) -> list[object]:
        return [r.internal_compound_id, r.source_record_id, r.original_smiles, stable_json(r)]


class ProteinVariantRepository(JsonRepository[ProteinVariantRecord]):
    model = ProteinVariantRecord
    select_sql = "SELECT record_json FROM protein_variants WHERE internal_variant_id=?"
    list_sql = "SELECT record_json FROM protein_variants ORDER BY internal_variant_id"
    insert_sql = "INSERT INTO protein_variants(internal_variant_id,variant_name,sequence_hash,record_json) VALUES (?,?,?,?)"

    def identifier(self, r: ProteinVariantRecord) -> str:
        return r.internal_variant_id

    def values(self, r: ProteinVariantRecord) -> list[object]:
        return [r.internal_variant_id, r.variant_name, r.sequence_hash, stable_json(r)]


class AssayRepository(JsonRepository[AssayRecord]):
    model = AssayRecord
    select_sql = "SELECT record_json FROM assays WHERE internal_assay_id=?"
    list_sql = "SELECT record_json FROM assays ORDER BY internal_assay_id"
    insert_sql = "INSERT INTO assays(internal_assay_id,source_id,enzyme_variant_id,endpoint_type,record_json) VALUES (?,?,?,?,?)"

    def identifier(self, r: AssayRecord) -> str:
        return r.internal_assay_id

    def values(self, r: AssayRecord) -> list[object]:
        return [
            r.internal_assay_id,
            r.source_id,
            r.enzyme_variant_id,
            r.endpoint_type.value,
            stable_json(r),
        ]


class MeasurementRepository(JsonRepository[MeasurementRecord]):
    model = MeasurementRecord
    select_sql = "SELECT record_json FROM measurements WHERE internal_measurement_id=?"
    list_sql = "SELECT record_json FROM measurements ORDER BY internal_measurement_id"
    insert_sql = "INSERT INTO measurements(internal_measurement_id,compound_id,assay_id,evidence_source_id,endpoint_type,original_value,original_units,relation,exclusion_status,record_json,source_location_id,record_hash) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)"

    def identifier(self, r: MeasurementRecord) -> str:
        return r.internal_measurement_id

    def values(self, r: MeasurementRecord) -> list[object]:
        return [
            r.internal_measurement_id,
            r.compound_id,
            r.assay_id,
            r.evidence_source_id,
            r.endpoint_type.value,
            r.original_value,
            r.original_units,
            r.relation.value,
            r.exclusion_status.value,
            stable_json(r),
            r.source_location_id,
            stable_hash(r),
        ]


class SourceDocumentRepository:
    def insert(self, c: duckdb.DuckDBPyConnection, r: SourceDocumentRecord) -> bool:
        row = c.execute(
            "SELECT record_hash FROM source_documents WHERE document_id=?", [r.document_id]
        ).fetchone()
        if row:
            if row[0] == r.record_hash:
                return False
            raise ConflictingRecordError(r.document_id)
        c.execute(
            "INSERT INTO source_documents(document_id,source_id,document_type,record_hash) VALUES (?,?,?,?)",
            [r.document_id, r.source_id, r.document_type, r.record_hash],
        )
        return True


class SourceFileRepository:
    def insert(self, c: duckdb.DuckDBPyConnection, r: SourceFileRecord) -> bool:
        row = c.execute("SELECT sha256 FROM source_files WHERE file_id=?", [r.file_id]).fetchone()
        if row:
            if row[0] == r.sha256:
                return False
            raise ConflictingRecordError(r.file_id)
        c.execute(
            "INSERT INTO source_files(file_id,document_id,path,sha256,immutable) VALUES (?,?,?,?,?)",
            [r.file_id, r.document_id, str(r.path), r.sha256, r.immutable],
        )
        return True


class SourceLocationRepository:
    def insert(self, c: duckdb.DuckDBPyConnection, r: SourceLocationRecord) -> bool:
        payload = stable_json(r)
        row = c.execute(
            "SELECT record_json FROM source_locations WHERE location_id=?", [r.location_id]
        ).fetchone()
        if row:
            if json.loads(row[0]) == json.loads(payload):
                return False
            raise ConflictingRecordError(r.location_id)
        c.execute(
            "INSERT INTO source_locations(location_id,source_id,location_type,page,section,object_label,record_json) VALUES (?,?,?,?,?,?,?)",
            [
                r.location_id,
                r.source_id,
                r.location_type,
                r.page,
                r.section,
                r.object_label,
                payload,
            ],
        )
        return True


class ProtocolRepository:
    def insert(self, c: duckdb.DuckDBPyConnection, r: ProtocolRecord) -> bool:
        payload = stable_json(r)
        row = c.execute(
            "SELECT record_json FROM protocols WHERE protocol_id=?", [r.protocol_id]
        ).fetchone()
        if row:
            if json.loads(row[0]) == json.loads(payload):
                return False
            raise ConflictingRecordError(r.protocol_id)
        c.execute(
            "INSERT INTO protocols(protocol_id,source_id,record_json) VALUES (?,?,?)",
            [r.protocol_id, r.source_id, payload],
        )
        return True


class CurationEventRepository:
    def insert(self, c: duckdb.DuckDBPyConnection, r: CurationEventRecord) -> bool:
        try:
            c.execute(
                "INSERT INTO curation_events(event_id,entity_type,entity_id,event_type,occurred_at,actor,details_json) VALUES (?,?,?,?,?,?,?)",
                [
                    r.event_id,
                    r.entity_type,
                    r.entity_id,
                    r.event_type,
                    r.occurred_at,
                    r.actor,
                    json.dumps(r.details, sort_keys=True),
                ],
            )
            return True
        except duckdb.ConstraintException:
            raise ConflictingRecordError(r.event_id) from None


class SourceRetrievalEventRepository:
    def insert(self, c: duckdb.DuckDBPyConnection, r: SourceRetrievalEventRecord) -> bool:
        if self.exists(c, r.retrieval_id):
            if self.get(c, r.retrieval_id) == r:
                return False
            raise ConflictingRecordError(r.retrieval_id)
        c.execute(
            "INSERT INTO source_retrieval_events(retrieval_id,source_id,provider,accessed_at,outcome,response_hash,response_path,error_type,error_message) VALUES (?,?,?,?,?,?,?,?,?)",
            [
                r.retrieval_id,
                r.source_id,
                r.provider,
                r.accessed_at,
                r.outcome,
                r.response_hash,
                str(r.response_path) if r.response_path else None,
                r.error_type,
                r.error_message,
            ],
        )
        return True

    def get(self, c: duckdb.DuckDBPyConnection, identifier: str) -> SourceRetrievalEventRecord:
        row = c.execute(
            "SELECT retrieval_id,source_id,provider,accessed_at,outcome,response_hash,response_path,error_type,error_message FROM source_retrieval_events WHERE retrieval_id=?",
            [identifier],
        ).fetchone()
        if row is None:
            raise RecordNotFoundError(identifier)
        return SourceRetrievalEventRecord.model_validate(
            dict(zip(SourceRetrievalEventRecord.model_fields, row, strict=True))
        )

    def exists(self, c: duckdb.DuckDBPyConnection, identifier: str) -> bool:
        return (
            c.execute(
                "SELECT 1 FROM source_retrieval_events WHERE retrieval_id=?", [identifier]
            ).fetchone()
            is not None
        )

    def list(self, c: duckdb.DuckDBPyConnection) -> list[SourceRetrievalEventRecord]:
        return [
            self.get(c, row[0])
            for row in c.execute(
                "SELECT retrieval_id FROM source_retrieval_events ORDER BY accessed_at,retrieval_id"
            ).fetchall()
        ]


class SourceRevisionRepository:
    def insert(self, c: duckdb.DuckDBPyConnection, r: SourceRevisionRecord) -> bool:
        if self.exists(c, r.revision_id):
            if self.get(c, r.revision_id) == r:
                return False
            raise ConflictingRecordError(r.revision_id)
        c.execute(
            "INSERT INTO source_revisions(revision_id,source_id,predecessor_revision_id,previous_content_hash,new_content_hash,revision_reason,detected_at,actor,retrieval_event_id,verification_status,notes) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            list(r.model_dump(mode="python").values()),
        )
        return True

    def get(self, c: duckdb.DuckDBPyConnection, identifier: str) -> SourceRevisionRecord:
        row = c.execute(
            "SELECT revision_id,source_id,predecessor_revision_id,previous_content_hash,new_content_hash,revision_reason,detected_at,actor,retrieval_event_id,verification_status,notes FROM source_revisions WHERE revision_id=?",
            [identifier],
        ).fetchone()
        if row is None:
            raise RecordNotFoundError(identifier)
        return SourceRevisionRecord.model_validate(
            dict(zip(SourceRevisionRecord.model_fields, row, strict=True))
        )

    def exists(self, c: duckdb.DuckDBPyConnection, identifier: str) -> bool:
        return (
            c.execute("SELECT 1 FROM source_revisions WHERE revision_id=?", [identifier]).fetchone()
            is not None
        )

    def list(self, c: duckdb.DuckDBPyConnection) -> list[SourceRevisionRecord]:
        return [
            self.get(c, row[0])
            for row in c.execute(
                "SELECT revision_id FROM source_revisions ORDER BY detected_at,revision_id"
            ).fetchall()
        ]
