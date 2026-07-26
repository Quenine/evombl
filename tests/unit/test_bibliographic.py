from pathlib import Path

from typer.testing import CliRunner

from evombl.cli import app
from evombl.ingestion.bibliographic import candidate_from_capture, compare_candidates, triage
from evombl.ingestion.metadata import MetadataCapture


def capture(provider: str, payload: dict[str, object]) -> MetadataCapture:
    return MetadataCapture(
        provider,
        "SYNTHETIC_TEST_DATA",
        "2026-01-01",
        "a" * 64,
        Path("SYNTHETIC_TEST_DATA.json"),
        payload,
        "SYNTHETIC_TEST_DATA-EVENT",
    )


def test_crossref_and_europe_metadata_comparison() -> None:
    crossref = candidate_from_capture(
        "EVO-SEED-001",
        "EVO-SRC-001",
        capture(
            "crossref",
            {
                "message": {
                    "DOI": "10.1/SYNTHETIC_TEST_DATA",
                    "title": ["Synthetic: Test Data"],
                    "author": [{"given": "Synthetic", "family": "Test Data"}],
                    "container-title": ["Synthetic Journal"],
                    "published": {"date-parts": [[2026]]},
                }
            },
        ),
    )
    europe = candidate_from_capture(
        "EVO-SEED-001",
        "EVO-SRC-001",
        capture(
            "europe_pmc",
            {
                "resultList": {
                    "result": [
                        {
                            "doi": "10.1/synthetic_test_data",
                            "title": "Synthetic Test Data",
                            "authorString": "Synthetic Test Data",
                            "journalTitle": "Synthetic Journal",
                            "pubYear": "2026",
                        }
                    ]
                }
            },
        ),
    )
    rows = compare_candidates(crossref, europe)
    classes = {row.field_name: row.classification for row in rows}
    assert classes["doi"] == "exact_agreement"
    assert classes["title"] == "formatting_only_difference"
    assert classes["publication_year"] == "exact_agreement"


def test_material_title_and_author_conflicts() -> None:
    first = candidate_from_capture(
        "EVO-SEED-001",
        "EVO-SRC-001",
        capture(
            "crossref",
            {
                "message": {
                    "DOI": "10.1/SYNTHETIC_TEST_DATA",
                    "title": ["SYNTHETIC TEST DATA A"],
                    "author": [{"family": "A"}],
                }
            },
        ),
    )
    second = candidate_from_capture(
        "EVO-SEED-001",
        "EVO-SRC-001",
        capture(
            "europe_pmc",
            {
                "resultList": {
                    "result": [
                        {
                            "doi": "10.1/SYNTHETIC_TEST_DATA",
                            "title": "SYNTHETIC TEST DATA B",
                            "authorString": "B",
                        }
                    ]
                }
            },
        ),
    )
    classes = {row.field_name: row.classification for row in compare_candidates(first, second)}
    assert classes["title"] == "material_conflict" and classes["authors"] == "material_conflict"


def test_relevance_is_rule_based() -> None:
    status, rule = triage(
        "SYNTHETIC_TEST_DATA taniborbactam metallo enzymes",
        "taniborbactam activity across metallo enzymes",
    )
    assert status == "likely_relevant" and rule.startswith("keyword-overlap-v1")


def test_contact_email_preflight(monkeypatch) -> None:
    monkeypatch.delenv("EVOMBL_CONTACT_EMAIL", raising=False)
    result = CliRunner().invoke(app, ["preflight-metadata-retrieval"])
    assert result.exit_code == 1 and "EVOMBL_CONTACT_EMAIL" in result.output
    offline = CliRunner().invoke(app, ["preflight-metadata-retrieval", "--offline"])
    assert offline.exit_code == 0
