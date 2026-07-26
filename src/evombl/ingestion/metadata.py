import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from .rate_limit import RateLimiter, policy_for


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
        timeout: float = 20.0,
        client: httpx.Client | None = None,
        rate_limiter: RateLimiter | None = None,
        ncbi_api_key: bool = False,
    ) -> None:
        self.capture_dir, self.contact_email, self.user_agent, self.timeout = (
            capture_dir,
            contact_email,
            user_agent,
            timeout,
        )
        self.client = client or httpx.Client()
        self.rate_limiter = rate_limiter or RateLimiter(
            policy_for(self.provider, ncbi_api_key=ncbi_api_key)
        )

    def url(self, identifier: str) -> str:
        raise NotImplementedError

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=0.5, max=4), reraise=True)
    def fetch(
        self, identifier: str, *, offline: bool = False, refresh: bool = False
    ) -> MetadataCapture:
        key = hashlib.sha256(f"{self.provider}:{identifier}".encode()).hexdigest()
        provider_dir = self.capture_dir / self.provider
        index = provider_dir / f"{key}.latest"
        target = (
            provider_dir / index.read_text().strip() if index.exists() else provider_dir / "missing"
        )
        if target.exists() and not refresh:
            raw = target.read_bytes()
        elif offline:
            raise RuntimeError("offline mode: immutable capture is unavailable")
        else:
            self.rate_limiter.acquire()
            response = self.client.get(
                self.url(identifier),
                timeout=self.timeout,
                headers={"User-Agent": f"{self.user_agent} mailto:{self.contact_email}"},
            )
            if response.status_code == 429:
                retry_after = response.headers.get("Retry-After")
                self.rate_limiter.acquire(float(retry_after) if retry_after else None)
            response.raise_for_status()
            raw = response.content
            try:
                candidate_payload = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise ValueError(f"malformed {self.provider} JSON response") from exc
            if not isinstance(candidate_payload, dict):
                raise ValueError("metadata response must be a JSON object")
            digest = hashlib.sha256(raw).hexdigest()
            target = provider_dir / f"sha256-{digest}.json"
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists() and target.read_bytes() != raw:
                raise RuntimeError("immutable capture hash collision")
            if not target.exists():
                target.write_bytes(raw)
            index.write_text(target.name, encoding="utf-8")
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"malformed {self.provider} JSON response") from exc
        if not isinstance(payload, dict):
            raise ValueError("metadata response must be a JSON object")
        return MetadataCapture(
            self.provider,
            identifier,
            datetime.now(UTC).isoformat(),
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
