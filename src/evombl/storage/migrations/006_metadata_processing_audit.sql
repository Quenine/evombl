CREATE TABLE metadata_processing_events(
  processing_id VARCHAR PRIMARY KEY,
  retrieval_event_id VARCHAR NOT NULL REFERENCES source_retrieval_events(retrieval_id),
  candidate_id VARCHAR,
  provider VARCHAR NOT NULL,
  outcome VARCHAR NOT NULL,
  processed_at TIMESTAMP NOT NULL,
  normalizer_version VARCHAR NOT NULL,
  error_type VARCHAR,
  error_path VARCHAR,
  received_type VARCHAR,
  expected_type VARCHAR,
  error_message VARCHAR
);
CREATE INDEX metadata_processing_retrieval_idx ON metadata_processing_events(retrieval_event_id,processed_at);
