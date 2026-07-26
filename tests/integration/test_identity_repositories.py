from pathlib import Path

import duckdb

from evombl.domain.persistence import (
    MutationObservationRecord,
    NumberingMappingRecord,
    ProteinSequenceRecord,
    ProteinStructureRecord,
    SourceIdentifierRecord,
    StructureChainRecord,
    VariantAccessionRecord,
    VariantSourceLinkRecord,
)
from evombl.storage.database import migrate
from evombl.storage.evidence_graph import insert_evidence_graph
from evombl.storage.repositories import (
    MutationObservationRepository,
    NumberingMappingRepository,
    ProteinSequenceRepository,
    ProteinStructureRepository,
    SourceIdentifierRepository,
    StructureChainRepository,
    VariantAccessionRepository,
    VariantSourceLinkRepository,
)

from .test_persistence_graph import synthetic_graph


def test_batch2c_identity_repositories_are_typed_and_idempotent(tmp_path: Path) -> None:
    path = tmp_path / "SYNTHETIC_TEST_DATA-identities.duckdb"
    migrate(path)
    graph = synthetic_graph()
    with duckdb.connect(str(path)) as connection:
        insert_evidence_graph(connection, graph)
        records = [
            (
                SourceIdentifierRepository(),
                SourceIdentifierRecord(
                    identifier_id="SYNTHETIC_TEST_DATA-ID",
                    source_id=graph.source.source_id,
                    scheme="synthetic",
                    value="SYNTHETIC_TEST_DATA",
                ),
                "SYNTHETIC_TEST_DATA-ID",
            ),
            (
                ProteinSequenceRepository(),
                ProteinSequenceRecord(
                    sequence_id="SYNTHETIC_TEST_DATA-SEQ",
                    variant_id=graph.variant.internal_variant_id,
                    source_id=graph.source.source_id,
                    sequence_kind="mature",
                    sequence_hash=graph.variant.sequence_hash,
                    sequence="ACDE",
                ),
                "SYNTHETIC_TEST_DATA-SEQ",
            ),
            (
                VariantAccessionRepository(),
                VariantAccessionRecord(
                    accession_id="SYNTHETIC_TEST_DATA-ACC",
                    variant_id=graph.variant.internal_variant_id,
                    accession="SYNTHETIC_TEST_DATA",
                    accession_type="protein",
                    source_database="synthetic",
                    verification_status="unverified",
                ),
                "SYNTHETIC_TEST_DATA-ACC",
            ),
            (
                VariantSourceLinkRepository(),
                VariantSourceLinkRecord(
                    variant_id=graph.variant.internal_variant_id, source_id=graph.source.source_id
                ),
                f"{graph.variant.internal_variant_id}|{graph.source.source_id}",
            ),
            (
                MutationObservationRepository(),
                MutationObservationRecord(
                    observation_id="SYNTHETIC_TEST_DATA-MUT",
                    variant_id=graph.variant.internal_variant_id,
                    reference_sequence_hash=graph.variant.sequence_hash,
                    author_mutation="SYNTHETIC_TEST_DATA",
                    author_numbering="synthetic",
                    verification_status="unverified",
                ),
                "SYNTHETIC_TEST_DATA-MUT",
            ),
            (
                NumberingMappingRepository(),
                NumberingMappingRecord(
                    mapping_id="SYNTHETIC_TEST_DATA-MAP",
                    observation_id="SYNTHETIC_TEST_DATA-MUT",
                    method="SYNTHETIC_TEST_DATA",
                ),
                "SYNTHETIC_TEST_DATA-MAP",
            ),
            (
                ProteinStructureRepository(),
                ProteinStructureRecord(
                    structure_id="SYNTHETIC_TEST_DATA-STR",
                    variant_id=graph.variant.internal_variant_id,
                    source_id=graph.source.source_id,
                    database_id="SYNTHETIC_TEST_DATA",
                    verification_status="unverified",
                ),
                "SYNTHETIC_TEST_DATA-STR",
            ),
            (
                StructureChainRepository(),
                StructureChainRecord(
                    chain_id="SYNTHETIC_TEST_DATA-CHAIN",
                    structure_id="SYNTHETIC_TEST_DATA-STR",
                    chain_label="SYNTHETIC_TEST_DATA",
                ),
                "SYNTHETIC_TEST_DATA-CHAIN",
            ),
        ]
        for repository, record, identifier in records:
            first_insert = repository.insert(connection, record)
            if not isinstance(repository, VariantSourceLinkRepository):
                assert first_insert
            assert not repository.insert(connection, record)
            assert repository.exists(connection, identifier)
            assert repository.get(connection, identifier) == record
            assert record in repository.list(connection)
