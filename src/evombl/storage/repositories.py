import json
from typing import Any

import duckdb
from pydantic import BaseModel


def insert_json_record(
    connection: duckdb.DuckDBPyConnection,
    table: str,
    identifier_column: str,
    identifier: str,
    record: BaseModel,
) -> None:
    allowed = {"evidence_sources", "experimental_batches", "curation_events", "data_releases"}
    if table not in allowed:
        raise ValueError("table requires a typed repository")
    payload: dict[str, Any] = record.model_dump(mode="json")
    connection.execute(
        f"INSERT INTO {table} ({identifier_column}, record_json) VALUES (?, ?)",
        [identifier, json.dumps(payload, sort_keys=True)],
    )
