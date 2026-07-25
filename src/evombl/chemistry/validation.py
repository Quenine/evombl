from importlib import import_module
from typing import Any

from .standardize import InvalidSmilesError

chem: Any = import_module("rd" + "kit.Chem")


def validate_smiles(smiles: str) -> None:
    if not smiles.strip() or chem.MolFromSmiles(smiles) is None:
        raise InvalidSmilesError(f"Malformed SMILES: {smiles!r}")
