from dataclasses import dataclass
from typing import Any

import pint

ureg: Any = pint.UnitRegistry()
ALIASES = {
    "M": "mole/liter",
    "mM": "millimole/liter",
    "µM": "micromole/liter",
    "uM": "micromole/liter",
    "nM": "nanomole/liter",
    "pM": "picomole/liter",
    "mg/L": "milligram/liter",
    "µg/mL": "microgram/milliliter",
    "ug/mL": "microgram/milliliter",
}
CANONICAL = {
    "M": "M",
    "mM": "mM",
    "µM": "µM",
    "uM": "µM",
    "nM": "nM",
    "pM": "pM",
    "mg/L": "mg/L",
    "µg/mL": "µg/mL",
    "ug/mL": "µg/mL",
}
CONVERSION_VERSION = "evombl-units-v1"


@dataclass(frozen=True)
class UnitConversion:
    original_value: float
    original_units: str
    standard_value: float
    standard_units: str
    conversion_rule: str


def convert(value: float, source: str, target: str) -> UnitConversion:
    if source not in ALIASES or target not in ALIASES:
        raise ValueError("uncontrolled unit")
    try:
        magnitude = (value * ureg(ALIASES[source])).to(ALIASES[target]).magnitude
    except pint.DimensionalityError as exc:
        raise ValueError("incompatible unit dimensions") from exc
    return UnitConversion(value, source, float(magnitude), CANONICAL[target], CONVERSION_VERSION)


def reverse(conversion: UnitConversion) -> float:
    return convert(
        conversion.standard_value, conversion.standard_units, conversion.original_units
    ).standard_value
