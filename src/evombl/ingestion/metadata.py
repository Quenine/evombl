import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

import duckdb
import httpx

from evombl.domain.persistence import SourceRetrievalEventRecord, SourceRevisionRecord
from evombl.storage.repositories import SourceRetrievalEventRepository, SourceRevisionRepository

from .rate_limit import RateLimitConfiguration, RateLimiter, load_rate_limits, policy_for

ADAPTER_VERSION = "evombl-official-api-v2"
VALID_OUTCOMES = {
    "success_new_capture",
    "success_identical_capture",
    "success_changed_capture",
    "offline_cache_hit",
    "offline_cache_miss",
    "http_error",
    "timeout",
    "malformed_response",
    "retry_exhausted",
}


@dataclass(frozen=True)
class MetadataCapture:
    provider: str
    identifier: str
    accessed_at: str
    response_hash: str
    response_path: Path
    payload: dict[str, Any]


class MetadataAdapter(Protocol):
    provider: str

    def fetch(
        self, identifier: str, *, offline: bool = False, refresh: bool = False
    ) -> MetadataCapture: ...


class OfficialApiAdapter:
    provider = "base"

    def __init__(
        self,
        capture_dir: Path,
        contact_email: str,
        user_agent: str,
        *,
        connection: duckdb.DuckDBPyConnection,
        source_id: str,
        timeout: float = 20.0,
        client: httpx.Client | None = None,
        rate_configuration: RateLimitConfiguration | None = None,
        rate_limiter: RateLimiter | None = None,
        ncbi_api_key: bool = False,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self.capture_dir = capture_dir
        self.contact_email = contact_email
        self.user_agent = user_agent
        self.connection = connection
        self.source_id = source_id
        self.timeout = timeout
        self.client = client or httpx.Client()
        self.configuration = rate_configuration or load_rate_limits()
        self.policy = policy_for(self.configuration, self.provider, ncbi_api_key=ncbi_api_key)
        self.rate_limiter = rate_limiter or RateLimiter(self.policy)
        self.now = now or (lambda: datetime.now(UTC))

    def url(self, identifier: str) -> str:
        raise NotImplementedError

    def _event(
        self,
        identifier: str,
        start: datetime,
        outcome: str,
        attempts: int,
        *,
        status: int | None = None,
        digest: str | None = None,
        path: Path | None = None,
        error: Exception | None = None,
        offline: bool = False,
    ) -> SourceRetrievalEventRecord:
        completed = self.now()
        seed = f"{self.provider}|{identifier}|{start.isoformat()}|{outcome}"
        event_id = "EVO-RET-" + hashlib.sha256(seed.encode()).hexdigest()[:20].upper()
        message = str(error).split("?")[0][:300] if error else None
        return SourceRetrievalEventRecord(
            retrieval_id=event_id,
            source_id=self.source_id,
            provider=self.provider,
            requested_identifier=identifier,
            request_timestamp=start,
            completion_timestamp=completed,
            outcome=outcome,
            http_status=status,
            attempt_count=max(attempts, 1),
            response_hash=digest,
            response_path=path,
            error_type=type(error).__name__ if error else None,
            error_message=message,
            offline=offline,
            adapter_version=ADAPTER_VERSION,
            configuration_version=self.configuration.configuration_version,
        )

    def _persist(
        self, event: SourceRetrievalEventRecord, revision: SourceRevisionRecord | None = None
    ) -> None:
        self.connection.execute("BEGIN")
        try:
            SourceRetrievalEventRepository().insert(self.connection, event)
            if revision:
                SourceRevisionRepository().insert(self.connection, revision)
            self.connection.execute("COMMIT")
        except Exception:
            self.connection.execute("ROLLBACK")
            raise

    def fetch(
        self, identifier: str, *, offline: bool = False, refresh: bool = False
    ) -> MetadataCapture:
        start = self.now()
        key = hashlib.sha256(f"{self.provider}:{identifier}".encode()).hexdigest()
        provider_dir = self.capture_dir / self.provider
        index = provider_dir / f"{key}.latest"
        old_name = index.read_text().strip() if index.exists() else None
        old_target = provider_dir / old_name if old_name else None
        if old_target and old_target.exists() and not refresh:
            raw = old_target.read_bytes()
            digest = hashlib.sha256(raw).hexdigest()
            outcome = "offline_cache_hit" if offline else "success_identical_capture"
            event = self._event(
                identifier, start, outcome, 1, digest=digest, path=old_target, offline=offline
            )
            self._persist(event)
            return self._capture(identifier, raw, old_target)
        if offline:
            error = RuntimeError("offline cache miss")
            self._persist(
                self._event(identifier, start, "offline_cache_miss", 1, error=error, offline=True)
            )
            raise error
        response: httpx.Response | None = None
        last_error: Exception | None = None
        for attempt in range(1, self.policy.retry_count + 1):
            try:
                self.rate_limiter.acquire()
                response = self.client.get(
                    self.url(identifier),
                    timeout=self.timeout,
                    headers={"User-Agent": f"{self.user_agent} mailto:{self.contact_email}"},
                )
                if response.status_code == 429 and self.policy.honor_retry_after:
                    self.rate_limiter.acquire(float(response.headers.get("Retry-After", "0")))
                response.raise_for_status()
                break
            except httpx.TimeoutException as exc:
                last_error = exc
            except httpx.HTTPStatusError as exc:
                last_error = exc
                if exc.response.status_code < 500 and exc.response.status_code != 429:
                    event = self._event(
                        identifier,
                        start,
                        "http_error",
                        attempt,
                        status=exc.response.status_code,
                        error=exc,
                    )
                    self._persist(event)
                    raise
            if attempt < self.policy.retry_count:
                self.rate_limiter.sleeper(
                    min(
                        self.policy.maximum_backoff, self.policy.base_backoff * (2 ** (attempt - 1))
                    )
                )
        else:
            outcome = (
                "timeout"
                if isinstance(last_error, httpx.TimeoutException) and self.policy.retry_count == 1
                else "retry_exhausted"
            )
            self._persist(
                self._event(
                    identifier,
                    start,
                    outcome,
                    self.policy.retry_count,
                    status=response.status_code if response else None,
                    error=last_error,
                )
            )
            raise last_error or RuntimeError("retry exhausted")
        assert response is not None
        raw = response.content
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            self._persist(
                self._event(
                    identifier,
                    start,
                    "malformed_response",
                    attempt,
                    status=response.status_code,
                    error=exc,
                )
            )
            raise ValueError(f"malformed {self.provider} JSON response") from exc
        if not isinstance(payload, dict):
            malformed_error = ValueError("metadata response must be a JSON object")
            self._persist(
                self._event(
                    identifier,
                    start,
                    "malformed_response",
                    attempt,
                    status=response.status_code,
                    error=malformed_error,
                )
            )
            raise malformed_error
        digest = hashlib.sha256(raw).hexdigest()
        target = provider_dir / f"sha256-{digest}.json"
        provider_dir.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            target.write_bytes(raw)
        old_hash = old_name.removeprefix("sha256-").removesuffix(".json") if old_name else None
        outcome = (
            "success_new_capture"
            if old_hash is None
            else ("success_identical_capture" if old_hash == digest else "success_changed_capture")
        )
        event = self._event(
            identifier,
            start,
            outcome,
            attempt,
            status=response.status_code,
            digest=digest,
            path=target,
        )
        revision = None
        if outcome == "success_changed_capture":
            prior = self.connection.execute(
                "SELECT revision_id FROM source_revisions WHERE source_id=? ORDER BY detected_at DESC,revision_id DESC LIMIT 1",
                [self.source_id],
            ).fetchone()
            revision_id = (
                "EVO-REV-"
                + hashlib.sha256(f"{self.source_id}|{old_hash}|{digest}".encode())
                .hexdigest()[:20]
                .upper()
            )
            revision = SourceRevisionRecord(
                revision_id=revision_id,
                source_id=self.source_id,
                predecessor_revision_id=prior[0] if prior else None,
                previous_content_hash=old_hash,
                new_content_hash=digest,
                revision_reason="official API response content changed",
                detected_at=self.now(),
                actor=self.provider,
                retrieval_event_id=event.retrieval_id,
                verification_status="metadata_pending_verification",
            )
        self._persist(event, revision)
        index.write_text(target.name, encoding="utf-8")
        return self._capture(identifier, raw, target)

    def _capture(self, identifier: str, raw: bytes, target: Path) -> MetadataCapture:
        payload = json.loads(raw)
        return MetadataCapture(
            self.provider,
            identifier,
            self.now().isoformat(),
            hashlib.sha256(raw).hexdigest(),
            target,
            payload,
        )


class CrossrefAdapter(OfficialApiAdapter):
    provider = "crossref"

    def url(self, identifier: str) -> str:
        return f"https://api.crossref.org/works/{identifier}"


class EuropePmcAdapter(OfficialApiAdapter):
    provider = "europe_pmc"

    def url(self, identifier: str) -> str:
        return f"https://www.ebi.ac.uk/europepmc/webservices/rest/search?query=DOI:{identifier}&format=json"


class NcbiAdapter(OfficialApiAdapter):
    provider = "ncbi"

    def url(self, identifier: str) -> str:
        return f"https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi?db=protein&id={identifier}&retmode=json"


class RcsbPdbAdapter(OfficialApiAdapter):
    provider = "rcsb_pdb"

    def url(self, identifier: str) -> str:
        return f"https://data.rcsb.org/rest/v1/core/entry/{identifier}"


RcdbPdbAdapter = RcsbPdbAdapter
