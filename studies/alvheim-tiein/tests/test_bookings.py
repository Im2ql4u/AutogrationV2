from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
import pytest

from alvheim_tiein import bookings as b


def month(label: str) -> str:
    return pd.Timestamp(label).strftime("%d %B %Y 00:00:00.0000000")


def table(alias: str, months: list[str], columns: dict[str, list[float]]) -> list[dict[str, Any]]:
    out = [{"object_alias": alias, "table_name": "Month", "values": [month(m) for m in months]}]
    out += [{"object_alias": alias, "table_name": g, "values": v} for g, v in columns.items()]
    return out


# As in the model: the future tables' Month column is yearly from the switch date; their
# group columns are read by step number.
FUTURE_MONTHS = ["2027-03-01", "2028-03-01", "2029-03-01", "2030-03-01", "2031-03-01"]
TABLES = {
    "tables": [
        *table(
            "Bookings_oil", ["2027-01-01", "2027-02-01"], {"G": [100.0, 90.0], "H": [10.0, 10.0]}
        ),
        *table("Bookings_gas", ["2027-01-01", "2027-02-01"], {"G": [50.0, 50.0], "H": [5.0, 5.0]}),
        *table(
            "Bookings_water", ["2027-01-01", "2027-02-01"], {"G": [20.0, 20.0], "H": [1.0, 1.0]}
        ),
        *table(
            "Future_Bookings_TotGas",
            FUTURE_MONTHS,
            {"G": [0.0, 0.0, 40.0, 41.0, 30.0], "H": [4.0] * 5},
        ),
        *table(
            "Future_Bookings_Liquid",
            FUTURE_MONTHS,
            {"G": [0.0, 0.0, 200.0, 201.0, 150.0], "H": [9.0] * 5},
        ),
        {"object_alias": "Capacities", "table_name": "TotalGas_Capacity", "values": [4300.0]},
    ]
}
PERIODS = list(pd.date_range("2027-01-01", periods=4, freq="MS")) + [pd.Timestamp("2028-11-01")]


def booked(frame: pd.DataFrame, group: str, period: str, phase: str) -> float:
    row = frame[
        (frame["group"] == group)
        & (frame["period"] == pd.Timestamp(period))
        & (frame["phase"] == phase)
    ]
    return float(row["booked_sm3d"].iloc[0])


def test_booked_reads_row_k_at_step_k_like_the_workflow() -> None:
    assert b.booking_groups(TABLES) == ["G", "H"]
    f = b.booked_from_tables(TABLES, PERIODS)
    assert booked(f, "G", "2027-01-01", "oil") == 100.0
    assert booked(f, "G", "2027-02-01", "oil") == 90.0
    assert booked(f, "G", "2027-01-01", "gas") == 50_000.0  # 1000 Sm3/d -> Sm3/d
    assert np.isnan(booked(f, "G", "2027-01-01", "liquid"))
    # After the last month of the monthly tables: future tables, row = step number.
    assert np.isnan(booked(f, "G", "2027-03-01", "oil"))
    assert booked(f, "G", "2027-03-01", "gas") == 40_000.0
    assert booked(f, "G", "2027-04-01", "liquid") == 201.0
    # Step 4 reads row 4 whatever its date: a coarse grid reads the wrong months.
    assert booked(f, "G", "2028-11-01", "liquid") == 150.0


def test_coarse_grid_reads_rows_by_step_not_by_date() -> None:
    tables = {
        "tables": table(
            "Bookings_oil",
            ["2027-01-01", "2027-02-01", "2027-03-01", "2027-04-01"],
            {"G": [100.0, 90.0, 80.0, 70.0]},
        )
    }
    quarterly = [pd.Timestamp("2027-01-01"), pd.Timestamp("2027-04-01")]
    f = b.booked_from_tables(tables, quarterly)
    # The second step (April) reads row 1 (February's booking), as the model does.
    assert booked(f, "G", "2027-04-01", "oil") == 90.0


def test_month_cells_stored_in_utc_are_local_midnight() -> None:
    months = b._months(["30 June 2026 22:00:00.0000000", "31 August 2027 22:00:00.0000000"])
    assert list(months) == [pd.Timestamp("2026-07-01"), pd.Timestamp("2027-09-01")]


def test_future_bookings_apply_from_their_first_month_even_if_monthly_rows_remain() -> None:
    # Alvheim: Bookings_* run to Jun 2028 but the applied limits switch to total gas and
    # liquid on 1 Oct 2027, the first Future_Bookings month (tracked MaxQliq, T6).
    months = [f"2027-{m:02d}-01" for m in range(7, 13)]
    tables = {
        "tables": [
            *table("Bookings_oil", months, {"G": [100.0] * 6}),
            *table("Future_Bookings_Liquid", ["2027-10-01", "2028-10-01"], {"G": [7.0] * 6}),
        ]
    }
    assert b.future_start(tables) == pd.Timestamp("2027-10-01")
    steps = list(pd.date_range("2027-07-01", periods=6, freq="MS"))
    f = b.booked_from_tables(tables, steps)
    assert booked(f, "G", "2027-09-01", "oil") == 100.0
    assert np.isnan(booked(f, "G", "2027-10-01", "oil"))
    assert booked(f, "G", "2027-10-01", "liquid") == 7.0


def test_flat_future_bookings_are_used_without_future_tables() -> None:
    tables = {
        "tables": [
            *table("Bookings_gas", ["2027-01-01"], {"G": [50.0]}),
            {"object_alias": "Bookings_future", "table_name": "Booking", "values": ["G"]},
            {"object_alias": "Bookings_future", "table_name": "gas", "values": [33.0]},
            {"object_alias": "Bookings_future", "table_name": "liquid", "values": [111.0]},
        ]
    }
    f = b.booked_from_tables(tables, PERIODS[:3])
    assert booked(f, "G", "2027-01-01", "gas") == 50_000.0
    assert booked(f, "G", "2027-02-01", "gas") == 33_000.0
    assert booked(f, "G", "2027-03-01", "liquid") == 111.0


def test_applied_limits_come_from_tracked_steps() -> None:
    steps = pd.DataFrame(
        {
            "time": [pd.Timestamp("2027-01-01")] * 3,
            "variable": [
                "resolve.module[0].MOD[{PROD}].GROUP[{G}].MaxQoil",
                "resolve.module[0].MOD[{PROD}].GROUP[{G}].MaxQTotGas",
                "resolve.module[0].MOD[{PROD}].GROUP[{G}].MaxQliq",
            ],
            "value": [95.0, 45.0, 3.4e35],
        }
    )
    f = b.booked_from_steps(steps)
    assert booked(f, "G", "2027-01-01", "oil") == 95.0
    assert booked(f, "G", "2027-01-01", "gas") == 45_000.0
    assert np.isnan(booked(f, "G", "2027-01-01", "liquid"))


class FakeModel:
    """Group G holds well W1 and group G2 (W2 and a joint)."""

    NODES = {
        1: {
            "name": "G",
            "equipment_type": "GROUP",
            "properties": {"member": {"value": [10.0, 2.0]}},
        },
        2: {
            "name": "G2",
            "equipment_type": "GROUP",
            "properties": {"member": {"value": [11.0, 12.0]}},
        },
        10: {"name": "W1", "equipment_type": "WELL"},
        11: {"name": "W2", "equipment_type": "WELL"},
        12: {"name": "J", "equipment_type": "JOINT"},
    }

    def browse(
        self, model_id: str, path: str | None = None, *, search: str | None = None, limit: int = 50
    ) -> dict[str, Any]:
        if search is not None:
            return {
                "matches": [
                    {
                        "name": n["name"],
                        "equipment_type": n["equipment_type"],
                        "path": f"S.EQUIP[{i}]",
                    }
                    for i, n in self.NODES.items()
                    if search in n["name"]
                ]
            }
        index = int(path.rsplit("[", 1)[1].rstrip("]"))  # type: ignore[union-attr]
        return {"node": self.NODES[index]}


def test_group_members_expand_nested_groups_to_wells() -> None:
    assert b.group_members(FakeModel(), "m", ["G"], system_path="S") == {"G": ["W1", "W2"]}
    with pytest.raises(LookupError, match="no GAP group"):
        b.group_members(FakeModel(), "m", ["Nope"], system_path="S")


def rates(
    case: str, well: str, oil: float, gas: float, water: float, periods: int = 2
) -> list[dict[str, Any]]:
    stamps = pd.date_range("2027-01-01", periods=periods, freq="MS")
    out = []
    for ts in stamps:
        for prop, value, unit in (
            ("OilRate", oil, "Sm3/day"),
            ("GasRate", gas, "1000Sm3/d"),
            ("WatRate", water, "Sm3/day"),
        ):
            out.append(
                {
                    "identifier": well,
                    "identifier_type": "WELL",
                    "timestamp": ts,
                    "property_name": prop,
                    "value": value,
                    "unit": unit,
                    "case_name": case,
                }
            )
    return out


@pytest.fixture
def report() -> b.BookingReport:
    results = pd.DataFrame(
        rates("base", "W1", 60, 30, 5)
        + rates("base", "W2", 40, 20, 5)
        + rates("base", "N1", 0, 0, 0)
        + rates("with", "W1", 50, 25, 5)
        + rates("with", "W2", 30, 15, 5)
        + rates("with", "N1", 70, 40, 0)
    )
    entities = pd.DataFrame({"identifier": ["W1", "W2", "N1"], "license": ["A", "B", "NEW"]})
    shares = pd.DataFrame(
        {
            "license": ["A", "B", "B", "NEW", "NEW"],
            "company": ["X", "X", "Y", "X", "Z"],
            "share": [1.0, 0.5, 0.5, 0.8, 0.2],
            "valid_from": pd.to_datetime(["2020-01-01"] * 5),
            "valid_to": pd.NaT,
        }
    )
    periods = sorted(results["timestamp"].unique())
    booked_frame = b.booked_from_tables(TABLES, periods, ["G"])
    return b.BookingReport(
        results,
        booked_frame,
        {"G": ["W1", "W2"]},
        entities,
        shares,
        baseline="base",
        unbooked={"New": ["N1"]},
    )


def test_satisfaction_compares_group_production_with_bookings(report: b.BookingReport) -> None:
    s = report.satisfaction()
    jan = s[
        (s["case_name"] == "base")
        & (s["group"] == "G")
        & (s["period"] == pd.Timestamp("2027-01-01"))
    ].set_index("phase")
    assert jan.loc["oil", "produced_sm3d"] == 100.0
    assert jan.loc["oil", "delta_sm3d"] == 0.0 and jan.loc["oil", "binding"]
    assert jan.loc["gas", "produced_sm3d"] == 50_000.0
    assert jan.loc["liquid", "produced_sm3d"] == 110.0  # oil + water
    new = s[(s["group"] == "New") & (s["case_name"] == "with") & (s["phase"] == "oil")]
    assert (new["booked_sm3d"] == 0).all() and (new["delta_sm3d"] == 70).all()


def test_company_delta_splits_the_group_delta_by_production_weighted_shares(
    report: b.BookingReport,
) -> None:
    d = report.company_delta()
    feb = d[
        (d["case_name"] == "with")
        & (d["group"] == "G")
        & (d["phase"] == "oil")
        & (d["period"] == pd.Timestamp("2027-02-01"))
    ].set_index("company")
    # W1 50 (A: X), W2 30 (B: X/Y halves): X 65, Y 15 of 80; booked 90.
    assert feb.loc["X", "produced_sm3d"] == pytest.approx(65.0)
    assert feb.loc["Y", "produced_sm3d"] == pytest.approx(15.0)
    assert feb["booked_sm3d"].sum() == pytest.approx(90.0)
    assert feb["delta_sm3d"].sum() == pytest.approx(80.0 - 90.0)
    assert feb.loc["Y", "delta_sm3d"] == pytest.approx(-10.0 * 15 / 80)


def test_change_vs_baseline_shows_who_loses_when_the_reservoir_comes_on(
    report: b.BookingReport,
) -> None:
    c = report.change_vs_baseline()
    jan = c[
        (c["group"] == "G") & (c["phase"] == "oil") & (c["period"] == pd.Timestamp("2027-01-01"))
    ].set_index("company")
    # Base: produced 100 = booked 100. With: 80 vs 100.
    assert jan["change_in_delta_sm3d"].sum() == pytest.approx(-20.0)
    assert (jan["change_in_produced_sm3d"] < 0).all()
    new = c[(c["group"] == "New") & (c["phase"] == "oil")].set_index("company")
    assert new.loc["X", "change_in_produced_sm3d"].iloc[0] == pytest.approx(56.0)


def test_summary_and_well_contributions(report: b.BookingReport) -> None:
    summary = report.summary().set_index(["case_name", "group", "phase"])
    # Base: Jan 100 of 100, Feb 100 of 90 booked. With: 80 both months.
    assert summary.loc[("base", "G", "oil"), "below_booking"] == 0.0
    assert summary.loc[("base", "G", "oil"), "at_booking"] == 1.0
    assert summary.loc[("with", "G", "oil"), "below_booking"] == 1.0
    wells = report.well_contributions()
    w2 = wells[
        (wells["identifier"] == "W2") & (wells["case_name"] == "base") & (wells["phase"] == "oil")
    ]
    assert set(w2["company"]) == {"X", "Y"} and (w2["produced_sm3d"] == 20.0).all()


def test_gas_includes_tracked_lift_gas_and_violations_are_flagged() -> None:
    results = pd.DataFrame(rates("base", "W1", 60, 30, 5) + rates("base", "W2", 40, 20, 5))
    entities = pd.DataFrame({"identifier": ["W1", "W2"], "license": ["A", "A"]})
    shares = pd.DataFrame(
        {
            "license": ["A"],
            "company": ["X"],
            "share": [1.0],
            "valid_from": pd.to_datetime(["2020-01-01"]),
            "valid_to": pd.NaT,
        }
    )
    periods = sorted(results["timestamp"].unique())
    booked_frame = b.booked_from_tables(TABLES, periods, ["G"])
    steps = pd.DataFrame(
        {
            "time": periods,
            "variable": ["resolve.module[0].MOD[{PROD}].GROUP[{G}].SolverResults[0].GasInj"] * 2,
            "value": [25.0, 0.0],  # 1000 Sm3/d
        }
    )
    lift = b.group_series_from_steps(steps, "SolverResults[0].GasInj").assign(case_name="base")
    rep = b.BookingReport(
        results, booked_frame, {"G": ["W1", "W2"]}, entities, shares, baseline="base", lift_gas=lift
    )
    s = rep.satisfaction().set_index(["period", "phase"])
    jan, feb = periods
    # Formation 50 + lift 25 (1000 Sm3/d) = 75 000 against a 50 000 booking.
    assert s.loc[(jan, "gas"), "produced_sm3d"] == 75_000.0
    assert s.loc[(jan, "gas"), "basis"] == "formation+lift"
    assert s.loc[(jan, "gas"), "violated"] and not s.loc[(feb, "gas"), "violated"]
    # Oil 100 against 90 booked in February: more than 2 % over.
    assert s.loc[(feb, "oil"), "violated"]
    v = rep.violations()
    assert set(zip(v["period"], v["phase"], strict=True)) == {(jan, "gas"), (feb, "oil")}
    assert rep.summary().set_index("phase").loc["gas", "basis"] == "formation+lift"


def test_gas_without_lift_gas_is_marked_and_not_called_a_violation(report: b.BookingReport) -> None:
    s = report.satisfaction()
    assert (s.loc[s["phase"] == "gas", "basis"] == "formation only").all()
    assert (report.violations()["phase"] != "gas").all()
