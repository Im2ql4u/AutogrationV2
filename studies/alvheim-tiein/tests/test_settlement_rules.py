from __future__ import annotations

import pandas as pd
import pytest

from alvheim_tiein import settlement as s

P1, P2 = pd.Timestamp("2027-01-01"), pd.Timestamp("2027-02-01")
DELTA = pd.Series({"A": 30.0, "B": -10.0, "C": 0.0})
SHARES = pd.DataFrame(
    {
        "license": ["A", "B", "B", "C"],
        "company": ["X", "X", "Y", "Y"],
        "share": [1.0, 0.5, 0.5, 1.0],
        "valid_from": pd.to_datetime(["2020-01-01"] * 4),
        "valid_to": pd.NaT,
    }
)


@pytest.mark.parametrize(
    ("rule", "kw", "expected"),
    [
        ("minimal", {}, {"A": 20.0, "B": 0.0, "C": 0.0}),
        (
            "proportional",
            {"basis": pd.Series({"A": 1.0, "B": 1.0, "C": 2.0})},
            {"A": 5.0, "B": 5.0, "C": 10.0},
        ),
        ("equal", {}, {"A": 20 / 3, "B": 20 / 3, "C": 20 / 3}),
        (
            "shapley",
            {"phi": pd.Series({"A": 3.0, "B": -1.0, "C": 1.0})},
            {"A": 15.0, "B": 0.0, "C": 5.0},
        ),
    ],
)
def test_awards_are_non_negative_and_sum_to_the_surplus(rule, kw, expected) -> None:
    a = s.awards(DELTA, rule, **kw)
    assert a.to_dict() == pytest.approx(expected)
    t = s.transfers(DELTA, a)
    assert t.sum() == pytest.approx(0.0)
    assert ((DELTA + t) >= -1e-12).all()


def test_awards_need_a_surplus_and_their_inputs() -> None:
    with pytest.raises(ValueError, match="not positive"):
        s.awards(pd.Series({"A": -1.0, "B": 0.5}), "equal")
    with pytest.raises(ValueError, match="basis"):
        s.awards(DELTA, "proportional")
    with pytest.raises(ValueError, match="unknown rule"):
        s.awards(DELTA, "nash")


def test_surplus_from_a_ledger() -> None:
    led = pd.DataFrame(
        {
            "case": ["r", "r", "c", "c"],
            "license": ["A", "B", "A", "B"],
            "pv": [10.0, 10.0, 40.0, 0.0],
        }
    )
    assert s.surplus(led, "r", "c").to_dict() == {"A": 30.0, "B": -10.0}
    by_t = s.delta_by_period(led.assign(period=P1), "r", "c")
    assert by_t["delta"].tolist() == [30.0, -10.0]
    with pytest.raises(KeyError):
        s.surplus(led, "r", "x")


DELTA_T = pd.DataFrame(
    {
        "license": ["A", "A", "B", "B", "C", "C"],
        "period": [P1, P2] * 3,
        "delta": [20.0, 10.0, -10.0, 0.0, 0.0, 0.0],
    }
)
AWARD = pd.Series({"A": 5.0, "B": 5.0, "C": 10.0})


def test_transfer_profile_is_zero_sum_each_period() -> None:
    prof = s.transfer_profile(DELTA_T, AWARD)
    assert prof.groupby("period")["pv"].sum().abs().max() == pytest.approx(0.0)
    per_licence = prof.groupby("license")["pv"].sum()
    assert per_licence.to_dict() == pytest.approx(s.transfers(DELTA, AWARD).to_dict())
    assert prof.set_index(["license", "period"]).loc[("A", P1), "pv"] == pytest.approx(-17.5)


def test_pairwise_flows_and_company_views() -> None:
    t = s.transfers(DELTA, AWARD)
    flows = s.pairwise_flows(t).set_index("payee_license")["amount"]
    assert flows.to_dict() == pytest.approx({"B": 15.0, "C": 10.0})
    prof = s.transfer_profile(DELTA_T, AWARD)
    by_period = s.company_matrix_by_period(prof, SHARES)
    p1 = by_period[by_period["period"] == P1]
    received = (
        p1.groupby("payee")["amount"].sum().sub(p1.groupby("payer")["amount"].sum(), fill_value=0.0)
    )
    company = s.company_profile(prof, SHARES)
    expect = company[company["period"] == P1].set_index("company")["pv"]
    assert received.to_dict() == pytest.approx(expect.to_dict())
    check = s.company_no_loss(DELTA_T, prof, SHARES).set_index("company")
    assert check.loc["X", "delta"] == pytest.approx(25.0)
    assert check.loc["X", "final"] == pytest.approx(7.5)
    assert check.loc["Y", "final"] == pytest.approx(12.5)
    assert check["ok"].all()


def test_price_of_no_transfers() -> None:
    table = pd.DataFrame(
        {"hub": [100.0, 130.0, 110.0], "X": [50.0, 90.0, 55.0], "Y": [50.0, 40.0, 55.0]},
        index=["ref", "a", "b"],
    )
    out = s.price_of_no_transfers(table, "ref", companies=["X", "Y"])
    assert out["best_case"] == "a" and out["best_no_transfer_case"] == "b"
    assert out["price_of_no_transfers"] == 20.0
    assert out["no_transfer_cases"] == ["ref", "b"]


def test_in_kind_check() -> None:
    out = s.in_kind_check(
        pd.Series({"X": 60.0, "Y": 40.0}),
        pd.Series({"X": 50.0, "Y": 50.0}),
        pd.Series({"X": -5.0, "Y": 12.0}),
    ).set_index("company")
    assert out["margin"].to_dict() == {"X": 5.0, "Y": 2.0}
    assert out["ok"].all()
    assert not s.in_kind_check(pd.Series({"X": 1.0}), pd.Series({"X": 2.0}))["ok"].any()
