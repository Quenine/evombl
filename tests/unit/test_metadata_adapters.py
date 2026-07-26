import json
from pathlib import Path

import httpx
import pytest

from evombl.ingestion.metadata import CrossrefAdapter


def adapter(tmp_path: Path, content: bytes, status: int = 200) -> CrossrefAdapter:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(status, content=content, request=request)
    )
    return CrossrefAdapter(
        tmp_path,
        "synthetic@example.invalid",
        "SYNTHETIC_TEST_DATA",
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
