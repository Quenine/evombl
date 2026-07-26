from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict

from evombl.ingestion.rate_limit import load_rate_limits

EXPECTED_VARIANTS = {
    "IMP-1",
    "IMP-6",
    "IMP-10",
    "IMP-14",
    "IMP-26",
    "IMP-59",
    "NDM-1",
    "NDM-9",
    "NDM-30",
    "VIM-2",
    "VIM-83",
}


class MetadataRetrievalPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    enabled: bool
    official_apis_only: bool
    preserve_raw_captures: bool
    permit_scientific_promotion: bool
    permit_activity_ingestion: bool
    permit_pdf_download: bool
    permit_publisher_scraping: bool
    policy_version: str


def load_metadata_policy(config_dir: Path) -> MetadataRetrievalPolicy:
    return MetadataRetrievalPolicy.model_validate(
        load_yaml(config_dir / "sources.yaml").get("metadata_retrieval")
    )


def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a mapping")
    return value


def validate_configuration(config_dir: Path) -> list[str]:
    errors: list[str] = []
    variants = load_yaml(config_dir / "variants.yaml").get("variants")
    if not isinstance(variants, list):
        return ["variants.yaml: variants must be a list"]
    names = {entry.get("variant_name") for entry in variants if isinstance(entry, dict)}
    if names != EXPECTED_VARIANTS:
        errors.append("variants.yaml must contain exactly the provisional panel")
    required = {
        "enabled",
        "family",
        "variant_name",
        "research_role",
        "verification_status",
        "priority",
        "notes",
    }
    for index, entry in enumerate(variants):
        if not isinstance(entry, dict) or set(entry) != required:
            errors.append(f"variants.yaml entry {index} has invalid fields")
            continue
        if entry["verification_status"] != "identity_pending_verification":
            errors.append(f"{entry['variant_name']}: identity must remain pending")
    endpoints = load_yaml(config_dir / "endpoints.yaml").get("endpoints")
    if not isinstance(endpoints, dict) or len(endpoints) != 14:
        errors.append("endpoints.yaml must define all 14 distinct endpoint types")
    try:
        policy = load_metadata_policy(config_dir)
        if not policy.enabled or not policy.official_apis_only or not policy.preserve_raw_captures:
            errors.append("metadata retrieval must use immutable official-API captures")
        if (
            policy.permit_scientific_promotion
            or policy.permit_activity_ingestion
            or policy.permit_pdf_download
            or policy.permit_publisher_scraping
        ):
            errors.append("metadata retrieval policy enables a prohibited capability")
    except Exception as exc:
        errors.append(f"sources.yaml metadata policy: {exc}")
    seeds = load_yaml(config_dir / "seed_sources.yaml").get("sources")
    if not isinstance(seeds, list) or len(seeds) != 8:
        errors.append("seed_sources.yaml must contain exactly eight candidates")
    elif len({entry.get("seed_id") for entry in seeds}) != 8:
        errors.append("seed source IDs must be unique")
    try:
        load_rate_limits(config_dir / "source_rate_limits.yaml")
    except Exception as exc:
        errors.append(f"source_rate_limits.yaml: {exc}")
    return errors
