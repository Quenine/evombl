import hashlib
import re
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
VIEWS = (
    "current_verified_sources",
    "current_verified_variants",
    "biochemical_measurement_matrix",
    "microbiological_measurement_matrix",
    "unresolved_identity_conflicts",
    "unresolved_measurement_conflicts",
    "excluded_records_audit",
    "source_provenance_chain",
)


def initialize_database(path: Path) -> None:
    with duckdb.connect(str(path)) as connection:
        connection.execute(files("evombl.storage").joinpath("schema.sql").read_text())


def _migrations() -> list[tuple[int, str, str, str]]:
    root = files("evombl.storage.migrations")
    found = []
    for item in root.iterdir():
        match = re.fullmatch(r"(\d{3})_(.+)\.sql", item.name)
        if match:
            sql = item.read_text(encoding="utf-8")
            found.append(
                (int(match.group(1)), match.group(2), hashlib.sha256(sql.encode()).hexdigest(), sql)
            )
    found.sort()
    versions = [m[0] for m in found]
    if versions != list(range(1, len(versions) + 1)):
        raise RuntimeError("missing or out-of-order migration number")
    if len(versions) != len(set(versions)):
        raise RuntimeError("duplicate migration version")
    return found


def migrate(path: Path) -> int:
    migrations = _migrations()
    with duckdb.connect(str(path)) as connection:
        existing = {r[0] for r in connection.execute("SHOW TABLES").fetchall()}
        if "evidence_sources" not in existing:
            connection.execute(files("evombl.storage").joinpath("schema.sql").read_text())
        if "schema_migrations" not in existing:
            version, name, checksum, sql = migrations[0]
            connection.execute(sql)
            connection.execute(
                "INSERT INTO schema_migrations(version,name,checksum) VALUES (?,?,?)",
                [version, name, checksum],
            )
        columns = {
            r[1] for r in connection.execute("PRAGMA table_info('schema_migrations')").fetchall()
        }
        if "checksum" not in columns:
            connection.execute("ALTER TABLE schema_migrations ADD COLUMN checksum VARCHAR")
            for version, _, checksum, _ in migrations:
                connection.execute(
                    "UPDATE schema_migrations SET checksum=? WHERE version=? AND checksum IS NULL",
                    [checksum, version],
                )
        applied = {
            int(r[0]): str(r[1])
            for r in connection.execute("SELECT version,checksum FROM schema_migrations").fetchall()
        }
        known = {m[0]: m[2] for m in migrations}
        for version, checksum in applied.items():
            if version not in known or checksum != known[version]:
                raise RuntimeError(f"migration checksum mismatch: {version}")
        for version, name, checksum, sql in migrations:
            if version in applied:
                continue
            connection.execute("BEGIN")
            try:
                if version == 3:
                    indexes = {
                        r[0]
                        for r in connection.execute(
                            "SELECT index_name FROM duckdb_indexes() WHERE table_name='measurements'"
                        ).fetchall()
                    }
                    if "measurements_matrix_idx" in indexes:
                        connection.execute("DROP INDEX measurements_matrix_idx")
                    retrieval_columns = {
                        r[1]
                        for r in connection.execute(
                            "PRAGMA table_info('source_retrieval_events')"
                        ).fetchall()
                    }
                    if "outcome" not in retrieval_columns:
                        connection.execute(
                            "ALTER TABLE source_retrieval_events ADD COLUMN outcome VARCHAR DEFAULT 'success'"
                        )
                        connection.execute(
                            "ALTER TABLE source_retrieval_events ADD COLUMN error_type VARCHAR"
                        )
                        connection.execute(
                            "ALTER TABLE source_retrieval_events ADD COLUMN error_message VARCHAR"
                        )
                    unresolved = connection.execute(
                        "SELECT count(*) FROM measurements m LEFT JOIN source_locations l ON l.location_id=m.source_location_id WHERE m.source_location_id IS NULL OR l.location_id IS NULL"
                    ).fetchone()
                    if unresolved and unresolved[0]:
                        raise RuntimeError(
                            "measurement source locations must resolve before migration 3"
                        )
                    before_row = connection.execute("SELECT count(*) FROM measurements").fetchone()
                    if before_row is None:
                        raise RuntimeError("measurement count unavailable")
                    before = before_row[0]
                connection.execute(sql)
                if (
                    version == 3
                    and (
                        after_row := connection.execute(
                            "SELECT count(*) FROM measurements"
                        ).fetchone()
                    )
                    is not None
                    and after_row[0] != before
                ):
                    raise RuntimeError("measurement row count changed during migration")
                connection.execute(
                    "INSERT INTO schema_migrations(version,name,checksum) VALUES (?,?,?)",
                    [version, name, checksum],
                )
                connection.execute("COMMIT")
            except Exception:
                connection.execute("ROLLBACK")
                raise
        return max(known)


def schema_version(path: Path) -> int:
    with duckdb.connect(str(path), read_only=True) as c:
        row = c.execute("SELECT max(version) FROM schema_migrations").fetchone()
        if row is None or row[0] is None:
            raise RuntimeError("schema migration version is unavailable")
        return int(row[0])


def verify_integrity(path: Path) -> list[str]:
    errors: list[str] = []
    with duckdb.connect(str(path), read_only=True) as c:
        existing = {r[0] for r in c.execute("SHOW TABLES").fetchall()}
        errors.extend(f"missing table: {n}" for n in TABLES if n not in existing)
        views = {
            r[0]
            for r in c.execute(
                "SELECT view_name FROM duckdb_views() WHERE internal=false"
            ).fetchall()
        }
        if "schema_migrations" in existing:
            errors.extend(f"missing view: {n}" for n in VIEWS if n not in views)
        if "measurements" in existing and "assays" in existing:
            errors.extend(
                f"endpoint mismatch: {r[0]}"
                for r in c.execute(
                    "SELECT m.internal_measurement_id FROM measurements m JOIN assays a ON a.internal_assay_id=m.assay_id WHERE m.endpoint_type<>a.endpoint_type"
                ).fetchall()
            )
    return errors
