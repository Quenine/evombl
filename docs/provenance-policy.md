# Provenance policy

Every scientific assertion must resolve to an evidence source and precise location.
Downloaded files are content-hashed; access date, licence, database version, and record ID
are retained where applicable. Raw evidence is immutable. Corrections create curation
events rather than overwriting history. Releases are content-addressed manifests and are
reproducible from committed code, configuration, and permitted source data.

No accession, mutation, structure ID, measurement, or bibliographic fact may be inferred
to fill a gap. Collaborator data retain protocol, batch, operator, control, deviation, raw
path, analysis version, and signed-report lineage.

Official-API responses use content-addressed SHA-256 paths. Provider/identifier indexes select the latest captured revision for deterministic offline reuse; prior captures are never overwritten. Retrieval metadata is not a verified scientific assertion. Malformed or unsuccessful responses are not retained as valid captures.

Changed valid content creates a new immutable capture and must be represented by a `SourceRevisionRecord`. Retrieval events distinguish success, HTTP failure, timeout, malformed response, and offline cache miss; failure events never carry the meaning of a valid source capture.
## Bibliographic provider records

Crossref, Europe PMC, and PubMed responses must enter through immutable captures, one retrieval event per request, and revision-preserving response hashes. Original provider values and discrepancies are retained. Open-access and licence claims must be explicitly provider-supported; unknown remains null.
