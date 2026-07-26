DROP VIEW source_provenance_chain;
DROP INDEX retrieval_source_idx;
ALTER TABLE source_retrieval_events RENAME TO source_retrieval_events_v2;
CREATE TABLE source_retrieval_events(retrieval_id VARCHAR PRIMARY KEY, source_id VARCHAR NOT NULL, provider VARCHAR NOT NULL, accessed_at TIMESTAMP NOT NULL, outcome VARCHAR NOT NULL, response_hash VARCHAR, response_path VARCHAR, error_type VARCHAR, error_message VARCHAR);
INSERT INTO source_retrieval_events SELECT retrieval_id,source_id,provider,accessed_at,outcome,response_hash,response_path,error_type,error_message FROM source_retrieval_events_v2;
DROP TABLE source_retrieval_events_v2;
CREATE INDEX retrieval_source_idx ON source_retrieval_events(source_id,accessed_at);
CREATE TABLE source_revisions(revision_id VARCHAR PRIMARY KEY, source_id VARCHAR NOT NULL REFERENCES evidence_sources(source_id), predecessor_revision_id VARCHAR REFERENCES source_revisions(revision_id), previous_content_hash VARCHAR, new_content_hash VARCHAR NOT NULL, revision_reason VARCHAR NOT NULL, detected_at TIMESTAMP NOT NULL, actor VARCHAR NOT NULL, retrieval_event_id VARCHAR NOT NULL REFERENCES source_retrieval_events(retrieval_id), verification_status VARCHAR NOT NULL, notes VARCHAR);
CREATE VIEW source_provenance_chain AS SELECT s.source_id,i.scheme,i.value,r.provider,r.accessed_at,r.response_hash FROM evidence_sources s LEFT JOIN source_identifiers i USING(source_id) LEFT JOIN source_retrieval_events r USING(source_id);
DROP VIEW biochemical_measurement_matrix;
DROP VIEW microbiological_measurement_matrix;
DROP VIEW unresolved_measurement_conflicts;
DROP VIEW excluded_records_audit;
ALTER TABLE measurements RENAME TO measurements_v2;
CREATE TABLE measurements (
  internal_measurement_id VARCHAR PRIMARY KEY,
  compound_id VARCHAR NOT NULL REFERENCES compounds(internal_compound_id),
  assay_id VARCHAR NOT NULL REFERENCES assays(internal_assay_id),
  evidence_source_id VARCHAR NOT NULL REFERENCES evidence_sources(source_id),
  source_location_id VARCHAR NOT NULL REFERENCES source_locations(location_id),
  endpoint_type VARCHAR NOT NULL,
  original_value DOUBLE NOT NULL,
  original_units VARCHAR NOT NULL,
  relation VARCHAR NOT NULL,
  exclusion_status VARCHAR NOT NULL,
  record_json JSON NOT NULL,
  record_hash VARCHAR NOT NULL
);
INSERT INTO measurements SELECT internal_measurement_id,compound_id,assay_id,evidence_source_id,source_location_id,endpoint_type,original_value,original_units,relation,exclusion_status,record_json,sha256(CAST(record_json AS VARCHAR)) FROM measurements_v2;
CREATE INDEX measurements_matrix_idx ON measurements(compound_id,assay_id,endpoint_type);
CREATE VIEW biochemical_measurement_matrix AS SELECT m.compound_id,a.enzyme_variant_id,m.endpoint_type,m.original_value,m.original_units FROM measurements m JOIN assays a ON m.assay_id=a.internal_assay_id WHERE json_extract_string(a.record_json,'$.assay_category')='BIOCHEMICAL';
CREATE VIEW microbiological_measurement_matrix AS SELECT m.compound_id,a.enzyme_variant_id,m.endpoint_type,m.original_value,m.original_units FROM measurements m JOIN assays a ON m.assay_id=a.internal_assay_id WHERE json_extract_string(a.record_json,'$.assay_category')='MICROBIOLOGICAL';
CREATE VIEW unresolved_measurement_conflicts AS SELECT compound_id,assay_id,endpoint_type,count(*) record_count FROM measurements GROUP BY ALL HAVING count(DISTINCT concat(relation,original_value,original_units))>1;
CREATE VIEW excluded_records_audit AS SELECT * FROM measurements WHERE exclusion_status='excluded';
DROP TABLE measurements_v2;
