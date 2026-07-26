ALTER TABLE metadata_candidates ADD COLUMN logical_candidate_key VARCHAR;
ALTER TABLE metadata_candidates ADD COLUMN requested_identifier VARCHAR;
ALTER TABLE metadata_candidates ADD COLUMN normalization_version VARCHAR;
ALTER TABLE metadata_candidates ADD COLUMN normalization_version_hash VARCHAR;
ALTER TABLE metadata_candidates ADD COLUMN normalized_record_hash VARCHAR;
ALTER TABLE metadata_candidates ADD COLUMN semantic_bibliographic_hash VARCHAR;
ALTER TABLE metadata_candidates ADD COLUMN predecessor_candidate_id VARCHAR;
ALTER TABLE metadata_candidates ADD COLUMN candidate_status VARCHAR;
ALTER TABLE metadata_candidates ADD COLUMN manual_review_required BOOLEAN;
ALTER TABLE metadata_candidates ADD COLUMN created_at TIMESTAMP;

ALTER TABLE metadata_processing_events ADD COLUMN normalized_record_hash VARCHAR;
ALTER TABLE metadata_processing_events ADD COLUMN semantic_bibliographic_hash VARCHAR;
ALTER TABLE metadata_processing_events ADD COLUMN predecessor_candidate_id VARCHAR;

CREATE UNIQUE INDEX metadata_candidate_observation_idx
  ON metadata_candidates(logical_candidate_key,response_hash,normalization_version_hash);
CREATE INDEX metadata_candidate_version_idx
  ON metadata_candidates(logical_candidate_key,created_at,candidate_id);
