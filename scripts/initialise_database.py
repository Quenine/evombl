from pathlib import Path

from evombl.storage import initialize_database

initialize_database(Path("data/evombl.duckdb"))
