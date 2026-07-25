from dataclasses import dataclass

from .sequences import normalize_sequence


@dataclass(frozen=True)
class SequenceDifference:
    position: int
    reference_residue: str
    alternate_residue: str


def compare_to_reference(sequence: str, reference_sequence: str | None) -> list[SequenceDifference]:
    if reference_sequence is None:
        raise ValueError("an explicit reference sequence is required")
    query = normalize_sequence(sequence)
    reference = normalize_sequence(reference_sequence)
    if len(query) != len(reference):
        raise ValueError("simple substitution comparison requires equal-length sequences")
    return [
        SequenceDifference(i, ref, alt)
        for i, (ref, alt) in enumerate(zip(reference, query, strict=True), start=1)
        if ref != alt
    ]
