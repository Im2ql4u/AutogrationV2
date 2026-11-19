from __future__ import annotations

from dataclasses import replace

import pandas as pd
import pytest

from alvheim_tiein import restructure as rs
from alvheim_tiein.economics import BBL_PER_SM3, Reference

from .test_bookings import TABLES

P1, P2 = pd.Timestamp("2027-01-01"), pd.Timestamp("2027-02-01")


def frame(col: str, values: dict[tuple[str, pd.Timestamp], float]) -> pd.DataFrame:
    return pd.DataFrame(
        [(g, p, "oil", v) for (g, p), v in values.items()],
        columns=["group", "period", "phase", col],
    )


BOOKED = frame("booked_sm3d", {("G", P1): 100, ("G", P2): 100, ("H", P1): 100, ("H", P2): 100})
Q1 = frame("produced_sm3d", {("G", P1): 100, ("G", P2): 60, ("H", P1): 50, ("H", P2): 100})
DEMAND = frame("produced_sm3d", {("G", P1): 150, ("G", P2): 60, ("H", P1): 50, ("H", P2): 130})
WORTH = pd.DataFrame(
    {"period": [P1, P2], "phase": "oil", "days": [31.0, 28.0], "worth": [2.0, 1.0]}
)


@pytest.fixture
def state() -> pd.DataFrame:
    return rs.booking_state(BOOKED, Q1, DEMAND)


def get(plan: pd.DataFrame, group: str, period: pd.Timestamp) -> float:
    row = plan[(plan["group"] == group) & (plan["period"] == period)]
    return float(row["booked_sm3d"].iloc[0])


def test_booking_state(state: pd.DataFrame) -> None:
    s = state.set_index(["group", "period"])
    assert bool(s.loc[("G", P1), "at_cap"]) and s.loc[("G", P1), "unmet"] == 50
    assert s.loc[("G", P2), "unused"] == 40 and s.loc[("G", P2), "slack"] == 40
    assert s.loc[("H", P1), "slack"] == 50 and s.loc[("H", P2), "unmet"] == 30


def test_r1_lends_unused_capacity_within_the_envelope(state: pd.DataFrame) -> None:
    plan = rs.r1_lend(state)
    assert get(plan, "G", P1) == 150 and get(plan, "H", P1) == 50
    assert get(plan, "H", P2) == 130 and get(plan, "G", P2) == 70
    assert rs.check_plan(rs.plan_of(state), plan) == []
    half = rs.r1_lend(state, lam=0.5)
    assert get(half, "G", P1) == 125
    with pytest.raises(ValueError):
        rs.r1_lend(state, lam=2)


def test_r2_swap_is_value_neutral_and_keeps_the_envelope(state: pd.DataFrame) -> None:
    res = rs.r2_swaps(state, WORTH)
    assert len(res.swaps) == 1
    sw = res.swaps[0]
    assert (sw.receiver, sw.giver, sw.period_in, sw.period_out) == ("G", "H", P1, P2)
    assert sw.amount_in == 15 and sw.amount_out == 30
    assert sw.amount_in * 2.0 == sw.amount_out * 1.0
    assert sw.gain == 60
    assert get(res.plan, "G", P1) == 115 and get(res.plan, "H", P2) == 130
    assert rs.check_plan(rs.plan_of(state), res.plan) == []
    assert len(res.table()) == 1
    with pytest.raises(ValueError, match="price deck"):
        rs.r2_swaps(state, WORTH.iloc[:1])


def test_r3_caps_froskelaar_at_a_share_of_its_peak() -> None:
    rates = pd.DataFrame(
        {
            "identifier": ["FL1", "FL1", "FL2"],
            "phase": "liquid",
            "rate_sm3d": [1000.0, 1200.0, 800.0],
        }
    )
    assert rs.r3_fl_caps(rates, 0.5) == {"FL1": 600.0, "FL2": 400.0}
    with pytest.raises(KeyError):
        rs.r3_fl_caps(rates, 0.5, wells=["FL3"])


def test_r4_resplit(state: pd.DataFrame) -> None:
    window = rs.r4_resplit(state)
    assert get(window, "G", P1) == pytest.approx(200 * 210 / 390)
    period = rs.r4_resplit(state, per_period=True)
    assert get(period, "G", P1) == pytest.approx(150)
    assert get(period, "H", P2) == pytest.approx(200 * 130 / 190)
    value = rs.r4_resplit(state, mode="value", priority={"H": 2.0, "G": 1.0})
    assert get(value, "G", P1) == 150 and get(value, "H", P2) == 135
    for plan in (window, period, value):
        assert rs.check_plan(rs.plan_of(state), plan) == []


def test_surrogate_cuts_the_lowest_priority_first() -> None:
    q = rs.surrogate(BOOKED, DEMAND).set_index(["group", "period"])["q_hat"]
    assert q[("G", P1)] == 100 and q[("H", P2)] == 100
    cut = rs.surrogate(BOOKED, DEMAND, limits={"oil": 120.0}, priority={"G": 1.0, "H": 2.0})
    c = cut.set_index(["group", "period"])["q_hat"]
    assert c[("G", P1)] == 70 and c[("H", P1)] == 50
    assert c[("G", P2)] == 20 and c[("H", P2)] == 100
    other = pd.DataFrame({"period": [P1], "phase": ["oil"], "other_sm3d": [60.0]})
    o = rs.surrogate(BOOKED, DEMAND, limits={"oil": 180.0}, other=other)
    assert o.groupby("period")["q_hat"].sum()[P1] == pytest.approx(120.0)


def test_rank_candidates(state: pd.DataFrame) -> None:
    ranked = rs.rank_candidates(
        {"r1": rs.r1_lend(state), "same": rs.plan_of(state)}, rs.plan_of(state), DEMAND, WORTH
    )
    assert ranked["candidate"].tolist() == ["r1", "same"]
    assert ranked.iloc[0]["surrogate_gain"] == pytest.approx(590 - 460)
    assert ranked.iloc[1]["surrogate_gain"] == 0


def test_swap_book_per_company(state: pd.DataFrame) -> None:
    split = pd.DataFrame(
        {"group": ["G", "H"], "license": ["L1", "L2"], "period": pd.NaT, "share": [1.0, 1.0]}
    )
    shares = pd.DataFrame(
        {
            "license": ["L1", "L2"],
            "company": ["X", "Y"],
            "share": [1.0, 1.0],
            "valid_from": pd.to_datetime(["2020-01-01"] * 2),
            "valid_to": pd.NaT,
        }
    )
    book = rs.swap_book(rs.plan_of(state), rs.r1_lend(state), split, shares, WORTH)
    b = book.set_index(["company", "period"])
    assert b.loc[("X", P1), "received_sm3oe"] == 50 * 31
    assert b.loc[("X", P1), "received_value"] == 100
    assert b.loc[("X", P2), "given_sm3oe"] == 30 * 28
    assert b.loc[("Y", P1), "net_value"] == -100
    assert book.groupby("period")["net_value"].sum().abs().max() == pytest.approx(0.0)


def test_unit_values(reference: Reference) -> None:
    cal = pd.DataFrame({"period": [P1, P2], "days": [31.0, 28.0]})
    uv = rs.unit_values(reference, cal).set_index(["phase", "period"])
    assert uv.loc[("oil", P1), "unit_value"] == pytest.approx(100 * BBL_PER_SM3)
    assert uv.loc[("oil", P2), "worth"] == pytest.approx(100 * BBL_PER_SM3 * 28)
    assert uv.loc[("gas", P1), "worth"] == 0


def test_unit_values_in_sm3_oe(reference: Reference) -> None:
    ref = replace(reference, economics=replace(reference.economics, value_basis="oe"))
    cal = pd.DataFrame({"period": [pd.Timestamp("2020-01-01"), P2], "days": [31.0, 28.0]})
    uv = rs.unit_values(ref, cal).set_index(["phase", "period"])
    assert uv.loc[("oil", P2), "unit_value"] == pytest.approx(1.0)
    assert uv.loc[("gas", P2), "worth"] == pytest.approx(28 / 1000)
    assert uv.loc[("oil", pd.Timestamp("2020-01-01")), "worth"] == pytest.approx(31.0)


def test_windows_and_priority_from_the_model_tables() -> None:
    periods = list(pd.date_range("2027-01-01", periods=4, freq="MS"))
    w = rs.booking_windows(TABLES, periods)
    assert w.tolist() == ["booking", "booking", "future", "future"]
    tables = {
        "tables": [
            {"object_alias": "Weightings", "table_name": "Booking", "values": ["G", "G", "H", ""]},
            {"object_alias": "Weightings", "table_name": "Weight", "values": [2.0, 4.0, 1.0, 9.0]},
        ]
    }
    assert rs.group_priority(tables) == {"G": 3.0, "H": 1.0}
