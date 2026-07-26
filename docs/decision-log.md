# Decision log

- EvoMBL selected as primary programme.
- Variant-aware inhibition selected over NDM-1-only QSAR.
- Public data sparsity acknowledged.
- Deep learning is not assumed to be appropriate.
- IMP escape variants selected as the primary initial problem.
- Experimental confirmation is required for claimed hits.
- IMP-78 excluded from the core panel pending source verification.
- Batch 2B evidence graphs require atomic insertion and precise source locations.
- Identical immutable captures are idempotent; changed content requires an explicit revision.
- Metadata retrieval remains separate from scientific verification.
- Schema version 3 rebuilds measurements to enforce source-location provenance with a database foreign key.
- Applied SQL migrations are immutable and checksum-validated.

Future entries must include date, decision owner, alternatives, evidence, rationale,
consequences, and review trigger.
