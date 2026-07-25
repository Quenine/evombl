import json
from pathlib import Path

from .hashing import sha256_file


def create_manifest(root: Path) -> dict[str, str]:
    files = sorted(path for path in root.rglob("*") if path.is_file() and ".git" not in path.parts)
    return {path.relative_to(root).as_posix(): sha256_file(path) for path in files}


def write_manifest(root: Path, output: Path) -> None:
    output.write_text(json.dumps(create_manifest(root), indent=2, sort_keys=True) + "\n")
