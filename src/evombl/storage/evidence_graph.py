from dataclasses import dataclass

import duckdb

from evombl.curation.validators import validate_endpoint_alignment
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

from .repositories import (
    AssayRepository,
    CompoundRepository,
    CurationEventRepository,
    EvidenceSourceRepository,
    MeasurementRepository,
    ProteinVariantRepository,
    ProtocolRepository,
    SourceDocumentRepository,
    SourceFileRepository,
    SourceLocationRepository,
)


@dataclass(frozen=True)
class EvidenceGraph:
    source: EvidenceSourceRecord
    document: SourceDocumentRecord
    source_file: SourceFileRecord
    location: SourceLocationRecord
    compound: CompoundRecord
    variant: ProteinVariantRecord
    protocol: ProtocolRecord
    assay: AssayRecord
    measurement: MeasurementRecord
    event: CurationEventRecord


def insert_evidence_graph(connection: duckdb.DuckDBPyConnection, graph: EvidenceGraph) -> None:
    validate_endpoint_alignment(graph.assay, graph.measurement)
    if graph.measurement.source_location_id != graph.location.location_id:
        raise ValueError("measurement must resolve to the graph source location")
    if (
        graph.assay.source_id != graph.source.source_id
        or graph.measurement.evidence_source_id != graph.source.source_id
    ):
        raise ValueError("graph source provenance is inconsistent")
    if graph.source.source_id not in graph.variant.evidence_source_ids:
        raise ValueError("variant sequence must resolve to its evidence source")
    connection.execute("BEGIN")
    try:
        EvidenceSourceRepository().insert(connection, graph.source)
        SourceDocumentRepository().insert(connection, graph.document)
        SourceFileRepository().insert(connection, graph.source_file)
        SourceLocationRepository().insert(connection, graph.location)
        CompoundRepository().insert(connection, graph.compound)
        ProteinVariantRepository().insert(connection, graph.variant)
        connection.execute(
            "INSERT INTO compound_source_links(compound_id,source_id) VALUES (?,?)",
            [graph.compound.internal_compound_id, graph.source.source_id],
        )
        connection.execute(
            "INSERT INTO variant_source_links(variant_id,source_id) VALUES (?,?)",
            [graph.variant.internal_variant_id, graph.source.source_id],
        )
        connection.execute(
            "INSERT INTO protein_sequences(sequence_id,variant_id,source_id,sequence_kind,sequence_hash,sequence) VALUES (?,?,?,?,?,?)",
            [
                f"{graph.variant.internal_variant_id}:raw",
                graph.variant.internal_variant_id,
                graph.source.source_id,
                "raw",
                graph.variant.sequence_hash,
                graph.variant.normalized_sequence,
            ],
        )
        ProtocolRepository().insert(connection, graph.protocol)
        AssayRepository().insert(connection, graph.assay)
        MeasurementRepository().insert(connection, graph.measurement)
        CurationEventRepository().insert(connection, graph.event)
        connection.execute("COMMIT")
    except Exception:
        connection.execute("ROLLBACK")
        raise
