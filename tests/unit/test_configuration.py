from pathlib import Path

from evombl.configuration import validate_configuration


def test_configuration_is_valid() -> None:
    assert validate_configuration(Path("config")) == []
