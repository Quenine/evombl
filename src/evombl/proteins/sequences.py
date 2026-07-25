import hashlib

AMINO_ACIDS = frozenset("ACDEFGHIKLMNPQRSTVWY")


def normalize_sequence(sequence: str) -> str:
    normalized = "".join(sequence.split()).upper()
    invalid = sorted(set(normalized) - AMINO_ACIDS)
    if not normalized or invalid:
        raise ValueError(f"Invalid amino-acid sequence; unsupported symbols: {invalid}")
    return normalized


def normalize_source_sequence(sequence: str) -> tuple[str, bool]:
    compact = "".join(sequence.split()).upper()
    had_stop = compact.endswith("*")
    if "*" in compact[:-1]:
        raise ValueError("stop character is only permitted at the source terminus")
    normalized = normalize_sequence(compact.removesuffix("*"))
    return normalized, had_stop


def sequence_hash(sequence: str) -> str:
    return hashlib.sha256(normalize_sequence(sequence).encode("ascii")).hexdigest()


def mature_sequence(sequence: str, signal_start: int, signal_end: int) -> str:
    normalized = normalize_sequence(sequence)
    if signal_start != 1 or not 1 <= signal_end < len(normalized):
        raise ValueError("signal peptide coordinates must be 1-based and within the sequence")
    return normalized[signal_end:]
