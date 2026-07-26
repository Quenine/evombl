import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any

import duckdb
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from evombl.domain.bibliographic import (
    ComparisonClass,
    MetadataCandidateRecord,
    MetadataComparisonRecord,
    RelevanceStatus,
)
from evombl.ingestion.metadata import MetadataCapture
from evombl.storage.repositories import stable_hash, stable_json

PUBMED_NORMALIZER_VERSION = "ncbi-pubmed-esummary-json-v2"
LEGACY_PUBMED_NORMALIZER_VERSION = "ncbi-pubmed-esummary-json-v1"


class NondeterministicNormalizationError(ValueError):
    pass


class CandidatePersistenceConflictError(ValueError):
    pass


@dataclass(frozen=True)
class CandidatePersistenceResult:
    outcome: str
    candidate_id: str
    normalized_record_hash: str
    semantic_bibliographic_hash: str
    predecessor_candidate_id: str | None = None
    inserted: bool = False


class PubmedAuthor(BaseModel):
    model_config = ConfigDict(extra="allow")
    name: str | None = None
    authtype: str | None = None
    clusterid: str | None = None


class PubmedArticleId(BaseModel):
    model_config = ConfigDict(extra="allow")
    idtype: str | None = None
    idtypen: int | None = None
    value: str | None = None


class PubmedRelationship(BaseModel):
    model_config = ConfigDict(extra="allow")
    refsource: str | None = None
    reftype: str | None = None
    pmid: str | int | None = None
    note: str | None = None


class PubmedHistoryItem(BaseModel):
    model_config = ConfigDict(extra="allow")
    pubstatus: str | None = None
    date: str | None = None


class PubmedSummary(BaseModel):
    model_config = ConfigDict(extra="allow")
    uid: str | int
    title: str | None = None
    authors: list[PubmedAuthor] = Field(default_factory=list)
    fulljournalname: str | None = None
    source: str | None = None
    pubdate: str | None = None
    epubdate: str | None = None
    sortpubdate: str | None = None
    volume: str | None = None
    issue: str | None = None
    pages: str | None = None
    elocationid: str | None = None
    pubtype: list[str] = Field(default_factory=list)
    articleids: list[PubmedArticleId] = Field(default_factory=list)
    references: list[PubmedRelationship] = Field(default_factory=list)
    history: list[PubmedHistoryItem] = Field(default_factory=list)
    recordstatus: str | None = None


def normalize_doi(value: str | None) -> str | None:
    if value is None:
        return None
    return re.sub(r"^https?://(dx\.)?doi\.org/", "", value.strip().lower()).rstrip(".")


def normalize_text(value: str | None) -> str | None:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip() if value else None


def _year(value: Any) -> int | None:
    try:
        return int(str(value)[:4])
    except (TypeError, ValueError):
        return None


def _pubmed_date(value: str | None) -> date | None:
    if not value:
        return None
    normalized = " ".join(value.split())
    for pattern in ("%Y %b %d", "%Y %b", "%Y"):
        try:
            parsed = datetime.strptime(normalized, pattern)
            return date(parsed.year, parsed.month, parsed.day)
        except ValueError:
            continue
    return None


def _pubmed_relationships(items: list[PubmedRelationship]) -> list[str]:
    relationships = []
    for item in items:
        values = {
            "reftype": item.reftype,
            "pmid": str(item.pmid) if item.pmid is not None else None,
            "note": item.note,
            "refsource": item.refsource,
        }
        if any(value for value in values.values()):
            relationships.append(json.dumps(values, sort_keys=True, separators=(",", ":")))
    return relationships


def logical_candidate_key(source_id: str, provider: str, requested_identifier: str) -> str:
    return "|".join((source_id, provider, requested_identifier))


def normalization_version_hash(version: str) -> str:
    return hashlib.sha256(version.encode()).hexdigest()


def immutable_candidate_id(
    source_id: str,
    provider: str,
    requested_identifier: str,
    response_hash: str,
    normalization_version: str,
) -> str:
    identity = "|".join(
        (
            logical_candidate_key(source_id, provider, requested_identifier),
            response_hash,
            normalization_version_hash(normalization_version),
        )
    )
    return "EVO-META-" + hashlib.sha256(identity.encode()).hexdigest()[:20].upper()


def normalized_candidate_hash(record: MetadataCandidateRecord) -> str:
    payload = record.model_dump(mode="json")
    payload.pop("candidate_id", None)
    payload.pop("retrieval_event_id", None)
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()


def semantic_candidate_payload(record: MetadataCandidateRecord) -> dict[str, Any]:
    return {
        "provider": record.provider,
        "doi": normalize_doi(record.doi),
        "pmid": record.pmid.strip() if record.pmid else None,
        "pmcid": record.pmcid.strip().upper() if record.pmcid else None,
        "title": normalize_text(record.title),
        "subtitle": normalize_text(record.subtitle),
        "authors": [normalize_text(author) for author in record.authors],
        "journal": normalize_text(record.journal),
        "publisher": normalize_text(record.publisher),
        "publication_year": record.publication_year,
        "electronic_publication_date": str(record.electronic_publication_date)
        if record.electronic_publication_date
        else None,
        "issue_publication_date": str(record.issue_publication_date)
        if record.issue_publication_date
        else None,
        "volume": normalize_text(record.volume),
        "issue": normalize_text(record.issue),
        "article_number": normalize_text(record.article_number),
        "pagination": normalize_text(record.pagination),
        "article_type": normalize_text(record.article_type),
        "publication_types": [normalize_text(value) for value in record.publication_types],
        "abstract_available": record.abstract_available,
        "update_indicators": sorted(record.update_indicators),
        "open_access": record.open_access,
        "licence": record.licence.strip() if record.licence else None,
        "full_text_location": record.full_text_location,
        "supplementary_material": record.supplementary_material,
        "provider_record_id": record.provider_record_id,
    }


def semantic_candidate_hash(record: MetadataCandidateRecord) -> str:
    return hashlib.sha256(
        json.dumps(
            semantic_candidate_payload(record),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode()
    ).hexdigest()


def candidate_from_capture(
    seed_id: str, source_id: str, capture: MetadataCapture
) -> MetadataCandidateRecord:
    payload = capture.payload
    provider = capture.provider
    data: dict[str, Any]
    if provider == "crossref":
        data = payload.get("message", {})
    elif provider == "europe_pmc":
        results = payload.get("resultList", {}).get("result", [])
        data = results[0] if results else {}
    elif provider == "ncbi_pubmed":
        result = payload.get("result", {})
        uids = result.get("uids", [])
        data = result.get(str(uids[0]), {}) if uids else {}
    else:
        raise ValueError(f"unsupported bibliographic provider: {provider}")
    if not isinstance(data, dict) or not data:
        raise LookupError(f"{provider} record not found")
    if provider == "crossref":
        authors = [
            " ".join(filter(None, [a.get("given"), a.get("family")]))
            for a in data.get("author", [])
        ]
        title = (data.get("title") or [None])[0]
        journal = (data.get("container-title") or [None])[0]
        year = ((data.get("published") or {}).get("date-parts") or [[None]])[0][0]
        doi = data.get("DOI")
        pmid = None
        pmcid = None
        open_access = None
        licence = (data.get("license") or [{}])[0].get("URL")
        full_text = None
    elif provider == "europe_pmc":
        authors = [
            item.strip() for item in str(data.get("authorString") or "").split(",") if item.strip()
        ]
        title = data.get("title")
        journal = data.get("journalTitle")
        year = data.get("pubYear")
        doi = data.get("doi")
        pmid = data.get("pmid")
        pmcid = data.get("pmcid")
        open_access = (
            str(data.get("isOpenAccess", "")).upper() == "Y"
            if data.get("isOpenAccess") is not None
            else None
        )
        licence = data.get("license")
        full_text = data.get("fullTextUrlList")
    else:
        summary = PubmedSummary.model_validate(data)
        authors = [author.name for author in summary.authors if author.name]
        title = summary.title
        journal = summary.fulljournalname
        year = summary.pubdate
        ids = {
            item.idtype.lower(): item.value
            for item in summary.articleids
            if item.idtype and item.value
        }
        doi = ids.get("doi")
        pmid = ids.get("pubmed") or str(summary.uid)
        pmcid = ids.get("pmc")
        open_access = None
        licence = None
        full_text = None
    normalizer_version = (
        PUBMED_NORMALIZER_VERSION if provider == "ncbi_pubmed" else "bibliographic-normalizer-v1"
    )
    candidate_id = immutable_candidate_id(
        source_id,
        provider,
        capture.identifier,
        capture.response_hash,
        normalizer_version,
    )
    return MetadataCandidateRecord(
        candidate_id=candidate_id,
        seed_id=seed_id,
        source_id=source_id,
        provider=provider,
        doi=doi,
        pmid=str(pmid) if pmid else None,
        pmcid=pmcid,
        title=title,
        authors=authors,
        journal=journal,
        publisher=data.get("publisher"),
        publication_year=_year(year),
        electronic_publication_date=_pubmed_date(summary.epubdate)
        if provider == "ncbi_pubmed"
        else None,
        issue_publication_date=_pubmed_date(summary.pubdate) if provider == "ncbi_pubmed" else None,
        volume=data.get("volume") or None,
        issue=data.get("issue") or None,
        article_number=(data.get("elocationid") or None)
        if not str(data.get("elocationid") or "").lower().startswith("doi:")
        else None,
        pagination=data.get("page") or data.get("pages") or None,
        article_type=(summary.pubtype[0] if summary.pubtype else None)
        if provider == "ncbi_pubmed"
        else data.get("type") or data.get("pubtype"),
        publication_types=summary.pubtype if provider == "ncbi_pubmed" else [],
        abstract_available=bool(data.get("hasTextMinedTerms"))
        if provider == "europe_pmc"
        else None,
        update_indicators=_pubmed_relationships(summary.references)
        if provider == "ncbi_pubmed"
        else [],
        open_access=open_access,
        licence=licence,
        full_text_location=json.dumps(full_text, sort_keys=True) if full_text else None,
        supplementary_material=None,
        provider_record_id=str(data.get("id") or data.get("uid") or data.get("DOI") or "") or None,
        provider_version=(
            next(
                (
                    item.date
                    for item in reversed(summary.history)
                    if item.pubstatus in {"entrez", "medline", "pubmed"} and item.date
                ),
                None,
            )
            or summary.sortpubdate
        )
        if provider == "ncbi_pubmed"
        else str(data.get("updated") or data.get("lastupdate") or "") or None,
        response_hash=capture.response_hash,
        retrieval_event_id=capture.retrieval_event_id,
        raw_provider_values=data,
    )


def save_candidate(
    connection: duckdb.DuckDBPyConnection,
    record: MetadataCandidateRecord,
    requested_identifier: str,
    normalization_version: str,
) -> CandidatePersistenceResult:
    logical_key = logical_candidate_key(record.source_id, record.provider, requested_identifier)
    version_hash = normalization_version_hash(normalization_version)
    normalized_hash = normalized_candidate_hash(record)
    semantic_hash = semantic_candidate_hash(record)
    observation = connection.execute(
        "SELECT candidate_id,normalized_record_hash,semantic_bibliographic_hash "
        "FROM metadata_candidates WHERE logical_candidate_key=? AND response_hash=? "
        "AND normalization_version_hash=?",
        [logical_key, record.response_hash, version_hash],
    ).fetchone()
    if observation:
        if observation[1] == normalized_hash:
            return CandidatePersistenceResult(
                "duplicate_ignored",
                str(observation[0]),
                normalized_hash,
                str(observation[2]),
            )
        raise NondeterministicNormalizationError(
            "same response and normalization version produced different normalized metadata"
        )
    if connection.execute(
        "SELECT 1 FROM metadata_candidates WHERE candidate_id=?", [record.candidate_id]
    ).fetchone():
        raise CandidatePersistenceConflictError(
            f"candidate identity collision: {record.candidate_id}"
        )
    predecessor = connection.execute(
        "SELECT candidate_id,response_hash,semantic_bibliographic_hash "
        "FROM metadata_candidates WHERE logical_candidate_key=? "
        "ORDER BY created_at DESC NULLS LAST,candidate_id DESC LIMIT 1",
        [logical_key],
    ).fetchone()
    outcome = "candidate_created"
    manual_review = False
    predecessor_id = None
    if predecessor:
        predecessor_id = str(predecessor[0])
        if predecessor[1] == record.response_hash:
            outcome = "candidate_version_created"
            manual_review = predecessor[2] != semantic_hash
        elif predecessor[2] == semantic_hash:
            outcome = "semantically_equivalent_revision"
        else:
            outcome = "material_candidate_revision"
            manual_review = True
    digest = stable_hash(record)
    connection.execute(
        "INSERT INTO metadata_candidates("
        "candidate_id,seed_id,source_id,provider,doi,pmid,pmcid,title,publication_year,"
        "response_hash,retrieval_event_id,record_json,record_hash,logical_candidate_key,"
        "requested_identifier,normalization_version,normalization_version_hash,"
        "normalized_record_hash,semantic_bibliographic_hash,predecessor_candidate_id,"
        "candidate_status,manual_review_required,created_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        [
            record.candidate_id,
            record.seed_id,
            record.source_id,
            record.provider,
            record.doi,
            record.pmid,
            record.pmcid,
            record.title,
            record.publication_year,
            record.response_hash,
            record.retrieval_event_id,
            stable_json(record),
            digest,
            logical_key,
            requested_identifier,
            normalization_version,
            version_hash,
            normalized_hash,
            semantic_hash,
            predecessor_id,
            outcome,
            manual_review,
            datetime.now(UTC),
        ],
    )
    return CandidatePersistenceResult(
        outcome,
        record.candidate_id,
        normalized_hash,
        semantic_hash,
        predecessor_id,
        True,
    )


def record_pubmed_processing(
    connection: duckdb.DuckDBPyConnection,
    capture: MetadataCapture,
    outcome: str,
    *,
    candidate_id: str | None = None,
    normalized_record_hash: str | None = None,
    semantic_bibliographic_hash: str | None = None,
    predecessor_candidate_id: str | None = None,
    error: Exception | None = None,
) -> None:
    error_path = received_type = expected_type = error_message = None
    if isinstance(error, ValidationError):
        detail = error.errors(include_url=False)[0]
        error_path = ".".join(str(item) for item in detail["loc"])
        received_type = type(detail.get("input")).__name__
        expected_type = str(detail.get("msg"))
        error_message = str(detail.get("type"))
    elif error is not None:
        error_message = str(error)[:300]
    seed = (
        f"{capture.retrieval_event_id}|{PUBMED_NORMALIZER_VERSION}|{candidate_id or ''}|{outcome}"
    )
    processing_id = "EVO-METAPROC-" + hashlib.sha256(seed.encode()).hexdigest()[:20].upper()
    connection.execute(
        "INSERT OR IGNORE INTO metadata_processing_events VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        [
            processing_id,
            capture.retrieval_event_id,
            candidate_id,
            capture.provider,
            outcome,
            datetime.now(UTC),
            PUBMED_NORMALIZER_VERSION,
            type(error).__name__ if error else None,
            error_path,
            received_type,
            expected_type,
            error_message,
            normalized_record_hash,
            semantic_bibliographic_hash,
            predecessor_candidate_id,
        ],
    )


def compare_candidates(
    a: MetadataCandidateRecord, b: MetadataCandidateRecord
) -> list[MetadataComparisonRecord]:
    rows = []
    for field in (
        "doi",
        "pmid",
        "pmcid",
        "title",
        "authors",
        "journal",
        "publication_year",
        "article_type",
        "open_access",
        "licence",
    ):
        av = getattr(a, field)
        bv = getattr(b, field)
        sa = (
            json.dumps(av, ensure_ascii=False)
            if isinstance(av, list)
            else (str(av) if av is not None else None)
        )
        sb = (
            json.dumps(bv, ensure_ascii=False)
            if isinstance(bv, list)
            else (str(bv) if bv is not None else None)
        )
        classification: ComparisonClass
        if av is None or bv is None:
            classification = "compatible_partial_metadata"
        elif field == "doi":
            classification = (
                "exact_agreement"
                if normalize_doi(sa) == normalize_doi(sb)
                else "identifier_conflict"
            )
        elif field in {"pmid", "pmcid"} and sa != sb:
            classification = "identifier_conflict"
        elif sa == sb:
            classification = "exact_agreement"
        elif field in {"title", "journal"} and normalize_text(sa) == normalize_text(sb):
            classification = "formatting_only_difference"
        else:
            classification = "material_conflict"
        cid = (
            "EVO-CMPMETA-"
            + hashlib.sha256(f"{a.candidate_id}|{b.candidate_id}|{field}".encode())
            .hexdigest()[:20]
            .upper()
        )
        rows.append(
            MetadataComparisonRecord(
                comparison_id=cid,
                seed_id=a.seed_id,
                source_id=a.source_id,
                provider_a=a.provider,
                provider_b=b.provider,
                field_name=field,
                classification=classification,
                value_a=sa,
                value_b=sb,
            )
        )
    return rows


def triage(title: str | None, purpose: str) -> tuple[RelevanceStatus, str]:
    if not title:
        return "insufficient_metadata", "keyword-overlap-v1:no-title"
    stop = {"and", "the", "across", "including", "activity", "analysis", "current"}
    wanted = {w for w in (normalize_text(purpose) or "").split() if len(w) > 3 and w not in stop}
    observed = set((normalize_text(title) or "").split())
    overlap = len(wanted & observed)
    return (
        "likely_relevant"
        if overlap >= 2
        else "possibly_relevant"
        if overlap == 1
        else "manual_review_required",
        f"keyword-overlap-v1:{overlap}",
    )
