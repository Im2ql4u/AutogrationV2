import datetime as dt

import pandas as pd
import pytest

from autogration_results import workbench
from autogration_results.contract import (
    SM3_PER_BBL,
    SM3_PER_SCF,
    UNIT_TO_SI,
    fold_unit,
    to_si,
)
from autogration_results.engine import ResultStore, Unavailable
from autogration_results.health import run_checks

THOUSAND_SM3_PER_DAY = [
    "1000Sm3/d",
    "1000Sm3/day",
    "1000 Sm3/d",
    "1000 Sm3/day",
    "1E3Sm3/d",
    "1e3Sm3/d",
    "1e3 Sm3/d",
    "e3Sm3/d",
    "E3Sm3/d",
    "e3 Sm3/day",
    "10^3 Sm3/d",
    "10^3Sm3/d",
    "1000*Sm3/d",
    "1000 x Sm3/d",
    "kSm3/D",
    "kSm3/d",
    "KSM3/DAY",
    " 1000Sm3/d ",
    "1000  Sm3 / d",
]


@pytest.mark.parametrize("unit", THOUSAND_SM3_PER_DAY)
def test_thousand_sm3_per_day(unit):
    si = to_si(unit)
    assert (si.si_unit, si.offset, si.known) == ("Sm3/d", 0.0, True)
    assert si.factor == pytest.approx(1e3)


@pytest.mark.parametrize(
    "unit", ["Sm3/day", "Sm3/d", "sm3/d", "Sm3/D", "SM3/DAY", "sm3/Day"]
)
def test_sm3_per_day(unit):
    assert to_si(unit) == ("Sm3/d", 1.0, 0.0, True)


@pytest.mark.parametrize(
    ("unit", "si_unit", "factor"),
    [
        ("1000Sm3", "Sm3", 1e3),
        ("1000 Sm3", "Sm3", 1e3),
        ("MSm3", "Sm3", 1e6),
        ("MMSm3", "Sm3", 1e6),
        ("MMSm3/d", "Sm3/d", 1e6),
        ("MSm3/day", "Sm3/d", 1e6),
        ("GSm3", "Sm3", 1e9),
        ("Mscf/d", "Sm3/d", SM3_PER_SCF * 1e3),
        ("MSCF/DAY", "Sm3/d", SM3_PER_SCF * 1e3),
        ("MMscf/D", "Sm3/d", SM3_PER_SCF * 1e6),
        ("Mscf", "Sm3", SM3_PER_SCF * 1e3),
        ("Mbbl", "Sm3", SM3_PER_BBL * 1e3),
        ("MMbbl", "Sm3", SM3_PER_BBL * 1e6),
        ("STB/D", "Sm3/d", SM3_PER_BBL),
        ("BARa", "bara", 1.0),
        ("BARA", "bara", 1.0),
        ("bar", "bar", 1.0),
        ("deg C", "degC", 1.0),
        ("DEG C", "degC", 1.0),
        ("percent", "%", 1.0),
        ("Sm3/Sm3", "Sm3/Sm3", 1.0),
    ],
)
def test_known_units(unit, si_unit, factor):
    si = to_si(unit)
    assert (si.si_unit, si.known) == (si_unit, True)
    assert si.factor == pytest.approx(factor)


def test_temperature_offset():
    si = to_si("DEG F")
    assert (si.si_unit, si.known) == ("degC", True)
    assert si.factor * 212 + si.offset == pytest.approx(100.0)


@pytest.mark.parametrize(
    "unit",
    [
        "bbl/week",
        "Sm3/h",
        "1000 m3/d",
        "e3m3/d",
        "100 %",
        "1000 degF",
        "0 Sm3/d",
        "",
        "__class__",
    ],
)
def test_unknown_stays_unknown(unit):
    assert to_si(unit) == (unit, 1.0, 0.0, False)


def test_missing_unit_is_dimensionless():
    assert to_si(None) == (None, 1.0, 0.0, True)


def test_no_table_keys_fold_together_with_different_conversions():
    seen: dict[str, tuple[str, object]] = {}
    for unit, si in UNIT_TO_SI.items():
        key = fold_unit(unit)
        if key in seen:
            assert si == seen[key][1], f"{unit} and {seen[key][0]} fold to {key}"
        seen[key] = (unit, si)
    # Mega Sm3 and oilfield thousand scf/bbl must not fold together.
    assert fold_unit("MSm3") != fold_unit("Mscf")
    assert fold_unit("Mbbl") != fold_unit("MMbbl")


@pytest.mark.parametrize("unit", list(UNIT_TO_SI))
def test_table_keys_read_the_same_in_upper_case(unit):
    assert to_si(unit.upper()) == to_si(unit)


def _store(rows):
    df = pd.DataFrame(
        rows,
        columns=["identifier", "identifier_type", "property_name", "value", "unit"],
    )
    df.insert(0, "timestamp", dt.date(2030, 1, 1))
    df.insert(0, "run_number", 1)
    df.insert(0, "system", "PROD")
    df.insert(0, "module", "GAP")
    return ResultStore.from_frames(df, workbench.registry())


def test_gap_gas_rates_combine_with_sm3_per_day():
    store = _store(
        [
            ("W1", "WELL", "AvgGasRate", 1.5, "1000Sm3/d"),
            ("W2", "WELL", "AvgGasRate", 500.0, "Sm3/day"),
            ("W3", "WELL", "AvgGasRate", 0.25, "1E3 Sm3/D"),
            ("W1", "WELL", "CumGas", 2.0, "MSm3"),
        ]
    )
    si = store.con.execute(
        "SELECT identifier, unit_si, value_si FROM results_si WHERE property_name = 'AvgGasRate'"
    ).df()
    assert si.set_index("identifier").value_si.to_dict() == pytest.approx(
        {"W1": 1500.0, "W2": 500.0, "W3": 250.0}
    )
    assert set(si.unit_si) == {"Sm3/d"}
    by_well = store.query("gas_rate", ["identifier"]).set_index("identifier")["value"]
    # gas_rate is in kSm3/d: 1.5 kSm3/d is 1500 Sm3/d.
    assert by_well.to_dict() == pytest.approx({"W1": 1.5, "W2": 0.5, "W3": 0.25})
    assert store.query("gas_rate", [])["value"].iloc[0] == pytest.approx(2.25)
    assert store.query("cum_gas", [])["value"].iloc[0] == pytest.approx(2e6 / 1e9)
    assert run_checks(store).query("check == 'unknown_unit'").empty


def test_unknown_unit_is_reported_and_blocks_the_measure():
    store = _store(
        [
            ("W1", "WELL", "AvgGasRate", 1.5, "1000 m3/d"),
            ("W1", "WELL", "AvgOilRate", 10.0, "Sm3/d"),
        ]
    )
    unknown = run_checks(store).query("check == 'unknown_unit'")
    assert unknown.detail.tolist() == ["unit 1000 m3/d"]
    assert store.query("oil_rate", [])["value"].iloc[0] == pytest.approx(10.0)
    with pytest.raises(Unavailable):
        store.query("gas_rate", [])
