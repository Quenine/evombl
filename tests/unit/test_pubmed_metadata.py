import json
from pathlib import Path

import duckdb
import httpx
import pytest
from pydantic import ValidationError

from evombl.domain.persistence import SourceRetrievalEventRecord
from evombl.ingestion.bibliographic import (
    NondeterministicNormalizationError,
    candidate_from_capture,
    immutable_candidate_id,
    record_pubmed_processing,
    save_candidate,
)
from evombl.ingestion.metadata import MetadataCapture, PubmedAdapter
from evombl.storage.database import migrate
from evombl.storage.repositories import SourceRetrievalEventRepository


def pubmed_capture(**overrides: object) -> MetadataCapture:
    record: dict[str, object] = {
        "uid": "SYNTHETIC_TEST_DATA-PMID",
        "title": "SYNTHETIC_TEST_DATA title",
        "authors": [
            {"name": "Synthetic One", "authtype": "Author"},
            {"name": "SYNTHETIC_TEST_DATA Consortium", "authtype": "CollectiveName"},
        ],
        "fulljournalname": "SYNTHETIC_TEST_DATA Journal",
        "pubdate": "2026 Jul 02",
        "epubdate": "2026 Jun 09",
        "sortpubdate": "2026/07/02 00:00",
        "volume": "9",
        "issue": "2",
        "pages": "e12345",
        "elocationid": "doi: 10.1/SYNTHETIC_TEST_DATA",
        "pubtype": ["Journal Article", "Research Support"],
        "articleids": [
            {"idtype": "pubmed", "value": "SYNTHETIC_TEST_DATA-PMID"},
            {"idtype": "doi", "value": "10.1/SYNTHETIC_TEST_DATA"},
            {"idtype": "pmc", "value": "SYNTHETIC_TEST_DATA-PMC"},
        ],
        "references": [{"reftype": "RetractionOf", "pmid": "SYNTHETIC_TEST_DATA-OLD"}],
        "history": [{"pubstatus": "entrez", "date": "2026/06/10 00:00"}],
        "recordstatus": "SYNTHETIC_TEST_DATA status",
        "unexpected_optional_provider_field": {"legally": "valid"},
    }
    record.update(overrides)
    payload = {
        "header": {"type": "esummary", "version": "0.3"},
        "result": {"uids": [record["uid"]], str(record["uid"]): record},
    }
    return MetadataCapture(
        "ncbi_pubmed",
        str(record["uid"]),
        "2026-01-01",
        "a" * 64,
        Path("SYNTHETIC_TEST_DATA.json"),
        payload,
        "SYNTHETIC_TEST_DATA-EVENT",
    )


def candidate(**overrides: object):  # type: ignore[no-untyped-def]
    return candidate_from_capture(
        "SYNTHETIC_TEST_DATA-SEED", "SYNTHETIC_TEST_DATA-SOURCE", pubmed_capture(**overrides)
    )


def versioned_candidate(
    response_hash: str,
    retrieval_event_id: str,
    **updates: object,
):  # type: ignore[no-untyped-def]
    record = candidate()
    identity = immutable_candidate_id(
        record.source_id,
        record.provider,
        "SYNTHETIC_TEST_DATA-PMID",
        response_hash,
        "ncbi-pubmed-esummary-json-v2",
    )
    return record.model_copy(
        update={
            "candidate_id": identity,
            "response_hash": response_hash,
            "retrieval_event_id": retrieval_event_id,
            **updates,
        }
    )


def insert_event(connection: duckdb.DuckDBPyConnection, event_id: str, digest: str) -> None:
    SourceRetrievalEventRepository().insert(
        connection,
        SourceRetrievalEventRecord(
            retrieval_id=event_id,
            source_id="SYNTHETIC_TEST_DATA-SOURCE",
            provider="ncbi_pubmed",
            requested_identifier="SYNTHETIC_TEST_DATA-PMID",
            request_timestamp="2026-01-01T00:00:00",
            completion_timestamp="2026-01-01T00:00:01",
            outcome="success_new_capture",
            http_status=200,
            attempt_count=1,
            response_hash=digest,
            response_path=Path(f"SYNTHETIC_TEST_DATA-{event_id}.json"),
            adapter_version="SYNTHETIC_TEST_DATA",
            configuration_version="SYNTHETIC_TEST_DATA",
        ),
    )


def version_database(tmp_path: Path, *events: tuple[str, str]) -> duckdb.DuckDBPyConnection:
    database = tmp_path / "SYNTHETIC_TEST_DATA-versions.duckdb"
    migrate(database)
    connection = duckdb.connect(str(database))
    connection.execute(
        "INSERT INTO evidence_sources VALUES (?,?,?)",
        ["SYNTHETIC_TEST_DATA-SOURCE", "other", json.dumps({"synthetic": True})],
    )
    for event_id, digest in events:
        insert_event(connection, event_id, digest)
    return connection


def test_pubmed_exact_esummary_shape_and_publication_type_array() -> None:
    record = candidate()
    assert record.doi == "10.1/SYNTHETIC_TEST_DATA"
    assert record.pmid == "SYNTHETIC_TEST_DATA-PMID"
    assert record.pmcid == "SYNTHETIC_TEST_DATA-PMC"
    assert record.publication_types == ["Journal Article", "Research Support"]
    assert record.article_type == "Journal Article"
    assert record.article_number is None
    assert record.raw_provider_values["unexpected_optional_provider_field"] == {"legally": "valid"}


def test_pubmed_authors_dates_and_relationships_preserve_provider_semantics() -> None:
    record = candidate()
    assert record.authors == ["Synthetic One", "SYNTHETIC_TEST_DATA Consortium"]
    assert str(record.electronic_publication_date) == "2026-06-09"
    assert str(record.issue_publication_date) == "2026-07-02"
    assert "RetractionOf" in record.update_indicators[0]
    assert record.abstract_available is None


@pytest.mark.parametrize(
    ("overrides", "expected_doi", "expected_pmcid"),
    [
        ({"articleids": [{"idtype": "pubmed", "value": "SYNTHETIC_TEST_DATA-PMID"}]}, None, None),
        ({"articleids": []}, None, None),
        (
            {"authors": [{"name": "Only Author"}]},
            "10.1/SYNTHETIC_TEST_DATA",
            "SYNTHETIC_TEST_DATA-PMC",
        ),
    ],
)
def test_pubmed_optional_identifiers_and_single_author(
    overrides: dict[str, object], expected_doi: str | None, expected_pmcid: str | None
) -> None:
    record = candidate(**overrides)
    assert record.doi == expected_doi
    assert record.pmcid == expected_pmcid


def test_pubmed_missing_issue_volume_pages_and_empty_arrays_are_null_safe() -> None:
    record = candidate(
        issue="", volume="", pages="", elocationid="", authors=[], pubtype=[], history=[]
    )
    assert (record.issue, record.volume, record.pagination, record.article_number) == (
        None,
        None,
        None,
        None,
    )
    assert record.authors == [] and record.publication_types == []


def test_pubmed_malformed_provider_record_has_precise_validation_path() -> None:
    with pytest.raises(ValidationError) as caught:
        candidate(pubtype="SYNTHETIC_TEST_DATA-not-an-array")
    detail = caught.value.errors(include_url=False)[0]
    assert detail["loc"] == ("pubtype",)
    assert detail["type"] == "list_type"


def test_pubmed_processing_classifies_validation_failure(tmp_path: Path) -> None:
    database = tmp_path / "SYNTHETIC_TEST_DATA.duckdb"
    migrate(database)
    with duckdb.connect(str(database)) as connection:
        connection.execute(
            "INSERT INTO evidence_sources VALUES (?,?,?)",
            ["SYNTHETIC_TEST_DATA-SOURCE", "other", json.dumps({"synthetic": True})],
        )
        event = SourceRetrievalEventRecord(
            retrieval_id="SYNTHETIC_TEST_DATA-EVENT",
            source_id="SYNTHETIC_TEST_DATA-SOURCE",
            provider="ncbi_pubmed",
            requested_identifier="SYNTHETIC_TEST_DATA-PMID",
            request_timestamp="2026-01-01T00:00:00",
            completion_timestamp="2026-01-01T00:00:01",
            outcome="success_new_capture",
            http_status=200,
            attempt_count=1,
            response_hash="a" * 64,
            response_path=Path("SYNTHETIC_TEST_DATA.json"),
            adapter_version="SYNTHETIC_TEST_DATA",
            configuration_version="SYNTHETIC_TEST_DATA",
        )
        SourceRetrievalEventRepository().insert(connection, event)
        capture = pubmed_capture(pubtype="SYNTHETIC_TEST_DATA-not-an-array")
        with pytest.raises(ValidationError) as caught:
            candidate_from_capture(
                "SYNTHETIC_TEST_DATA-SEED", "SYNTHETIC_TEST_DATA-SOURCE", capture
            )
        record_pubmed_processing(connection, capture, "normalization_failure", error=caught.value)
        row = connection.execute(
            "SELECT outcome,error_type,error_path,received_type,expected_type "
            "FROM metadata_processing_events"
        ).fetchone()
    assert row == (
        "normalization_failure",
        "ValidationError",
        "pubtype",
        "str",
        "Input should be a valid list",
    )


def test_pubmed_candidate_save_is_idempotent_across_offline_reprocessing(tmp_path: Path) -> None:
    database = tmp_path / "SYNTHETIC_TEST_DATA-idempotent.duckdb"
    migrate(database)
    with duckdb.connect(str(database)) as connection:
        connection.execute(
            "INSERT INTO evidence_sources VALUES (?,?,?)",
            ["SYNTHETIC_TEST_DATA-SOURCE", "other", json.dumps({"synthetic": True})],
        )
        for event_id in ("SYNTHETIC_TEST_DATA-EVENT", "SYNTHETIC_TEST_DATA-REPROCESS"):
            SourceRetrievalEventRepository().insert(
                connection,
                SourceRetrievalEventRecord(
                    retrieval_id=event_id,
                    source_id="SYNTHETIC_TEST_DATA-SOURCE",
                    provider="ncbi_pubmed",
                    requested_identifier="SYNTHETIC_TEST_DATA-PMID",
                    request_timestamp="2026-01-01T00:00:00",
                    completion_timestamp="2026-01-01T00:00:01",
                    outcome="offline_cache_hit",
                    attempt_count=1,
                    response_hash="a" * 64,
                    response_path=Path("SYNTHETIC_TEST_DATA.json"),
                    offline=True,
                    adapter_version="SYNTHETIC_TEST_DATA",
                    configuration_version="SYNTHETIC_TEST_DATA",
                ),
            )
        first = candidate()
        second = first.model_copy(update={"retrieval_event_id": "SYNTHETIC_TEST_DATA-REPROCESS"})
        first_result = save_candidate(
            connection,
            first,
            "SYNTHETIC_TEST_DATA-PMID",
            "ncbi-pubmed-esummary-json-v2",
        )
        second_result = save_candidate(
            connection,
            second,
            "SYNTHETIC_TEST_DATA-PMID",
            "ncbi-pubmed-esummary-json-v2",
        )
        assert first_result.outcome == "candidate_created"
        assert second_result.outcome == "duplicate_ignored"
        assert connection.execute("SELECT count(*) FROM metadata_candidates").fetchone() == (1,)


def test_identical_response_with_changed_output_is_nondeterministic(tmp_path: Path) -> None:
    digest = "b" * 64
    connection = version_database(tmp_path, ("SYNTHETIC_TEST_DATA-E1", digest))
    with connection:
        first = versioned_candidate(digest, "SYNTHETIC_TEST_DATA-E1")
        save_candidate(
            connection, first, "SYNTHETIC_TEST_DATA-PMID", "ncbi-pubmed-esummary-json-v2"
        )
        changed = first.model_copy(update={"title": "SYNTHETIC_TEST_DATA changed"})
        with pytest.raises(NondeterministicNormalizationError):
            save_candidate(
                connection,
                changed,
                "SYNTHETIC_TEST_DATA-PMID",
                "ncbi-pubmed-esummary-json-v2",
            )
        assert connection.execute("SELECT count(*) FROM metadata_candidates").fetchone() == (1,)


@pytest.mark.parametrize(
    ("updates", "expected"),
    [
        (
            {"raw_provider_values": {"SYNTHETIC_TEST_DATA": "changed"}},
            "semantically_equivalent_revision",
        ),
        ({"title": "Synthetic test data, title!"}, "semantically_equivalent_revision"),
        (
            {"title": "SYNTHETIC_TEST_DATA materially different subject"},
            "material_candidate_revision",
        ),
        (
            {"authors": ["SYNTHETIC_TEST_DATA Consortium", "Synthetic One"]},
            "material_candidate_revision",
        ),
        (
            {"doi": "10.2/SYNTHETIC_TEST_DATA", "pmid": "SYNTHETIC_TEST_DATA-OTHER"},
            "material_candidate_revision",
        ),
    ],
)
def test_changed_response_candidate_revision_classification(
    tmp_path: Path, updates: dict[str, object], expected: str
) -> None:
    first_hash, second_hash = "c" * 64, "d" * 64
    connection = version_database(
        tmp_path,
        ("SYNTHETIC_TEST_DATA-E1", first_hash),
        ("SYNTHETIC_TEST_DATA-E2", second_hash),
    )
    with connection:
        first = versioned_candidate(first_hash, "SYNTHETIC_TEST_DATA-E1")
        second = versioned_candidate(second_hash, "SYNTHETIC_TEST_DATA-E2", **updates)
        save_candidate(
            connection, first, "SYNTHETIC_TEST_DATA-PMID", "ncbi-pubmed-esummary-json-v2"
        )
        result = save_candidate(
            connection, second, "SYNTHETIC_TEST_DATA-PMID", "ncbi-pubmed-esummary-json-v2"
        )
        assert result.outcome == expected
        assert result.predecessor_candidate_id == first.candidate_id
        expected_review = expected == "material_candidate_revision"
        row = connection.execute(
            "SELECT manual_review_required FROM metadata_candidates WHERE candidate_id=?",
            [second.candidate_id],
        ).fetchone()
        assert row == (expected_review,)


def test_candidate_predecessor_chain_preserves_all_versions(tmp_path: Path) -> None:
    hashes = ("e" * 64, "f" * 64, "1" * 64)
    events = tuple((f"SYNTHETIC_TEST_DATA-E{i}", digest) for i, digest in enumerate(hashes))
    connection = version_database(tmp_path, *events)
    with connection:
        records = [
            versioned_candidate(digest, event_id, title=f"SYNTHETIC_TEST_DATA title {index}")
            for index, (event_id, digest) in enumerate(events)
        ]
        results = [
            save_candidate(
                connection,
                record,
                "SYNTHETIC_TEST_DATA-PMID",
                "ncbi-pubmed-esummary-json-v2",
            )
            for record in records
        ]
        assert [result.predecessor_candidate_id for result in results] == [
            None,
            records[0].candidate_id,
            records[1].candidate_id,
        ]
        assert connection.execute("SELECT count(*) FROM metadata_candidates").fetchone() == (3,)


def test_same_capture_with_new_normalizer_creates_candidate_version(tmp_path: Path) -> None:
    digest = "2" * 64
    connection = version_database(
        tmp_path,
        ("SYNTHETIC_TEST_DATA-E1", digest),
        ("SYNTHETIC_TEST_DATA-E2", digest),
    )
    with connection:
        old = versioned_candidate(digest, "SYNTHETIC_TEST_DATA-E1")
        old = old.model_copy(
            update={
                "candidate_id": immutable_candidate_id(
                    old.source_id,
                    old.provider,
                    "SYNTHETIC_TEST_DATA-PMID",
                    digest,
                    "ncbi-pubmed-esummary-json-v1",
                )
            }
        )
        save_candidate(connection, old, "SYNTHETIC_TEST_DATA-PMID", "ncbi-pubmed-esummary-json-v1")
        new = versioned_candidate(digest, "SYNTHETIC_TEST_DATA-E2", article_number=None)
        result = save_candidate(
            connection, new, "SYNTHETIC_TEST_DATA-PMID", "ncbi-pubmed-esummary-json-v2"
        )
        assert result.outcome == "candidate_version_created"
        assert result.predecessor_candidate_id == old.candidate_id
        assert connection.execute("SELECT count(*) FROM metadata_candidates").fetchone() == (2,)


def test_mocked_filtered_refresh_versions_changed_capture_and_is_idempotent(
    tmp_path: Path,
) -> None:
    database = tmp_path / "SYNTHETIC_TEST_DATA-refresh.duckdb"
    migrate(database)
    first_payload = pubmed_capture().payload
    second_payload = json.loads(json.dumps(first_payload))
    uid = second_payload["result"]["uids"][0]
    second_payload["result"][uid]["title"] = "SYNTHETIC_TEST_DATA materially changed title"
    payloads = iter([first_payload, second_payload, second_payload])
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            json=next(payloads),
            headers={"Content-Type": "application/json"},
            request=request,
        )
    )
    with duckdb.connect(str(database)) as connection:
        connection.execute(
            "INSERT INTO evidence_sources VALUES (?,?,?)",
            ["SYNTHETIC_TEST_DATA-SOURCE", "other", json.dumps({"synthetic": True})],
        )
        adapter = PubmedAdapter(
            tmp_path / "captures",
            "synthetic@example.invalid",
            "SYNTHETIC_TEST_DATA",
            connection=connection,
            source_id="SYNTHETIC_TEST_DATA-SOURCE",
            client=httpx.Client(transport=transport),
        )
        outcomes = []
        for _ in range(3):
            capture = adapter.fetch("SYNTHETIC_TEST_DATA-PMID", refresh=True)
            record = candidate_from_capture(
                "SYNTHETIC_TEST_DATA-SEED", "SYNTHETIC_TEST_DATA-SOURCE", capture
            )
            result = save_candidate(
                connection,
                record,
                "SYNTHETIC_TEST_DATA-PMID",
                "ncbi-pubmed-esummary-json-v2",
            )
            outcomes.append(result.outcome)
            record_pubmed_processing(
                connection,
                capture,
                result.outcome,
                candidate_id=result.candidate_id,
                normalized_record_hash=result.normalized_record_hash,
                semantic_bibliographic_hash=result.semantic_bibliographic_hash,
                predecessor_candidate_id=result.predecessor_candidate_id,
            )
        revisions = connection.execute("SELECT count(*) FROM source_revisions").fetchone()
        candidates = connection.execute("SELECT count(*) FROM metadata_candidates").fetchone()
        processing = connection.execute(
            "SELECT outcome FROM metadata_processing_events ORDER BY processed_at"
        ).fetchall()
    assert outcomes == [
        "candidate_created",
        "material_candidate_revision",
        "duplicate_ignored",
    ]
    assert revisions == (1,)
    assert candidates == (2,)
    assert processing == [(outcome,) for outcome in outcomes]
