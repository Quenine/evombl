from pathlib import Path

import duckdb
import pytest

from evombl.storage.database import migrate, schema_version


def test_checksum_mismatch_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "SYNTHETIC_TEST_DATA-checksum.duckdb"
    migrate(path)
    with duckdb.connect(str(path)) as connection:
        connection.execute(
            "UPDATE schema_migrations SET checksum='SYNTHETIC_TEST_DATA-BAD' WHERE version=2"
        )
    with pytest.raises(RuntimeError, match="checksum mismatch"):
        migrate(path)
    assert schema_version(path) == 4


def test_measurement_location_foreign_key_exists(tmp_path: Path) -> None:
    path = tmp_path / "SYNTHETIC_TEST_DATA-fk.duckdb"
    migrate(path)
    with duckdb.connect(str(path)) as connection:
        foreign_keys = connection.execute(
            "SELECT sql FROM duckdb_tables() WHERE table_name='measurements'"
        ).fetchone()
        assert foreign_keys is not None and "source_locations" in foreign_keys[0]


def test_immediate_views_have_exact_empty_columns(tmp_path: Path) -> None:
    path = tmp_path / "SYNTHETIC_TEST_DATA-views.duckdb"
    migrate(path)
    expected = {
        "current_verified_sources": ["source_id", "source_type", "record_json"],
        "current_verified_variants": [
            "internal_variant_id",
            "variant_name",
            "sequence_hash",
            "record_json",
        ],
        "unresolved_identity_conflicts": [
            "accession_id",
            "variant_id",
            "accession",
            "accession_type",
            "source_database",
            "verification_status",
        ],
        "source_provenance_chain": [
            "source_id",
            "scheme",
            "value",
            "provider",
            "accessed_at",
            "response_hash",
            "revision_id",
            "previous_content_hash",
            "new_content_hash",
        ],
    }
    with duckdb.connect(str(path)) as connection:
        for view, columns in expected.items():
            result = connection.execute(f"SELECT * FROM {view} ORDER BY ALL")
            assert [item[0] for item in result.description] == columns
            assert result.fetchall() == []
