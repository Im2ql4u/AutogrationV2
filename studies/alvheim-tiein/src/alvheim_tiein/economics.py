"""Value period volumes and split them over licences and companies.

All economic inputs live in a reference folder (see ``templates/reference``) so every
assumption is visible and versionable:

- ``entities.csv``: identifier -> field, license (results-workbench compatible).
- ``licence_shares.csv``: license, company, share (fraction), valid_from, valid_to.
- ``prices.csv``: date, oil_price_per_bbl, gas_price_per_sm3 (step-wise from date).
- ``economics.yaml``: value basis, currency, discounting, unit costs, tax approximation,
  tariffs.

``value_basis: oe`` values production in Sm3 oil equivalent instead of money: revenue is
the oe volume, ``prices.csv`` is not needed, and costs and tariffs are read in Sm3 oe. It
compares cases and licences relative to each other before a price deck is agreed.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import numpy as np
import pandas as pd
import yaml

BBL_PER_SM3 = 6.28981077
VOLUME_BASES = ("oil_sm3", "gas_sm3", "water_sm3", "oe_sm3")
VALUE_BASES = ("price", "oe")
PRICE_COLUMNS = ["date", "oil_price_per_bbl", "gas_price_per_sm3"]


@dataclass(frozen=True)
class Tariff:
    """Payment from the user licence to the facility owner per unit of the user's volume."""

    payer_license: str
    payee_license: str
    basis: Literal["oil_sm3", "gas_sm3", "water_sm3", "oe_sm3"]
    rate: float
    description: str = ""


@dataclass(frozen=True)
class EconomicsConfig:
    valuation_date: dt.date
    value_basis: Literal["price", "oe"] = "price"
    currency: str = "USD"
    discount_rate: float = 0.08
    opex_per_sm3oe: float = 0.0
    water_cost_per_sm3: float = 0.0
    # 0 values pre-tax. A flat marginal rate (e.g. 0.78 on the NCS) is only an approximation.
    tax_rate: float = 0.0
    gas_sm3_per_sm3oe: float = 1000.0
    tariffs: tuple[Tariff, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.value_basis not in VALUE_BASES:
            raise ValueError(f"value_basis {self.value_basis!r}; use one of {VALUE_BASES}")

    @property
    def value_unit(self) -> str:
        """Unit of revenue, cash flow and PV."""
        return "Sm3 oe" if self.value_basis == "oe" else self.currency

    @classmethod
    def from_yaml(cls, path: Path) -> EconomicsConfig:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        tariffs = tuple(Tariff(**t) for t in raw.pop("tariffs", None) or [])
        for t in tariffs:
            if t.basis not in VOLUME_BASES:
                raise ValueError(f"tariff basis {t.basis!r}; use one of {VOLUME_BASES}")
        raw["valuation_date"] = pd.Timestamp(raw["valuation_date"]).date()
        return cls(**raw, tariffs=tariffs)


@dataclass
class Reference:
    entities: pd.DataFrame
    shares: pd.DataFrame
    prices: pd.DataFrame
    economics: EconomicsConfig

    @classmethod
    def load(cls, folder: Path, *, entities_csv: Path | None = None) -> Reference:
        economics = EconomicsConfig.from_yaml(folder / "economics.yaml")
        ref = cls(
            entities=pd.read_csv(
                entities_csv or folder / "entities.csv", dtype={"identifier": str, "license": str}
            ),
            shares=load_shares(folder / "licence_shares.csv"),
            prices=load_prices(folder / "prices.csv", required=economics.value_basis == "price"),
            economics=economics,
        )
        ref.validate()
        return ref

    def validate(self) -> None:
        problems = check_shares(self.shares)
        known = set(self.shares["license"])
        missing = sorted(set(self.entities["license"].dropna()) - known)
        if missing:
            problems.append(f"licences without shares: {missing}")
        for t in self.economics.tariffs:
            for lic in (t.payer_license, t.payee_license):
                if lic not in known:
                    problems.append(f"tariff licence {lic!r} has no shares")
        if problems:
            raise ValueError("reference data: " + "; ".join(problems))

    def companies(self) -> list[str]:
        return sorted(self.shares["company"].unique())


def load_prices(path: Path, *, required: bool = True) -> pd.DataFrame:
    """The price deck, or an empty one when it is not ``required`` and there is none."""
    if not path.exists():
        if required:
            raise FileNotFoundError(f"{path} is needed with value_basis: price")
        return pd.DataFrame(
            {c: pd.Series(dtype="datetime64[ns]" if c == "date" else float) for c in PRICE_COLUMNS}
        )
    return pd.read_csv(path, parse_dates=["date"]).sort_values("date")


def load_shares(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, dtype={"license": str, "company": str})
    df["valid_from"] = pd.to_datetime(df["valid_from"])
    df["valid_to"] = pd.to_datetime(df.get("valid_to"))
    return df


def check_shares(shares: pd.DataFrame, tol: float = 1e-6) -> list[str]:
    """Shares are fractions summing to 1 per licence at every date where they change."""
    problems = []
    if (shares["share"] > 1).any():
        problems.append("shares must be fractions (0-1), not percent")
    for lic, g in shares.groupby("license"):
        for date in sorted(g["valid_from"].unique()):
            active = g[(g["valid_from"] <= date) & (g["valid_to"].isna() | (g["valid_to"] > date))]
            total = active["share"].sum()
            if abs(total - 1.0) > tol:
                problems.append(f"{lic} shares sum to {total:.6f} from {pd.Timestamp(date).date()}")
    return problems


def shares_at(shares: pd.DataFrame, when: dt.date | pd.Timestamp) -> pd.DataFrame:
    when = pd.Timestamp(when)
    active = (shares["valid_from"] <= when) & (
        shares["valid_to"].isna() | (shares["valid_to"] > when)
    )
    return shares.loc[active, ["license", "company", "share"]].reset_index(drop=True)


def value_volumes(
    volumes: pd.DataFrame, ref: Reference, *, case_col: str = "case_name"
) -> pd.DataFrame:
    """Revenue, costs, cash flow and present value per case, identifier and period, in
    ``ref.economics.value_unit``.

    Every identifier must be mapped to a licence in ``entities.csv``; unmapped wells are
    an error so no production silently drops out of the economics."""
    econ = ref.economics
    mapping = ref.entities[["identifier", "field", "license"]].drop_duplicates("identifier")
    df = volumes.merge(mapping, on="identifier", how="left")
    unmapped = sorted(df.loc[df["license"].isna(), "identifier"].unique())
    if unmapped:
        raise ValueError(f"identifiers without a licence in entities.csv: {unmapped}")

    df["period"] = pd.to_datetime(df["period"]).astype("datetime64[ns]")
    df["oe_sm3"] = df["oil_sm3"] + df["gas_sm3"] / econ.gas_sm3_per_sm3oe
    if econ.value_basis == "oe":
        df["revenue"] = df["oe_sm3"]
    else:
        df = _with_prices(df, ref.prices)
        df["revenue"] = (
            df["oil_sm3"] * BBL_PER_SM3 * df["oil_price_per_bbl"]
            + df["gas_sm3"] * df["gas_price_per_sm3"]
        )
    df["opex"] = df["oe_sm3"] * econ.opex_per_sm3oe + df["water_sm3"] * econ.water_cost_per_sm3
    df["pre_tax_cf"] = df["revenue"] - df["opex"]
    df["cash_flow"] = df["pre_tax_cf"] * (1.0 - econ.tax_rate)
    mid = df["period"] + pd.to_timedelta(df["days"] / 2.0, unit="D")
    years = (mid - pd.Timestamp(econ.valuation_date)).dt.days / 365.25
    df["discount_factor"] = np.power(1.0 + econ.discount_rate, -years)
    df["pv"] = df["cash_flow"] * df["discount_factor"]
    cols = [
        case_col,
        "identifier",
        "field",
        "license",
        "period",
        "days",
        *VOLUME_BASES,
        "revenue",
        "opex",
        "pre_tax_cf",
        "cash_flow",
        "discount_factor",
        "pv",
    ]
    return df[cols].sort_values([case_col, "identifier", "period"]).reset_index(drop=True)


def _with_prices(df: pd.DataFrame, deck: pd.DataFrame) -> pd.DataFrame:
    """``df`` (with ``period``) plus the prices in force at each period."""
    prices = deck.rename(columns={"date": "period"})
    prices["period"] = prices["period"].astype("datetime64[ns]")
    if prices.empty:
        raise ValueError("value_basis: price needs a price deck in prices.csv")
    if df["period"].min() < prices["period"].min():
        raise ValueError(
            f"price deck starts {prices['period'].min().date()}, after the first period "
            f"{df['period'].min().date()}"
        )
    return pd.merge_asof(df.sort_values("period"), prices, on="period", direction="backward")


def unit_prices(ref: Reference, periods: pd.Series) -> pd.DataFrame:
    """Per period: value of 1 Sm3 oil and 1 Sm3 gas before costs, in the value unit."""
    econ = ref.economics
    df = pd.DataFrame({"period": pd.to_datetime(periods).astype("datetime64[ns]")})
    df = df.drop_duplicates().sort_values("period").reset_index(drop=True)
    if econ.value_basis == "oe":
        return df.assign(oil=1.0, gas=1.0 / econ.gas_sm3_per_sm3oe)
    df = _with_prices(df, ref.prices)
    return pd.DataFrame(
        {
            "period": df["period"],
            "oil": df["oil_price_per_bbl"] * BBL_PER_SM3,
            "gas": df["gas_price_per_sm3"],
        }
    )


def split_to_companies(
    valued: pd.DataFrame,
    shares: pd.DataFrame,
    value_cols: tuple[str, ...] = ("oil_sm3", "gas_sm3", "oe_sm3", "cash_flow", "pv"),
) -> pd.DataFrame:
    """Each row's values times the company shares valid in that period."""
    df = valued.merge(shares, on="license", how="inner")
    active = (df["valid_from"] <= df["period"]) & (
        df["valid_to"].isna() | (df["valid_to"] > df["period"])
    )
    df = df[active].copy()
    for col in value_cols:
        df[col] = df[col] * df["share"]
    keep = [c for c in valued.columns if c not in value_cols and c in df.columns]
    return df[[*keep, "company", "share", *value_cols]].reset_index(drop=True)
