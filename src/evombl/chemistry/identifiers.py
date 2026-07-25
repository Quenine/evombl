import hashlib


def deterministic_compound_id(parent_inchikey: str) -> str:
    digest = hashlib.sha256(parent_inchikey.encode("ascii")).hexdigest()[:16]
    return f"EVO-CMP-{digest.upper()}"
