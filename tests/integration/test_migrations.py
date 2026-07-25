from pathlib import Path

import duckdb

from evombl.storage.database import migrate, schema_version


def test_migrations_are_ordered_and_idempotent(tmp_path: Path) -> None:
    path = tmp_path / "SYNTHETIC_TEST_DATA-migrations.duckdb"
    assert migrate(path) == 2
    assert migrate(path) == 2
    assert schema_version(path) == 2
    with duckdb.connect(str(path)) as connection:
        views = {
            row[0]
            for row in connection.execute(
                "SELECT view_name FROM duckdb_views() WHERE internal=false"
            ).fetchall()
        }
    assert "biochemical_measurement_matrix" in views
    assert "source_provenance_chain" in views
