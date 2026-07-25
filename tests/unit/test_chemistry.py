import pytest

from evombl.chemistry.identifiers import deterministic_compound_id
from evombl.chemistry.standardize import InvalidSmilesError, standardize_smiles


def test_identifier_and_stereochemistry_are_deterministic() -> None:
    first = standardize_smiles("C[C@H](O)F")
    second = standardize_smiles("C[C@H](O)F")
    assert first.isomeric_smiles == second.isomeric_smiles
    assert "@" in first.isomeric_smiles
    assert deterministic_compound_id(first.parent_inchikey) == deterministic_compound_id(
        second.parent_inchikey
    )


def test_salt_source_is_preserved_and_parent_is_separate() -> None:
    result = standardize_smiles("CC(=O)[O-].[Na+]")
    assert "." in result.isomeric_smiles
    assert result.fragment_count == 2
    assert result.parent_smiles != result.isomeric_smiles
    assert result.transformations == ("select_largest_fragment_as_parent",)


@pytest.mark.parametrize("smiles", ["[13CH3]CO", "C.C"])
def test_isotopes_and_disconnected_structures_are_accepted(smiles: str) -> None:
    assert standardize_smiles(smiles).original_smiles == smiles


def test_invalid_smiles_is_rejected() -> None:
    with pytest.raises(InvalidSmilesError):
        standardize_smiles("not-a-smiles")
