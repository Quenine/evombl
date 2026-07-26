import json
from datetime import UTC, datetime
from pathlib import Path

import duckdb

from evombl.domain.bibliographic import MetadataCandidateRecord
from evombl.storage.database import _migrations, initialize_database, migrate, schema_version
from evombl.storage.repositories import stable_hash, stable_json


def test_migrations_are_ordered_and_idempotent(tmp_path: Path) -> None:
    path = tmp_path / "SYNTHETIC_TEST_DATA-migrations.duckdb"
    assert migrate(path) == 7
    assert migrate(path) == 7
    assert schema_version(path) == 7
    with duckdb.connect(str(path)) as connection:
        views = {
            row[0]
            for row in connection.execute(
                "SELECT view_name FROM duckdb_views() WHERE internal=false"
            ).fetchall()
        }
    assert "biochemical_measurement_matrix" in views
    assert "source_provenance_chain" in views


def test_candidate_version_migration_preserves_existing_candidate(tmp_path: Path) -> None:
    path = tmp_path / "SYNTHETIC_TEST_DATA-preservation.duckdb"
    initialize_database(path)
    with duckdb.connect(str(path)) as connection:
        for version, name, checksum, sql in _migrations()[:6]:
            connection.execute(sql)
            connection.execute(
                "INSERT INTO schema_migrations(version,name,checksum) VALUES (?,?,?)",
                [version, name, checksum],
            )
        connection.execute(
            "INSERT INTO evidence_sources VALUES (?,?,?)",
            ["SYNTHETIC_TEST_DATA-SOURCE", "other", json.dumps({"synthetic": True})],
        )
        now = datetime(2026, 1, 1, tzinfo=UTC)
        connection.execute(
            "INSERT INTO source_retrieval_events VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [
                "SYNTHETIC_TEST_DATA-EVENT",
                "SYNTHETIC_TEST_DATA-SOURCE",
                "ncbi_pubmed",
                "SYNTHETIC_TEST_DATA-PMID",
                now,
                now,
                "success_new_capture",
                200,
                1,
                "a" * 64,
                "SYNTHETIC_TEST_DATA.json",
                None,
                None,
                False,
                "SYNTHETIC_TEST_DATA",
                "SYNTHETIC_TEST_DATA",
            ],
        )
        record = MetadataCandidateRecord(
            candidate_id="SYNTHETIC_TEST_DATA-CANDIDATE",
            seed_id="SYNTHETIC_TEST_DATA-SEED",
            source_id="SYNTHETIC_TEST_DATA-SOURCE",
            provider="ncbi_pubmed",
            pmid="SYNTHETIC_TEST_DATA-PMID",
            response_hash="a" * 64,
            retrieval_event_id="SYNTHETIC_TEST_DATA-EVENT",
        )
        connection.execute(
            "INSERT INTO metadata_candidates VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [
                record.candidate_id,
                record.seed_id,
                record.source_id,
                record.provider,
                record.doi,
                record.pmid,
                record.pmcid,
                record.title,
                record.publication_year,
                record.response_hash,
                record.retrieval_event_id,
                stable_json(record),
                stable_hash(record),
            ],
        )
    assert migrate(path) == 7
    with duckdb.connect(str(path), read_only=True) as connection:
        row = connection.execute(
            "SELECT candidate_id,logical_candidate_key,requested_identifier,"
            "normalization_version,normalized_record_hash,semantic_bibliographic_hash,"
            "candidate_status FROM metadata_candidates"
        ).fetchone()
    assert row is not None
    assert row[0] == "SYNTHETIC_TEST_DATA-CANDIDATE"
    assert row[1:4] == (
        "SYNTHETIC_TEST_DATA-SOURCE|ncbi_pubmed|SYNTHETIC_TEST_DATA-PMID",
        "SYNTHETIC_TEST_DATA-PMID",
        "ncbi-pubmed-esummary-json-v1",
    )
    assert row[4] and row[5] and row[6] == "legacy_preserved"
