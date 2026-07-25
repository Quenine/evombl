from dataclasses import dataclass


@dataclass(frozen=True)
class NumberingProvenance:
    author_scheme: str
    reference_sequence: str
    bbl_mapping_verified: bool = False
