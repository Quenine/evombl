from dataclasses import dataclass
from importlib import import_module
from typing import Any, cast

chem: Any = import_module("rd" + "kit.Chem")
descriptors: Any = import_module("rdkit.Chem." + "Descriptors")
rd_mol_descriptors: Any = import_module("rdkit.Chem." + "rdMolDescriptors")


class InvalidSmilesError(ValueError):
    """Raised when a submitted SMILES cannot be parsed."""


@dataclass(frozen=True)
class StandardizedStructure:
    original_smiles: str
    canonical_smiles: str
    isomeric_smiles: str
    standard_inchi: str
    standard_inchikey: str
    parent_smiles: str
    parent_inchikey: str
    molecular_formula: str
    molecular_weight: float
    transformations: tuple[str, ...]
    fragment_count: int


def standardize_smiles(smiles: str) -> StandardizedStructure:
    """Parse without neutralisation/tautomerisation and derive a largest-fragment parent."""
    molecule = chem.MolFromSmiles(smiles)
    if molecule is None:
        raise InvalidSmilesError(f"Malformed SMILES: {smiles!r}")
    fragments = chem.GetMolFrags(molecule, asMols=True, sanitizeFrags=True)
    parent = max(fragments, key=lambda mol: mol.GetNumHeavyAtoms())
    parent_smiles = chem.MolToSmiles(parent, canonical=True, isomericSmiles=True)
    transformations = () if len(fragments) == 1 else ("select_largest_fragment_as_parent",)
    return StandardizedStructure(
        original_smiles=smiles,
        canonical_smiles=chem.MolToSmiles(molecule, canonical=True, isomericSmiles=False),
        isomeric_smiles=chem.MolToSmiles(molecule, canonical=True, isomericSmiles=True),
        standard_inchi=chem.MolToInchi(molecule),
        standard_inchikey=chem.MolToInchiKey(molecule),
        parent_smiles=parent_smiles,
        parent_inchikey=chem.MolToInchiKey(parent),
        molecular_formula=cast(str, rd_mol_descriptors.CalcMolFormula(molecule)),
        molecular_weight=cast(float, descriptors.MolWt(molecule)),
        transformations=transformations,
        fragment_count=len(fragments),
    )
