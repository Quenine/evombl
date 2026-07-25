def source_locator(source_id: str, location: str) -> str:
    if not source_id.strip() or not location.strip():
        raise ValueError("source ID and location are required")
    return f"{source_id}::{location}"
