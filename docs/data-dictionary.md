# Data dictionary

The canonical machine-readable definitions are the Pydantic models in `src/evombl/domain`
and their exported JSON Schemas in `schemas/`. Identifiers prefixed `internal_` are stable
EvoMBL identifiers; source identifiers remain separately preserved. Raw/original fields
are source assertions, standard fields are rule-derived, and transformed fields require a
complete `transform_definition`. Null means unknown or not applicable; it never means zero.

Assays define experimental context. Measurements point to exactly one assay, compound, and
evidence source. Protein mutations carry author numbering and an explicit reference;
standard BBL numbering is populated only after verification.

