import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential


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
        self, capture_dir: Path, contact_email: str, user_agent: str, timeout: float = 20.0
    ) -> None:
        self.capture_dir, self.contact_email, self.user_agent, self.timeout = (
            capture_dir,
            contact_email,
            user_agent,
            timeout,
        )

    def url(self, identifier: str) -> str:
        raise NotImplementedError

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=0.5, max=4), reraise=True)
    def fetch(
        self, identifier: str, *, offline: bool = False, refresh: bool = False
    ) -> MetadataCapture:
        key = hashlib.sha256(f"{self.provider}:{identifier}".encode()).hexdigest()
        target = self.capture_dir / self.provider / f"{key}.json"
        if target.exists() and not refresh:
            raw = target.read_bytes()
        elif offline:
            raise RuntimeError("offline mode: immutable capture is unavailable")
        else:
            response = httpx.get(
                self.url(identifier),
                timeout=self.timeout,
                headers={"User-Agent": f"{self.user_agent} mailto:{self.contact_email}"},
            )
            response.raise_for_status()
            raw = response.content
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)
        payload = json.loads(raw)
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


class RcdbPdbAdapter(OfficialApiAdapter):
    provider = "rcsb_pdb"

    def url(self, identifier: str) -> str:
        return f"https://data.rcsb.org/rest/v1/core/entry/{identifier}"
