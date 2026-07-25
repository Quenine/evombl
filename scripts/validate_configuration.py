from pathlib import Path

from evombl.configuration import validate_configuration

errors = validate_configuration(Path("config"))
if errors:
    raise SystemExit("\n".join(errors))
print("Configuration valid")
