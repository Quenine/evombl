from pathlib import Path
from typing import Any

import yaml

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
    sources = load_yaml(config_dir / "sources.yaml")
    if sources.get("retrieval_implemented") is not False:
        errors.append("source retrieval must remain disabled in this baseline")
    try:
        load_rate_limits(config_dir / "source_rate_limits.yaml")
    except Exception as exc:
        errors.append(f"source_rate_limits.yaml: {exc}")
    return errors
