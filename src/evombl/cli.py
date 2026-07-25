import json
from pathlib import Path

import typer
from pydantic import BaseModel

from evombl.chemistry.standardize import standardize_smiles
from evombl.configuration import validate_configuration
from evombl.domain import (
    AssayRecord,
    CompoundRecord,
    EvidenceSourceRecord,
    ExperimentalBatchRecord,
    MeasurementRecord,
    ProteinVariantRecord,
)
from evombl.proteins.sequences import normalize_sequence, sequence_hash
from evombl.provenance.manifests import write_manifest
from evombl.storage.database import (
    initialize_database,
    verify_integrity,
)
from evombl.storage.database import (
    migrate as run_migrations,
)
from evombl.storage.database import (
    schema_version as read_schema_version,
)

app = typer.Typer(help="EvoMBL evidence infrastructure.")


@app.command("migrate")
def migrate(path: Path = Path("data/evombl.duckdb")) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    typer.echo(f"Schema version {run_migrations(path)}")


@app.command("schema-version")
def schema_version(path: Path = Path("data/evombl.duckdb")) -> None:
    typer.echo(read_schema_version(path))


@app.command("verify-evidence-graph")
def verify_evidence_graph(path: Path = Path("data/evombl.duckdb")) -> None:
    verify_data(path)


@app.command("init-db")
def init_db(path: Path = Path("data/evombl.duckdb")) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    initialize_database(path)
    typer.echo(f"Initialized {path}")


@app.command("validate-config")
def validate_config(config_dir: Path = Path("config")) -> None:
    errors = validate_configuration(config_dir)
    if errors:
        for error in errors:
            typer.echo(error, err=True)
        raise typer.Exit(1)
    typer.echo("Configuration valid")


@app.command("validate-compound")
def validate_compound(smiles: str) -> None:
    typer.echo(json.dumps(standardize_smiles(smiles).__dict__, indent=2))


@app.command("validate-protein")
def validate_protein(sequence: str) -> None:
    normalized = normalize_sequence(sequence)
    typer.echo(json.dumps({"length": len(normalized), "sha256": sequence_hash(normalized)}))


@app.command("export-schemas")
def export_schemas(output_dir: Path = Path("schemas")) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    models: dict[str, type[BaseModel]] = {
        "compound": CompoundRecord,
        "protein_variant": ProteinVariantRecord,
        "assay": AssayRecord,
        "measurement": MeasurementRecord,
        "evidence_source": EvidenceSourceRecord,
        "experimental_batch": ExperimentalBatchRecord,
    }
    for name, model in models.items():
        target = output_dir / f"{name}.schema.json"
        target.write_text(json.dumps(model.model_json_schema(), indent=2) + "\n", encoding="utf-8")
    typer.echo(f"Exported {len(models)} schemas")


@app.command("verify-data")
def verify_data(path: Path = Path("data/evombl.duckdb")) -> None:
    errors = verify_integrity(path)
    if errors:
        for error in errors:
            typer.echo(error, err=True)
        raise typer.Exit(1)
    typer.echo("Data integrity valid")


@app.command("create-manifest")
def create_manifest(root: Path = Path("."), output: Path = Path("manifest.json")) -> None:
    write_manifest(root.resolve(), output.resolve())
    typer.echo(f"Wrote {output}")
