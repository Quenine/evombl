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
