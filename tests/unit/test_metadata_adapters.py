import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import duckdb
import httpx
import pytest

from evombl.domain.sources import EvidenceSourceRecord
from evombl.ingestion.metadata import CrossrefAdapter
from evombl.storage.database import migrate
from evombl.storage.repositories import EvidenceSourceRepository


def adapter(tmp_path: Path, content: bytes, status: int = 200) -> CrossrefAdapter:
    tmp_path.mkdir(parents=True, exist_ok=True)
    database = tmp_path / "SYNTHETIC_TEST_DATA.duckdb"
    migrate(database)
    connection = duckdb.connect(str(database))
    EvidenceSourceRepository().insert(
        connection, EvidenceSourceRecord(source_id="SYNTHETIC_TEST_DATA-S", source_type="other")
    )
    transport = httpx.MockTransport(
        lambda request: httpx.Response(status, content=content, request=request)
    )
    return CrossrefAdapter(
        tmp_path / "captures",
        "synthetic@example.invalid",
        "SYNTHETIC_TEST_DATA",
        connection=connection,
        source_id="SYNTHETIC_TEST_DATA-S",
        client=httpx.Client(transport=transport),
    )


def test_capture_hash_and_offline_reuse(tmp_path: Path) -> None:
    first = adapter(tmp_path, b'{"message":{"title":"SYNTHETIC_TEST_DATA"}}').fetch(
        "SYNTHETIC_TEST_DATA"
    )
    second = adapter(tmp_path, b"{}").fetch("SYNTHETIC_TEST_DATA", offline=True)
    assert first.response_hash == second.response_hash
    assert first.response_path.name.startswith("sha256-")


def test_malformed_and_http_errors(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="malformed"):
        adapter(tmp_path / "malformed", b"not-json").fetch("SYNTHETIC_TEST_DATA")
    with pytest.raises(httpx.HTTPStatusError):
        adapter(
            tmp_path / "http", json.dumps({"error": "SYNTHETIC_TEST_DATA"}).encode(), 503
        ).fetch("SYNTHETIC_TEST_DATA")


def test_retrieval_events_and_revision_chain(tmp_path: Path) -> None:
    database = tmp_path / "SYNTHETIC_TEST_DATA-chain.duckdb"
    migrate(database)
    connection = duckdb.connect(str(database))
    EvidenceSourceRepository().insert(
        connection, EvidenceSourceRecord(source_id="SYNTHETIC_TEST_DATA-S", source_type="other")
    )
    payloads = iter(
        [
            b'{"v":"SYNTHETIC_TEST_DATA-A"}',
            b'{"v":"SYNTHETIC_TEST_DATA-A"}',
            b'{"v":"SYNTHETIC_TEST_DATA-B"}',
            b'{"v":"SYNTHETIC_TEST_DATA-C"}',
        ]
    )
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, content=next(payloads), request=request)
    )
    moment = [datetime(2026, 1, 1, tzinfo=UTC)]

    def now() -> datetime:
        moment[0] += timedelta(seconds=1)
        return moment[0]

    instance = CrossrefAdapter(
        tmp_path / "captures",
        "synthetic@example.invalid",
        "SYNTHETIC_TEST_DATA",
        connection=connection,
        source_id="SYNTHETIC_TEST_DATA-S",
        client=httpx.Client(transport=transport),
        now=now,
    )
    for _ in range(4):
        instance.fetch("SYNTHETIC_TEST_DATA", refresh=True)
    instance.fetch("SYNTHETIC_TEST_DATA", offline=True)
    outcomes = [
        row[0]
        for row in connection.execute(
            "SELECT outcome FROM source_retrieval_events ORDER BY request_timestamp"
        ).fetchall()
    ]
    assert outcomes == [
        "success_new_capture",
        "success_identical_capture",
        "success_changed_capture",
        "success_changed_capture",
        "offline_cache_hit",
    ]
    revisions = connection.execute(
        "SELECT revision_id,predecessor_revision_id FROM source_revisions ORDER BY detected_at"
    ).fetchall()
    assert len(revisions) == 2
    assert revisions[1][1] == revisions[0][0]
    assert len(list((tmp_path / "captures" / "crossref").glob("sha256-*.json"))) == 3
