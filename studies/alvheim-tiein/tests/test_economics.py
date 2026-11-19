from __future__ import annotations

import datetime as dt
from dataclasses import replace

import pandas as pd
import pytest

from alvheim_tiein.economics import (
    BBL_PER_SM3,
    Reference,
    check_shares,
    split_to_companies,
    unit_prices,
    value_volumes,
)


def volumes(
    case: str, well: str, oil: float, *, period: str = "2027-01-01", days: float = 31.0
) -> dict:
    return {
        "case_name": case,
        "identifier": well,
        "period": pd.Timestamp(period),
        "days": days,
        "oil_sm3": oil,
        "gas_sm3": 0.0,
        "water_sm3": 0.0,
    }


def test_value_volumes_revenue_costs_and_discounting(reference: Reference) -> None:
    econ = replace(reference.economics, discount_rate=0.1, opex_per_sm3oe=50.0, tax_rate=0.5)
    ref = replace(reference, economics=econ)
    vol = pd.DataFrame([volumes("c", "H1", 100.0, period="2028-01-01", days=0.0)])
    row = value_volumes(vol, ref).iloc[0]
    assert row["revenue"] == pytest.approx(100 * BBL_PER_SM3 * 100.0)
    assert row["opex"] == pytest.approx(5000.0)
    assert row["cash_flow"] == pytest.approx((row["revenue"] - 5000.0) * 0.5)
    years = (pd.Timestamp("2028-01-01") - pd.Timestamp("2027-01-01")).days / 365.25
    assert row["discount_factor"] == pytest.approx(1.1**-years)
    assert row["license"] == "HOST"


def test_value_volumes_refuses_unmapped_wells_and_short_price_decks(reference: Reference) -> None:
    with pytest.raises(ValueError, match="without a licence"):
        value_volumes(pd.DataFrame([volumes("c", "GHOST", 1.0)]), reference)
    with pytest.raises(ValueError, match="price deck starts"):
        value_volumes(pd.DataFrame([volumes("c", "H1", 1.0, period="2026-06-01")]), reference)


def test_check_shares_catches_percent_and_bad_sums() -> None:
    shares = pd.DataFrame(
        {
            "license": ["L", "L", "M", "M", "M"],
            "company": ["A", "B", "A", "A", "B"],
            "share": [0.6, 0.3, 1.0, 0.5, 0.5],
            "valid_from": pd.to_datetime(
                ["2020-01-01", "2020-01-01", "2020-01-01", "2025-01-01", "2025-01-01"]
            ),
            "valid_to": pd.to_datetime([None, None, "2025-01-01", None, None]),
        }
    )
    problems = check_shares(shares)
    assert any("L shares sum to 0.9" in p for p in problems)
    assert not any(p.startswith("M") for p in problems)
    assert any("fractions" in p for p in check_shares(shares.assign(share=60.0)))


def test_split_to_companies_follows_dated_share_changes(reference: Reference) -> None:
    shares = pd.DataFrame(
        {
            "license": ["HOST", "HOST", "HOST"],
            "company": ["A", "B", "A"],
            "share": [0.8, 0.2, 1.0],
            "valid_from": pd.to_datetime(["2020-01-01", "2020-01-01", "2028-01-01"]),
            "valid_to": pd.to_datetime(["2028-01-01", "2028-01-01", None]),
        }
    )
    vol = pd.DataFrame([volumes("c", "H1", 10.0), volumes("c", "H1", 10.0, period="2028-02-01")])
    split = split_to_companies(value_volumes(vol, reference), shares)
    by = split.groupby(["period", "company"])["oil_sm3"].sum()
    assert by[(pd.Timestamp("2027-01-01"), "A")] == pytest.approx(8.0)
    assert by[(pd.Timestamp("2027-01-01"), "B")] == pytest.approx(2.0)
    assert by[(pd.Timestamp("2028-02-01"), "A")] == pytest.approx(10.0)
    assert (pd.Timestamp("2028-02-01"), "B") not in by


def test_reference_load_reads_templates_layout(tmp_path, reference: Reference) -> None:
    reference.entities.to_csv(tmp_path / "entities.csv", index=False)
    reference.shares.to_csv(tmp_path / "licence_shares.csv", index=False)
    reference.prices.to_csv(tmp_path / "prices.csv", index=False)
    (tmp_path / "economics.yaml").write_text(
        "valuation_date: 2027-01-01\ndiscount_rate: 0.07\ntariffs:\n"
        "  - {payer_license: NEW, payee_license: HOST, basis: oe_sm3, rate: 5}\n",
        encoding="utf-8",
    )
    ref = Reference.load(tmp_path)
    assert ref.economics.valuation_date == dt.date(2027, 1, 1)
    assert ref.economics.tariffs[0].basis == "oe_sm3"
    assert ref.companies() == ["A", "B", "C"]
    assert ref.economics.value_unit == "USD"


def test_oe_basis_values_in_sm3_oe_without_a_price_deck(tmp_path, reference: Reference) -> None:
    reference.entities.to_csv(tmp_path / "entities.csv", index=False)
    reference.shares.to_csv(tmp_path / "licence_shares.csv", index=False)
    (tmp_path / "economics.yaml").write_text(
        "value_basis: oe\nvaluation_date: 2027-01-01\ndiscount_rate: 0.0\nopex_per_sm3oe: 0.1\n",
        encoding="utf-8",
    )
    ref = Reference.load(tmp_path)
    assert ref.economics.value_unit == "Sm3 oe"
    assert ref.prices.empty
    vol = pd.DataFrame([{**volumes("c", "H1", 100.0, period="2020-01-01"), "gas_sm3": 50_000.0}])
    row = value_volumes(vol, ref).iloc[0]
    assert row["oe_sm3"] == pytest.approx(150.0)
    assert row["revenue"] == pytest.approx(150.0)
    assert row["pv"] == pytest.approx(150.0 * 0.9)
    prices = unit_prices(ref, pd.Series(pd.to_datetime(["2020-01-01", "2030-01-01"])))
    assert prices["oil"].tolist() == [1.0, 1.0]
    assert prices["gas"].tolist() == pytest.approx([0.001, 0.001])


def test_price_basis_needs_prices_and_valid_basis(tmp_path, reference: Reference) -> None:
    reference.entities.to_csv(tmp_path / "entities.csv", index=False)
    reference.shares.to_csv(tmp_path / "licence_shares.csv", index=False)
    (tmp_path / "economics.yaml").write_text("valuation_date: 2027-01-01\n", encoding="utf-8")
    with pytest.raises(FileNotFoundError, match="value_basis: price"):
        Reference.load(tmp_path)
    with pytest.raises(ValueError, match="value_basis"):
        replace(reference.economics, value_basis="usd")
