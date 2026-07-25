CREATE TABLE IF NOT EXISTS evidence_sources (
  source_id VARCHAR PRIMARY KEY,
  source_type VARCHAR NOT NULL,
  record_json JSON NOT NULL
);
CREATE TABLE IF NOT EXISTS compounds (
  internal_compound_id VARCHAR PRIMARY KEY,
  source_record_id VARCHAR NOT NULL,
  original_smiles VARCHAR NOT NULL,
  record_json JSON NOT NULL
);
CREATE TABLE IF NOT EXISTS protein_variants (
  internal_variant_id VARCHAR PRIMARY KEY,
  variant_name VARCHAR NOT NULL,
  sequence_hash VARCHAR NOT NULL,
  record_json JSON NOT NULL
);
CREATE TABLE IF NOT EXISTS assays (
  internal_assay_id VARCHAR PRIMARY KEY,
  source_id VARCHAR NOT NULL REFERENCES evidence_sources(source_id),
  enzyme_variant_id VARCHAR REFERENCES protein_variants(internal_variant_id),
  endpoint_type VARCHAR NOT NULL,
  record_json JSON NOT NULL
);
CREATE TABLE IF NOT EXISTS measurements (
  internal_measurement_id VARCHAR PRIMARY KEY,
  compound_id VARCHAR NOT NULL REFERENCES compounds(internal_compound_id),
  assay_id VARCHAR NOT NULL REFERENCES assays(internal_assay_id),
  evidence_source_id VARCHAR NOT NULL REFERENCES evidence_sources(source_id),
  endpoint_type VARCHAR NOT NULL,
  original_value DOUBLE NOT NULL,
  original_units VARCHAR NOT NULL,
  relation VARCHAR NOT NULL,
  exclusion_status VARCHAR NOT NULL,
  record_json JSON NOT NULL
);
CREATE TABLE IF NOT EXISTS experimental_batches (
  batch_id VARCHAR PRIMARY KEY,
  record_json JSON NOT NULL
);
CREATE TABLE IF NOT EXISTS curation_events (
  event_id VARCHAR PRIMARY KEY,
  entity_type VARCHAR NOT NULL,
  entity_id VARCHAR NOT NULL,
  event_type VARCHAR NOT NULL,
  occurred_at TIMESTAMP NOT NULL,
  actor VARCHAR NOT NULL,
  details_json JSON NOT NULL
);
CREATE TABLE IF NOT EXISTS data_releases (
  release_id VARCHAR PRIMARY KEY,
  created_at TIMESTAMP NOT NULL,
  manifest_hash VARCHAR NOT NULL,
  manifest_json JSON NOT NULL
);

