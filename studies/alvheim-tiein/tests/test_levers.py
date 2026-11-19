from __future__ import annotations

from typing import Any

import pandas as pd
import pytest

from alvheim_tiein import levers as lv

from .test_bookings import TABLES, table

EXTRA: list[dict[str, Any]] = [
    {"object_alias": "Weightings", "table_name": "Well", "values": ["W1", "W2", "W3"]},
    {"object_alias": "Weightings", "table_name": "Booking", "values": ["G", "G", "H"]},
    {"object_alias": "Weightings", "table_name": "Weight", "values": [3.0, 1.0, None]},
    {"object_alias": "Capacities", "table_name": "TotalOil_Capacity", "values": [1000.0]},
    {"object_alias": "Capacities", "table_name": "Maximumwaterrate", "values": [500.0]},
    {"object_alias": "Gas_upgrade", "table_name": "TotalGas_capacity", "values": [4700.0]},
    {"object_alias": "Wells_constraints", "table_name": "Well", "values": ["W1", "FL1"]},
    {"object_alias": "Wells_constraints", "table_name": "MaxLiquidRate", "values": [9.0, 8.0]},
]
MODEL = lv.ModelTables({"tables": [*TABLES["tables"], *EXTRA]})
STEPS = list(pd.date_range("2027-01-01", periods=4, freq="MS"))


def by_key(cells: list[dict[str, Any]]) -> dict[tuple[str, str, int], float]:
    return {lv.cell_key(c): c["values"][0] for c in cells}


def test_fpso_limits_in_sm3d_with_and_without_gas_upgrade() -> None:
    lim = lv.fpso_limits(MODEL)
    assert lim == {"oil": 1000.0, "gas": 4_700_000.0, "water": 500.0, "liquid": 1500.0}
    assert lv.fpso_limits(MODEL, gas_upgrade=False)["gas"] == 4_300_000.0


def test_weights_interpolate_towards_neutral_and_skip_blank_cells() -> None:
    cells = by_key(lv.weight_cells(MODEL, 0.5))
    assert cells == {("Weightings", "Weight", 0): 2.0, ("Weightings", "Weight", 1): 1.0}
    assert by_key(lv.weight_cells(MODEL, 0.0, wells=["W1"])) == {("Weightings", "Weight", 0): 1.0}


def test_release_moves_caps_towards_the_fpso_limit_in_its_window() -> None:
    lim = {"oil": 1000.0, "gas": 100_000.0, "water": 500.0, "liquid": 1500.0}
    cells = by_key(lv.release_cells(MODEL, STEPS, {"G": 0.5}, limits=lim, window="booking"))
    # Monthly oil row 0: 100 + 0.5 (1000 - 100); gas in table units (1000 Sm3/d).
    assert cells[("Bookings_oil", "G", 0)] == 550.0
    assert cells[("Bookings_gas", "G", 1)] == 75.0
    assert ("Bookings_oil", "H", 0) not in cells
    assert not any(k[0].startswith("Future") for k in cells)
    future = by_key(lv.release_cells(MODEL, STEPS, 1.0, limits=lim, window="future"))
    assert future[("Future_Bookings_Liquid", "G", 2)] == 1500.0
    assert future[("Future_Bookings_TotGas", "H", 3)] == 100.0
    none = lv.release_cells(MODEL, STEPS, 0.0, limits=lim, window="all", phases=["water"])
    assert by_key(none)[("Bookings_water", "G", 0)] == 20.0


def test_liquid_scale_only_touches_future_liquid() -> None:
    cells = by_key(lv.liquid_scale_cells(MODEL, STEPS, 0.5, groups=["G"]))
    assert cells == {
        ("Future_Bookings_Liquid", "G", 2): 100.0,
        ("Future_Bookings_Liquid", "G", 3): 100.5,
    }


def plan(rows: list[tuple[str, str, str, float]]) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=["group", "period", "phase", "booked_sm3d"])


def test_booking_plan_writes_changed_cells_only() -> None:
    p = plan(
        [
            ("G", "2027-01-01", "oil", 100.0),  # unchanged
            ("G", "2027-02-01", "oil", 120.0),
            ("G", "2027-03-01", "gas", 45_000.0),
            ("G", "2027-04-01", "liquid", float("nan")),  # no request
        ]
    )
    assert by_key(lv.booking_plan_cells(MODEL, STEPS, p)) == {
        ("Bookings_oil", "G", 1): 120.0,
        ("Future_Bookings_TotGas", "G", 2): 45.0,
    }


def test_booking_plan_rejects_a_phase_the_window_does_not_book() -> None:
    with pytest.raises(ValueError, match="doesn't book"):
        lv.booking_plan_cells(MODEL, STEPS, plan([("G", "2027-03-01", "oil", 1.0)]))


def test_booking_plan_rejects_a_group_the_tables_have_no_column_for() -> None:
    # An unbooked tie-in (Froskelår) is reported as booked 0 but has no cell to write.
    with pytest.raises(ValueError, match="no booking cell for FL gas"):
        lv.booking_plan_cells(MODEL, STEPS, plan([("FL", "2027-01-01", "gas", 5_000.0)]))


def test_booking_plan_rejects_different_values_for_a_shared_flat_cell() -> None:
    tables = lv.ModelTables(
        {
            "tables": [
                *table("Bookings_oil", ["2027-01-01"], {"G": [1.0]}),
                {"object_alias": "Bookings_future", "table_name": "Booking", "values": ["G"]},
                {"object_alias": "Bookings_future", "table_name": "liquid", "values": [10.0]},
            ]
        }
    )
    ok = plan([("G", "2027-02-01", "liquid", 12.0), ("G", "2027-03-01", "liquid", 12.0)])
    assert by_key(lv.booking_plan_cells(tables, STEPS[:3], ok)) == {
        ("Bookings_future", "liquid", 0): 12.0
    }
    bad = plan([("G", "2027-02-01", "liquid", 12.0), ("G", "2027-03-01", "liquid", 13.0)])
    with pytest.raises(ValueError, match="several steps"):
        lv.booking_plan_cells(tables, STEPS[:3], bad)


def test_well_cell_finds_the_row_by_well_name() -> None:
    assert lv.well_cell(MODEL, "FL1", "MaxLiquidRate", 5.0) == {
        "object_alias": "Wells_constraints",
        "table_name": "MaxLiquidRate",
        "index": 1,
        "values": [5.0],
    }
    with pytest.raises(KeyError):
        lv.well_cell(MODEL, "FL9", "MaxLiquidRate", 5.0)
    with pytest.raises(KeyError):
        lv.well_cell(MODEL, "FL1", "NoSuchColumn", 5.0)


def test_cells_for_checks_bounds_and_later_levers_win() -> None:
    levers = [
        lv.LeverDef(name="alpha", kind="weights", lower=0, upper=1, baseline=1),
        lv.LeverDef(
            name="fl_cap",
            kind="well_cell",
            lower=0,
            upper=10,
            wells=["FL1"],
            column="MaxLiquidRate",
        ),
        lv.LeverDef(
            name="fl_cap2",
            kind="well_cell",
            lower=0,
            upper=10,
            wells=["FL1"],
            column="MaxLiquidRate",
        ),
    ]
    cells = by_key(lv.cells_for({"alpha": 0, "fl_cap": 3, "fl_cap2": 4}, levers, MODEL, STEPS))
    assert cells[("Weightings", "Weight", 0)] == 1.0
    assert cells[("Wells_constraints", "MaxLiquidRate", 1)] == 4.0
    with pytest.raises(ValueError, match="outside"):
        lv.cells_for({"alpha": 2, "fl_cap": 3, "fl_cap2": 4}, levers, MODEL, STEPS)
    with pytest.raises(KeyError):
        lv.cells_for({"alpha": 0}, levers, MODEL, STEPS)


def test_lever_definitions_are_validated() -> None:
    with pytest.raises(ValueError):
        lv.LeverDef(name="x", kind="release", lower=1, upper=0)
    with pytest.raises(ValueError):
        lv.LeverDef(name="x", kind="well_cell", lower=0, upper=1)
    with pytest.raises(ValueError):
        lv.LeverDef(name="x", kind="weights", lower=0, upper=1, baseline=2)
