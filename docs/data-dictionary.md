# Data dictionary

The canonical machine-readable definitions are the Pydantic models in `src/evombl/domain`
and their exported JSON Schemas in `schemas/`. Identifiers prefixed `internal_` are stable
EvoMBL identifiers; source identifiers remain separately preserved. Raw/original fields
are source assertions, standard fields are rule-derived, and transformed fields require a
complete `transform_definition`. Null means unknown or not applicable; it never means zero.

Assays define experimental context. Measurements point to exactly one assay, compound, and
evidence source. Protein mutations carry author numbering and an explicit reference;
standard BBL numbering is populated only after verification.

Batch 2B relational entities include source documents, immutable source files, structured locations and identifiers, retrieval events, aliases, accessions, sequences, mutation observations, numbering mappings, structures and chains, protocols, assay conditions, curation events, and releases. JSON snapshots are deterministic; matrix and provenance fields remain relationally queryable.

Schema version 3 rebuilds measurements with a mandatory foreign key to `source_locations` and a deterministic immutable `record_hash`. Applied migration files are identified by SHA-256 checksums; changed applied files are rejected.
## Batch 2C1 tables

- `seed_source_registry`: stable DOI/PMID-independent seed identity mapped to an evidence source and provisional request.
- `metadata_candidates`: immutable normalized candidate plus original provider values, response hash, and retrieval-event link.
- `metadata_comparisons`: deterministic field-level agreement or conflict records.
- `bibliographic_audits`: derived bibliographic status, relevance triage, legal-access state, and manual-review flag; it does not alter scientific verification status.
