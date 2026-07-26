# Curation protocol

1. Register the source and immutable file hash before extraction.
2. Preserve author values, units, relations, endpoint labels, and exact locations.
3. Create derived standard values only under a versioned, reversible rule.
4. Verify compound identity, variant identity, numbering scheme, and assay context
   independently; uncertainty is recorded, never guessed.
5. Group possible duplicates deterministically. Conflicts are reported and never averaged
   automatically.
6. Retain censored values and exclusions. A second curator verifies records used for
   consequential analysis.

Endpoint types remain separate. Cross-endpoint conversion or pooling requires an explicit
scientific decision recorded in the decision log.

## Batch 2B persistence controls

Scientific records are inserted through fixed-SQL typed repositories. An identical immutable record is idempotent; changed content under the same identifier is rejected and requires a curation event or explicit revision. Complete evidence graphs are committed in one transaction. Measurements require structured source locations, assay endpoints must agree exactly, and variant sequences must link to their source.

Official adapters apply provider-specific rate policies with bounded retries. NCBI API-key and no-key modes have distinct request intervals. Retry-After is honored without treating the response as evidence.
## Batch 2C1 bibliographic gate

Official API metadata is bibliographic evidence, not scientific verification. Purpose relevance remains provisional until lawful full-text review. Identifier conflicts stay visible and require manual adjudication; no bioactivity extraction, variant verification, or scientific promotion is permitted in this stage.
