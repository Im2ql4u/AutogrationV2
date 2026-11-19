from __future__ import annotations

import pandas as pd
import pytest

from alvheim_tiein import settlement as s
from alvheim_tiein.economics import BBL_PER_SM3, Reference, value_volumes


def vol(case: str, well: str, oil: float) -> dict:
    return {
        "case_name": case,
        "identifier": well,
        "period": pd.Timestamp("2027-01-01"),
        "days": 31.0,
        "oil_sm3": oil,
        "gas_sm3": 0.0,
        "water_sm3": 0.0,
    }


@pytest.fixture
def valued(reference: Reference) -> pd.DataFrame:
    # With the tie-in, NEW produces 100 and pushes HOST down 10 and SAT down 5. Without
    # facility limits it would only cost HOST 4 and SAT 2 (back-pressure).
    rows = [
        vol("without", "H1", 100),
        vol("without", "S1", 50),
        vol("without", "N1", 0),
        vol("with", "H1", 90),
        vol("with", "S1", 45),
        vol("with", "N1", 100),
        vol("uncapped", "H1", 96),
        vol("uncapped", "S1", 48),
        vol("uncapped", "N1", 110),
    ]
    return value_volumes(pd.DataFrame(rows), reference)


PER_SM3 = BBL_PER_SM3 * 100.0  # value of 1 Sm3 oil at 100/bbl, no costs or discounting


def test_compare_and_decompose(valued: pd.DataFrame) -> None:
    d = s.compare(valued, "without", "with").set_index("license")
    assert d.loc["HOST", "delta_oil_sm3"] == -10
    assert d.loc["NEW", "delta_pv"] == pytest.approx(100 * PER_SM3)
    dec = s.decompose(
        valued, "without", "with", "uncapped", by=("license",), value="oil_sm3"
    ).set_index("license")
    assert dec.loc["HOST"].to_dict() == {"total": -10, "interference": -4, "displacement": -6}
    assert (dec["interference"] + dec["displacement"] - dec["total"]).abs().max() == 0


def test_compensation_pays_losses_only_unless_symmetric(valued: pd.DataFrame) -> None:
    flows = s.compensation_flows(valued, "without", "with", ["NEW"]).set_index("payee_license")
    assert flows["amount"].to_dict() == pytest.approx({"HOST": 10 * PER_SM3, "SAT": 5 * PER_SM3})
    assert (flows["payer_license"] == "NEW").all()
    reverse = s.compensation_flows(valued, "with", "without", ["HOST"], symmetric=True)
    assert reverse.set_index("payee_license").loc["NEW", "amount"] == pytest.approx(100 * PER_SM3)


def test_settlement_matrix_spreads_flows_over_both_sides_shares(
    valued: pd.DataFrame, reference: Reference
) -> None:
    st = s.settle(valued, reference, "without", "with", ["NEW"])
    tariff = st.licence_flows.set_index("kind").loc["tariff"]
    assert tariff["amount"] == pytest.approx(100 * 10.0)  # new licence: full tariff
    m = st.company_matrix
    host_due = 10 * PER_SM3 + 1000.0
    assert m.loc["C", "A"] == pytest.approx(0.5 * 0.8 * host_due)
    assert m.loc["C", "B"] == pytest.approx(0.5 * 0.2 * host_due + 0.5 * 5 * PER_SM3)
    assert st.net.sum() == pytest.approx(0.0, abs=1e-6)
    assert st.net["C"] == pytest.approx(-0.5 * (host_due + 5 * PER_SM3))


def test_tariff_change_charges_existing_payers_only_on_extra_volume(reference: Reference) -> None:
    rows = [vol("a", "N1", 40), vol("b", "N1", 100), vol("a", "H1", 1), vol("b", "H1", 1)]
    v = value_volumes(pd.DataFrame(rows), reference)
    change = s.tariff_change(v, "a", "b", reference)
    assert change["amount"].iloc[0] == pytest.approx(60 * 10.0)


def test_objective_table_and_price_of_conflict(reference: Reference) -> None:
    # Plan "share" favours SAT (wholly B's) at the cost of total hub value.
    rows = [
        vol("hub_plan", "H1", 100),
        vol("hub_plan", "S1", 10),
        vol("b_plan", "H1", 60),
        vol("b_plan", "S1", 40),
    ]
    table = s.objective_table(value_volumes(pd.DataFrame(rows), reference), reference)
    assert table["rank_hub"].to_dict() == {"b_plan": 2, "hub_plan": 1}
    poc = s.price_of_conflict(table, "B")
    assert poc["company_best_case"] == "b_plan"
    assert poc["hub_value_lost"] == pytest.approx(10 * PER_SM3)
    assert poc["company_value_gained"] == pytest.approx((52 - 30) * PER_SM3)


def test_shapley_values() -> None:
    additive = {
        frozenset(c): float(sum({"a": 1, "b": 2, "c": 3}[p] for p in c))
        for c in [(), ("a",), ("b",), ("c",), ("a", "b"), ("a", "c"), ("b", "c"), ("a", "b", "c")]
    }
    assert s.shapley_values(["a", "b", "c"], additive) == pytest.approx({"a": 1, "b": 2, "c": 3})
    # Two fields only make money together (shared hub): they split the synergy equally.
    phi = s.shapley_values(["x", "y"], lambda c: 10.0 if len(c) == 2 else 0.0)
    assert phi == pytest.approx({"x": 5.0, "y": 5.0})
