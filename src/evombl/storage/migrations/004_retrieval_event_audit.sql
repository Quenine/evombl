DROP VIEW source_provenance_chain;
DROP INDEX retrieval_source_idx;
CREATE TEMP TABLE source_revisions_backup AS SELECT * FROM source_revisions;
DROP TABLE source_revisions;
ALTER TABLE source_retrieval_events RENAME TO source_retrieval_events_v3;
CREATE TABLE source_retrieval_events(
  retrieval_id VARCHAR PRIMARY KEY,
  source_id VARCHAR NOT NULL REFERENCES evidence_sources(source_id),
  provider VARCHAR NOT NULL,
  requested_identifier VARCHAR NOT NULL,
  request_timestamp TIMESTAMP NOT NULL,
  completion_timestamp TIMESTAMP NOT NULL,
  outcome VARCHAR NOT NULL,
  http_status INTEGER,
  attempt_count INTEGER NOT NULL CHECK(attempt_count > 0),
  response_hash VARCHAR,
  response_path VARCHAR,
  error_type VARCHAR,
  error_message VARCHAR,
  offline BOOLEAN NOT NULL,
  adapter_version VARCHAR NOT NULL,
  configuration_version VARCHAR NOT NULL
);
INSERT INTO source_retrieval_events SELECT retrieval_id,source_id,provider,provider,accessed_at,accessed_at,outcome,NULL,1,response_hash,response_path,error_type,error_message,false,'legacy','legacy' FROM source_retrieval_events_v3;
DROP TABLE source_retrieval_events_v3;
CREATE TABLE source_revisions(revision_id VARCHAR PRIMARY KEY,source_id VARCHAR NOT NULL REFERENCES evidence_sources(source_id),predecessor_revision_id VARCHAR REFERENCES source_revisions(revision_id),previous_content_hash VARCHAR,new_content_hash VARCHAR NOT NULL,revision_reason VARCHAR NOT NULL,detected_at TIMESTAMP NOT NULL,actor VARCHAR NOT NULL,retrieval_event_id VARCHAR NOT NULL REFERENCES source_retrieval_events(retrieval_id),verification_status VARCHAR NOT NULL,notes VARCHAR);
INSERT INTO source_revisions SELECT * FROM source_revisions_backup;
DROP TABLE source_revisions_backup;
CREATE INDEX retrieval_source_idx ON source_retrieval_events(source_id,request_timestamp);
CREATE VIEW source_provenance_chain AS SELECT s.source_id,i.scheme,i.value,r.provider,r.request_timestamp AS accessed_at,r.response_hash,v.revision_id,v.previous_content_hash,v.new_content_hash FROM evidence_sources s LEFT JOIN source_identifiers i USING(source_id) LEFT JOIN source_retrieval_events r USING(source_id) LEFT JOIN source_revisions v ON v.retrieval_event_id=r.retrieval_id;
