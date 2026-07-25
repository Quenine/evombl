from pathlib import Path

from typer.testing import CliRunner

from evombl.cli import app

result = CliRunner().invoke(app, ["export-schemas", "--output-dir", str(Path("schemas"))])
if result.exit_code:
    raise SystemExit(result.output)
print(result.output, end="")
