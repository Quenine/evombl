CREATE TABLE schema_migrations(version INTEGER PRIMARY KEY, name VARCHAR NOT NULL, checksum VARCHAR NOT NULL, applied_at TIMESTAMP NOT NULL DEFAULT current_timestamp);
