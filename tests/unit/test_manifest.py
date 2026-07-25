from pathlib import Path

from evombl.provenance.manifests import create_manifest


def test_manifest_is_reproducible(tmp_path: Path) -> None:
    path = tmp_path / "SYNTHETIC_TEST_DATA.txt"
    path.write_text("SYNTHETIC_TEST_DATA", encoding="utf-8")
    assert create_manifest(tmp_path) == create_manifest(tmp_path)
