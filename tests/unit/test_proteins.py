import pytest

from evombl.proteins.mutations import compare_to_reference
from evombl.proteins.sequences import sequence_hash


def test_exact_sequence_hash_is_deterministic() -> None:
    assert sequence_hash("ACDE") == sequence_hash("ACDE")


def test_comparison_requires_explicit_reference() -> None:
    with pytest.raises(ValueError, match="explicit reference"):
        compare_to_reference("ACDE", None)
    differences = compare_to_reference("ACNE", "ACDE")
    assert differences[0].position == 3
    assert differences[0].reference_residue == "D"
