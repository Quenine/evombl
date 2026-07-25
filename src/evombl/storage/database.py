from importlib.resources import files
from pathlib import Path

import duckdb

TABLES = (
    "evidence_sources",
    "compounds",
    "protein_variants",
    "assays",
    "measurements",
    "experimental_batches",
    "curation_events",
    "data_releases",
)


def initialize_database(path: Path) -> None:
    schema = files("evombl.storage").joinpath("schema.sql").read_text(encoding="utf-8")
    with duckdb.connect(str(path)) as connection:
        connection.execute(schema)


def migrate(path: Path) -> int:
    migration_root = files("evombl.storage.migrations")
    with duckdb.connect(str(path)) as connection:
        existing = {row[0] for row in connection.execute("SHOW TABLES").fetchall()}
        if "evidence_sources" not in existing:
            connection.execute(files("evombl.storage").joinpath("schema.sql").read_text())
        if "schema_migrations" not in existing:
            connection.execute(migration_root.joinpath("001_batch1.sql").read_text())
            connection.execute("INSERT INTO schema_migrations(version,name) VALUES (1,'batch1')")
        applied = {
            row[0] for row in connection.execute("SELECT version FROM schema_migrations").fetchall()
        }
        if 2 not in applied:
            connection.execute("BEGIN")
            try:
                connection.execute(
                    migration_root.joinpath("002_evidence_foundation.sql").read_text()
                )
                connection.execute(
                    "INSERT INTO schema_migrations(version,name) VALUES (2,'evidence_foundation')"
                )
                connection.execute("COMMIT")
            except Exception:
                connection.execute("ROLLBACK")
                raise
        row = connection.execute("SELECT max(version) FROM schema_migrations").fetchone()
        if row is None:
            raise RuntimeError("schema migration version is unavailable")
        return int(row[0])


def schema_version(path: Path) -> int:
    with duckdb.connect(str(path), read_only=True) as connection:
        row = connection.execute("SELECT max(version) FROM schema_migrations").fetchone()
        if row is None:
            raise RuntimeError("schema migration version is unavailable")
        return int(row[0])


def verify_integrity(path: Path) -> list[str]:
    errors: list[str] = []
    with duckdb.connect(str(path), read_only=True) as connection:
        existing = {row[0] for row in connection.execute("SHOW TABLES").fetchall()}
        errors.extend(f"missing table: {name}" for name in TABLES if name not in existing)
        if "measurements" in existing and "assays" in existing:
            mismatches = connection.execute(
                """SELECT m.internal_measurement_id FROM measurements m
                   JOIN assays a ON a.internal_assay_id = m.assay_id
                   WHERE m.endpoint_type <> a.endpoint_type"""
            ).fetchall()
            errors.extend(f"endpoint mismatch: {row[0]}" for row in mismatches)
    return errors
