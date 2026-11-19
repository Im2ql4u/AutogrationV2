from __future__ import annotations

import pandas as pd
import pytest

from alvheim_tiein import ledgers as lg
from alvheim_tiein.economics import BBL_PER_SM3, Reference, value_volumes

P1, P2 = pd.Timestamp("2027-01-01"), pd.Timestamp("2027-02-01")
PER_SM3 = BBL_PER_SM3 * 100.0


def vol(case: str, well: str, oil: float, period: pd.Timestamp = P1) -> dict:
    days = 31.0 if period == P1 else 28.0
    return {
        "case_name": case,
        "identifier": well,
        "period": period,
        "days": days,
        "oil_sm3": oil,
        "gas_sm3": 0.0,
        "water_sm3": 0.0,
    }


@pytest.fixture
def valued(reference: Reference) -> pd.DataFrame:
    rows = [
        vol("off", "H1", 100),
        vol("off", "S1", 50),
        vol("off", "N1", 0),
        vol("on", "H1", 90),
        vol("on", "S1", 45),
        vol("on", "N1", 100),
        vol("on", "H1", 80, P2),
        vol("on", "N1", 20, P2),
    ]
    return value_volumes(pd.DataFrame(rows), reference)


def test_resource_ledger_is_hub_totals(valued: pd.DataFrame) -> None:
    r = lg.resource_ledger(valued).set_index(["case", "period"])
    assert r.loc[("on", P1), "oil_sm3"] == 235
    assert r.loc[("on", P2), "pv"] == pytest.approx(100 * PER_SM3)
    assert lg.resource_ledger(valued, by=()).set_index("case").loc["off", "oil_sm3"] == 150


def test_participant_ledger_tariffs_cancel_and_reconcile(
    valued: pd.DataFrame, reference: Reference
) -> None:
    led = lg.participant_ledger(valued, reference)
    tariff = led[(led["kind"] == "tariff") & (led["case"] == "on")]
    paid = tariff[tariff["license"] == "NEW"]["pv"].sum()
    assert paid == pytest.approx(-(100 + 20) * 10.0)
    assert tariff["pv"].sum() == pytest.approx(0.0)
    rec = lg.reconcile(valued, led)
    assert rec["ok"].all()
    lic = lg.licence_values(led)
    assert lic.loc["on", "HOST"] == pytest.approx(170 * PER_SM3 + 1200.0)
    comp = lg.company_values(led, reference.shares)
    assert comp.loc["on"].sum() == pytest.approx(lic.loc["on"].sum())


def test_transfers_enter_the_participant_ledger_and_still_reconcile(
    valued: pd.DataFrame, reference: Reference
) -> None:
    t = pd.DataFrame(
        {"case": ["on", "on"], "license": ["NEW", "SAT"], "period": [P1, P1], "pv": [-50.0, 50.0]}
    )
    led = lg.participant_ledger(valued, reference, transfers=t)
    assert set(led["kind"]) == {"production", "tariff", "transfer"}
    assert lg.reconcile(valued, led)["ok"].all()
    broken = pd.concat([led, led[led["kind"] == "transfer"].head(1)])
    assert not lg.reconcile(valued, broken).set_index("case").loc["on", "ok"]


MEMBERS = {"G": ["H1", "S1"], "K": ["N1"]}


def test_group_split_is_production_weighted_with_equal_fallback(reference: Reference) -> None:
    prod = pd.DataFrame(
        {
            "identifier": ["H1", "S1", "N1", "H1", "S1", "N1"],
            "period": [P1, P1, P1, P2, P2, P2],
            "oe_sm3": [30.0, 10.0, 5.0, 0.0, 0.0, 5.0],
        }
    )
    split = lg.group_licence_split(MEMBERS, reference.entities, prod)
    s = lg.split_for_periods(split, [P1, P2]).set_index(["group", "license", "period"])["share"]
    assert s[("G", "HOST", P1)] == 0.75
    assert s[("G", "SAT", P2)] == 0.5
    assert s[("K", "NEW", P2)] == 1.0
    with pytest.raises(ValueError, match="without a licence"):
        lg.group_licence_split({"G": ["X9"]}, reference.entities)


def test_booked_basis_with_host_residual(reference: Reference) -> None:
    prod = pd.DataFrame(
        {
            "identifier": ["H1", "S1", "N1", "N1"],
            "period": [P1, P1, P1, P2],
            "oe_sm3": [30.0, 10.0, 5.0, 5.0],
        }
    )
    split = lg.group_licence_split(MEMBERS, reference.entities, prod)
    booked = pd.DataFrame(
        [
            (g, p, ph, v)
            for p in (P1, P2)
            for g, ph, v in (
                ("G", "oil", 100.0),
                ("G", "gas", 10_000.0),
                ("K", "oil", 50.0),
                ("K", "gas", 0.0),
                ("G", "water", 999.0),
            )
        ],
        columns=["group", "period", "phase", "booked_sm3d"],
    )
    cal = pd.DataFrame({"period": [P1, P2], "days": [31.0, 28.0], "discount_factor": [1.0, 1.0]})
    basis = lg.booked_basis(booked, split, cal, limits={"oil": 200.0, "gas": 20_000.0}, host="HOST")
    r = lg.basis_totals(basis)
    assert r["SAT"] == pytest.approx(110 * 31 * 0.25 + 110 * 28 * 0.5)
    assert r["NEW"] == pytest.approx(50 * 59)
    residual = (50 + 10) * 59
    assert r["HOST"] == pytest.approx(110 * 31 * 0.75 + 110 * 28 * 0.5 + residual)
    none = lg.basis_totals(lg.booked_basis(booked, split, cal, host_basis="none", host="HOST"))
    assert none["HOST"] == pytest.approx(r["HOST"] - residual)
    with pytest.raises(ValueError, match="limits"):
        lg.booked_basis(booked, split, cal)


def test_discount_factors_match_the_economics(reference: Reference, valued: pd.DataFrame) -> None:
    cal = lg.calendar(valued)
    df = lg.discount_factors(cal["period"], cal["days"], reference.economics)
    assert list(df) == pytest.approx(list(cal["discount_factor"]))
