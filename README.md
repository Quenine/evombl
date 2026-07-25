# EvoMBL

EvoMBL is a provenance-first research data platform for variant-resolved
metallo-beta-lactamase inhibitor discovery. This baseline deliberately contains no
predictive models and no asserted bioactivity, sequence, mutation, accession, structure,
patent, or literature records.

## Setup

```bash
uv sync --all-groups
uv run evombl validate-config
uv run evombl init-db
uv run evombl export-schemas
uv run ruff check .
uv run mypy
uv run pytest
```

See `docs/` for scientific governance and `data/README.md` for data handling.

