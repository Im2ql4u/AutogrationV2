"""Canonical data contract.

Results use Autogration's per-task Parquet layout (``GET /runs/{task_id}/results/parquet``):
one row per equipment x property x timestep. Cases and entities are small side tables.
"""

from __future__ import annotations

import math
import re
from typing import NamedTuple

RESULT_COLUMNS: dict[str, str] = {
    "module": "VARCHAR",
    "system": "VARCHAR",
    "identifier": "VARCHAR",
    "identifier_type": "VARCHAR",
    "timestamp": "DATE",
    "run_number": "INTEGER",
    "property_name": "VARCHAR",
    "value": "DOUBLE",
    "unit": "VARCHAR",
}

# cases.csv: one row per case (= Autogration task / assumption case). Extra columns are assumption axes.
CASE_REQUIRED = ["run_number", "case_name"]
CASE_RESERVED = {"run_number", "case_name", "task_id", "status", "is_baseline", "description"}

# entities.csv: one row per result identifier. Extra columns become `entity.<column>` dimensions.
ENTITY_REQUIRED = ["identifier"]
ENTITY_RESERVED = {"identifier", "identifier_type"}

COMPLETED = "Completed"

# GAP/RESOLVE write 3.4e+35 for "no value".
SENTINEL_ABS = 1e35

SM3_PER_BBL = 0.158987294928
# 1 scf as 1 ft3; the slightly different reference conditions of scf (60 degF) and Sm3 (15 degC)
# are ignored, as in most field conversions.
SM3_PER_SCF = 0.028316846592
BAR_PER_PSI = 0.0689475729


class SiConversion(NamedTuple):
    """SI value = native value x factor + offset."""

    si_unit: str | None
    factor: float
    offset: float = 0.0
    known: bool = True


_C = SiConversion

# Native unit -> SI unit used by measures. Mirrors the frontend's results/engine/units.ts.
# Gauge and absolute pressure stay apart (psig -> barg, never bara): converting needs the
# ambient pressure, which results do not carry. Spellings not listed here go through
# ``to_si``'s normaliser: a leading multiplier ("1000", "1E3", "e3", "10^3"), any case,
# any whitespace, and "/day" read as "/d".
UNIT_TO_SI: dict[str, SiConversion] = {
    "Sm3/day": _C("Sm3/d", 1.0),
    "Sm3/d": _C("Sm3/d", 1.0),
    "sm3/d": _C("Sm3/d", 1.0),
    "kSm3/day": _C("Sm3/d", 1e3),
    "kSm3/d": _C("Sm3/d", 1e3),
    # GAP writes gas rates as 1000Sm3/d.
    "1000Sm3/day": _C("Sm3/d", 1e3),
    "1000Sm3/d": _C("Sm3/d", 1e3),
    "MSm3/day": _C("Sm3/d", 1e6),
    "MSm3/d": _C("Sm3/d", 1e6),
    "MMSm3/day": _C("Sm3/d", 1e6),
    "MMSm3/d": _C("Sm3/d", 1e6),
    "STB/day": _C("Sm3/d", SM3_PER_BBL),
    "STB/d": _C("Sm3/d", SM3_PER_BBL),
    "stb/day": _C("Sm3/d", SM3_PER_BBL),
    "stb/d": _C("Sm3/d", SM3_PER_BBL),
    "bbl/day": _C("Sm3/d", SM3_PER_BBL),
    "bbl/d": _C("Sm3/d", SM3_PER_BBL),
    "MSTB/day": _C("Sm3/d", SM3_PER_BBL * 1e3),
    "MSTB/d": _C("Sm3/d", SM3_PER_BBL * 1e3),
    "Mbbl/day": _C("Sm3/d", SM3_PER_BBL * 1e3),
    "Mbbl/d": _C("Sm3/d", SM3_PER_BBL * 1e3),
    "scf/day": _C("Sm3/d", SM3_PER_SCF),
    "scf/d": _C("Sm3/d", SM3_PER_SCF),
    "Mscf/day": _C("Sm3/d", SM3_PER_SCF * 1e3),
    "Mscf/d": _C("Sm3/d", SM3_PER_SCF * 1e3),
    "MMscf/day": _C("Sm3/d", SM3_PER_SCF * 1e6),
    "MMscf/d": _C("Sm3/d", SM3_PER_SCF * 1e6),
    "Sm3": _C("Sm3", 1.0),
    "kSm3": _C("Sm3", 1e3),
    "1000Sm3": _C("Sm3", 1e3),
    "MSm3": _C("Sm3", 1e6),
    "MMSm3": _C("Sm3", 1e6),
    "GSm3": _C("Sm3", 1e9),
    "STB": _C("Sm3", SM3_PER_BBL),
    "stb": _C("Sm3", SM3_PER_BBL),
    "bbl": _C("Sm3", SM3_PER_BBL),
    "MSTB": _C("Sm3", SM3_PER_BBL * 1e3),
    "Mbbl": _C("Sm3", SM3_PER_BBL * 1e3),
    "MMSTB": _C("Sm3", SM3_PER_BBL * 1e6),
    "MMbbl": _C("Sm3", SM3_PER_BBL * 1e6),
    "scf": _C("Sm3", SM3_PER_SCF),
    "Mscf": _C("Sm3", SM3_PER_SCF * 1e3),
    "MMscf": _C("Sm3", SM3_PER_SCF * 1e6),
    "Bscf": _C("Sm3", SM3_PER_SCF * 1e9),
    "BARa": _C("bara", 1.0),
    "bara": _C("bara", 1.0),
    "bar": _C("bar", 1.0),
    "BARg": _C("barg", 1.0),
    "barg": _C("barg", 1.0),
    "psia": _C("bara", BAR_PER_PSI),
    "psig": _C("barg", BAR_PER_PSI),
    "deg C": _C("degC", 1.0),
    "degC": _C("degC", 1.0),
    "deg F": _C("degC", 5 / 9, -32 * 5 / 9),
    "degF": _C("degC", 5 / 9, -32 * 5 / 9),
    "percent": _C("%", 1.0),
    "%": _C("%", 1.0),
    "fraction": _C("%", 100.0),
    "Sm3/Sm3": _C("Sm3/Sm3", 1.0),
    "kg/s": _C("kg/s", 1.0),
    "m/s": _C("m/s", 1.0),
    "MW": _C("MW", 1.0),
}


def fold_unit(unit: str) -> str:
    """Case- and whitespace-insensitive key, with "/day" read as "/d"."""
    return re.sub(r"/day$", "/d", re.sub(r"\s+", "", unit.lower()))


_FOLDED: dict[str, SiConversion] = {fold_unit(u): si for u, si in UNIT_TO_SI.items()}

# "1000", "1.5", "1E3", "e3" or "10^3", then an optional "*", "x" or "×", then the unit.
_MULTIPLIER = re.compile(
    r"^(?:10\^([+-]?\d+)|(\d+(?:\.\d+)?(?:e[+-]?\d+)?)|e([+-]?\d+))\s*[*x×]?\s*(?=[a-z])",
    re.IGNORECASE,
)


def _parse_multiplier(unit: str) -> tuple[float, str]:
    m = _MULTIPLIER.match(unit)
    if not m:
        return 1.0, unit
    power, number, e_power = m.groups()
    if power is not None:
        scale = 10.0 ** int(power)
    elif number is not None:
        scale = float(number)
    else:
        scale = 10.0 ** int(e_power)
    return scale, unit[m.end() :]


def to_si(unit: str | None) -> SiConversion:
    """Conversion of a native unit to SI. Unknown units are reported, not guessed: they keep
    their own name and factor 1, with ``known`` False."""
    if unit is None:
        return SiConversion(None, 1.0)
    scale = 1.0
    hit = UNIT_TO_SI.get(unit)
    if hit is None:
        scale, rest = _parse_multiplier(" ".join(unit.split()))
        hit = UNIT_TO_SI.get(rest) or _FOLDED.get(fold_unit(rest))
    # A zero multiplier, or one on an offset unit ("1000 degF"), means nothing.
    if hit is None or not (0 < scale < math.inf) or (scale != 1 and hit.offset):
        return SiConversion(unit, 1.0, known=False)
    return SiConversion(hit.si_unit, hit.factor * scale, hit.offset)


BBL_PER_SM3 = 1 / 0.1589873
