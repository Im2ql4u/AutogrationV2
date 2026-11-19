from __future__ import annotations

import datetime as dt

import pandas as pd
import pytest

from alvheim_tiein.economics import EconomicsConfig, Reference, Tariff


def result_rows(
    case: str,
    well: str,
    oil: list[float],
    *,
    unit: str = "Sm3/day",
    prop: str = "AvgOilRate",
    start: str = "2027-01-01",
) -> list[dict]:
    stamps = pd.date_range(start, periods=len(oil), freq="MS")
    return [
        {
            "module": "GAP",
            "system": "PROD",
            "identifier": well,
            "identifier_type": "WELL",
            "timestamp": ts,
            "run_number": 1,
            "property_name": prop,
            "value": v,
            "unit": unit,
            "case_name": case,
        }
        for ts, v in zip(stamps, oil, strict=True)
    ]


@pytest.fixture
def reference() -> Reference:
    entities = pd.DataFrame(
        {
            "identifier": ["H1", "S1", "N1"],
            "identifier_type": "WELL",
            "field": ["Host", "Sat", "New"],
            "license": ["HOST", "SAT", "NEW"],
        }
    )
    shares = pd.DataFrame(
        {
            "license": ["HOST", "HOST", "SAT", "NEW", "NEW"],
            "company": ["A", "B", "B", "A", "C"],
            "share": [0.8, 0.2, 1.0, 0.5, 0.5],
            "valid_from": pd.to_datetime(["2020-01-01"] * 5),
            "valid_to": pd.NaT,
        }
    )
    prices = pd.DataFrame(
        {
            "date": pd.to_datetime(["2027-01-01"]),
            "oil_price_per_bbl": [100.0],
            "gas_price_per_sm3": [0.0],
        }
    )
    econ = EconomicsConfig(
        valuation_date=dt.date(2027, 1, 1),
        discount_rate=0.0,
        tariffs=(Tariff("NEW", "HOST", "oil_sm3", 10.0),),
    )
    ref = Reference(entities, shares, prices, econ)
    ref.validate()
    return ref
