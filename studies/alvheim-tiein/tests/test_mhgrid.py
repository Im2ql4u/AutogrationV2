from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
import pytest

from alvheim_tiein import mhgrid as mg
from alvheim_tiein.levers import ModelTables, cell, cell_key


def month(label: str | pd.Timestamp) -> str:
    return pd.Timestamp(label).strftime("%d %B %Y 00:00:00.0000000")


MONTHS = list(pd.date_range("2026-07-01", periods=24, freq="MS"))
SWITCH = pd.Timestamp("2027-10-01")


def model() -> ModelTables:
    """Like Alvheim: 24 monthly rows from the forecast start; the future table's Month is
    yearly from the switch but its group column is read by step."""
    tables: list[dict[str, Any]] = [
        {"object_alias": "Uptime_base", "table_name": "Date", "values": [month(m) for m in MONTHS]},
        {
            "object_alias": "Uptime_base",
            "table_name": "Uptime",
            "values": [0.5 + 0.01 * m for m in range(24)],
        },
        {
            "object_alias": "Bookings_oil",
            "table_name": "Month",
            "values": [month(m) for m in MONTHS],
        },
        {
            "object_alias": "Bookings_oil",
            "table_name": "G",
            "values": [100.0 + m for m in range(24)],
        },
        {
            "object_alias": "Future_Bookings_Liquid",
            "table_name": "Month",
            "values": [month(SWITCH), month("2028-10-01"), month("2029-10-01")],
        },
        {
            "object_alias": "Future_Bookings_Liquid",
            "table_name": "G",
            "values": [1000.0 + m for m in range(24)],
        },
        {"object_alias": "Capacities", "table_name": "X", "values": [1.0]},
    ]
    return ModelTables({"tables": tables})


def by_key(cells: list[dict[str, Any]]) -> dict[tuple[str, str, int], float]:
    return {cell_key(c): c["values"][0] for c in cells}


@pytest.mark.parametrize(
    ("name", "count"),
    [("monthly", 174), ("mh", 45), ("my", 32), ("qy", 25), ("y", 23), ("q", 63), ("h", 37)],
)
def test_predicted_step_counts_match_the_observed_runs(name: str, count: int) -> None:
    steps = mg.predict_steps(name)
    assert len(steps) == count
    assert steps[0] == mg.FORECAST_START
    assert steps[-1] < mg.FORECAST_END


def test_forced_dates_cut_a_coarse_step_and_restart_it() -> None:
    steps = mg.predict_steps("h")
    assert steps[:8] == [
        pd.Timestamp(d)
        for d in (
            "2026-07-01",
            "2026-09-01",
            "2026-10-01",
            "2027-04-01",
            "2027-05-01",
            "2027-06-01",
            "2027-07-01",
            "2028-01-01",
        )
    ]


def test_unknown_grid_lists_the_known_ones() -> None:
    with pytest.raises(KeyError, match="mh"):
        mg.grid("weekly")


def test_tables_are_read_on_either_side_of_the_future_switch() -> None:
    tables = model()
    assert mg.table_window(tables, "Bookings_oil") == (None, SWITCH)
    assert mg.table_window(tables, "Future_Bookings_Liquid") == (SWITCH, None)
    assert mg.table_window(tables, "Uptime_base") == (None, None)


def test_monthly_grid_gives_back_the_overrides_the_workflow_reads() -> None:
    overrides = [
        cell("Uptime_base", "Uptime", 3, 0.1),
        cell("Bookings_oil", "G", 2, 7.0),
        cell("Bookings_oil", "G", 20, 7.0),  # Mar 2028: after the switch, never read
        cell("Future_Bookings_Liquid", "G", 16, 9.0),
        cell("Capacities", "X", 0, 5.0),
    ]
    out = by_key(mg.remap_cells(model(), mg.predict_steps("monthly"), overrides=overrides))
    assert out == {
        ("Uptime_base", "Uptime", 3): 0.1,
        ("Bookings_oil", "G", 2): 7.0,
        ("Future_Bookings_Liquid", "G", 16): 9.0,
        ("Capacities", "X", 0): 5.0,
    }


def test_h_grid_averages_whole_months_and_respects_the_switch() -> None:
    out = by_key(mg.remap_cells(model(), mg.predict_steps("h")))
    # Step 0 is Jul-Aug 2026, step 2 Oct 2026-Apr 2027 (rows 3-8).
    assert out[("Uptime_base", "Uptime", 0)] == pytest.approx(0.505)
    assert out[("Uptime_base", "Uptime", 2)] == pytest.approx(0.555)
    # Step 6 runs Jul 2027-Jan 2028: the monthly bookings only up to the switch (rows
    # 12-14), the future bookings not at all as the step starts before it.
    assert out[("Bookings_oil", "G", 6)] == pytest.approx(113.0)
    assert ("Future_Bookings_Liquid", "G", 6) not in out
    # Step 7 runs Jan-Jul 2028 (rows 18-23): future bookings only.
    assert out[("Future_Bookings_Liquid", "G", 7)] == pytest.approx(1020.5)
    assert ("Bookings_oil", "G", 7) not in out
    assert ("Capacities", "X", 0) not in out


def test_day_weights_differ_from_whole_months_on_uneven_months() -> None:
    steps = mg.predict_steps("h")
    days = by_key(mg.remap_cells(model(), steps, weights="days"))
    rows = range(3, 9)  # Oct 2026 - Mar 2027
    lengths = np.array([MONTHS[r].days_in_month for r in rows], dtype=float)
    values = np.array([0.5 + 0.01 * r for r in rows])
    expected = float((lengths * values).sum() / lengths.sum())
    assert days[("Uptime_base", "Uptime", 2)] == pytest.approx(expected, abs=1e-6)
    assert expected != pytest.approx(0.555, abs=1e-5)


def test_overrides_flow_into_the_step_average() -> None:
    overrides = [cell("Uptime_base", "Uptime", 1, 0.0), cell("Capacities", "X", 0, 5.0)]
    out = by_key(mg.remap_cells(model(), mg.predict_steps("h"), overrides=overrides))
    assert out[("Uptime_base", "Uptime", 0)] == pytest.approx(0.25)
    assert out[("Capacities", "X", 0)] == 5.0


def test_remap_table_lists_the_rows_read_on_the_grid() -> None:
    frame = mg.remap_table(model(), mg.predict_steps("h"))
    oil = frame[(frame["object_alias"] == "Bookings_oil")].set_index("row")
    assert oil.loc[6, "unmapped"] == 106.0
    assert oil.loc[6, "remapped"] == pytest.approx(113.0)
    assert oil.index.max() == 6
    assert frame["remapped"].notna().all()


def test_resolve_settings_for_uniform_and_mixed_grids() -> None:
    assert mg.resolve_settings("monthly") == []
    assert mg.resolve_settings("h") == [
        {
            "key": "INITIAL_TIMESTEP",
            "tag": "RESOLVE.ScheduleList[0].InitialTimestep",
            "value": 6.0,
        },
        {
            "key": "INITIAL_TIMESTEP_TYPE",
            "tag": "RESOLVE.ScheduleList[0].InitialTimestepType",
            "value": 2,
        },
    ]
    # As Kristoffer's QY run (booking-release qy_base).
    qy = {s["key"]: (s["tag"], s["value"]) for s in mg.resolve_settings("qy")}
    assert qy == {
        "END_DATE": ("RESOLVE.ScheduleList[0].EndDate", "2027-10-01"),
        "INITIAL_TIMESTEP": ("RESOLVE.ScheduleList[0].InitialTimestep", 3.0),
        "INITIAL_TIMESTEP_TYPE": ("RESOLVE.ScheduleList[0].InitialTimestepType", 2),
        "END_DATE__R1": ("RESOLVE.ScheduleList[1].EndDate", "2041-01-01"),
        "TIMESTEP_MODE__R1": ("RESOLVE.ScheduleList[1].TimestepMode", 0),
        "INITIAL_TIMESTEP__R1": ("RESOLVE.ScheduleList[1].InitialTimestep", 12.0),
        "INITIAL_TIMESTEP_TYPE__R1": ("RESOLVE.ScheduleList[1].InitialTimestepType", 2),
        "MAX_TIMESTEP_TYPE__R1": ("RESOLVE.ScheduleList[1].MaxTimestepType", 0),
        "OPTIMISATION_MODE__R1": ("RESOLVE.ScheduleList[1].OptimisationMode", 0),
        "OPTIMISATION_FREQUENCY_TYPE__R1": (
            "RESOLVE.ScheduleList[1].OptimisationFrequencyType",
            0,
        ),
    }
    mh = {s["key"]: s["value"] for s in mg.resolve_settings("mh")}
    assert mh["INITIAL_TIMESTEP"] == 1.0
    assert mh["INITIAL_TIMESTEP__R1"] == 6.0
