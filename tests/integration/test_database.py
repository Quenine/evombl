from pathlib import Path

import duckdb
import pytest

from evombl.storage.database import initialize_database, verify_integrity


def test_database_schema_and_foreign_key_integrity(tmp_path: Path) -> None:
    database = tmp_path / "SYNTHETIC_TEST_DATA.duckdb"
    initialize_database(database)
    assert verify_integrity(database) == []
    with duckdb.connect(str(database)) as connection:
        with pytest.raises(duckdb.ConstraintException):
            connection.execute(
                """INSERT INTO assays VALUES
                ('SYNTHETIC_TEST_DATA-A','SYNTHETIC_TEST_DATA-MISSING',NULL,
                 'IC50','{}')"""
            )
