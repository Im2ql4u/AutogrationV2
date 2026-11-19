"""The two ledgers (research/22, "Shared Building Blocks" 4) and booked capacity.

- **Resource ledger (hub)**: the value of what was produced, less costs actually
  incurred, per case and period. Tariffs and transfers are left out: they cancel. The
  physical optimisation uses this ledger.
- **Participant ledger**: cash flows per licence (and, through effective-dated equity,
  per company): its own production value, tariffs paid and received, settlement
  transfers. Fairness and settlement use this ledger.
- **Reconciliation**: summed over participants, the participant ledger equals the
  resource ledger, for every case.

**Booked capacity** ``r_l`` is the basis of the proportional settlement rule (decision
3): oil and gas bookings in Sm3 oe, discounted like the cash flows.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from typing import Literal

import numpy as np
import pandas as pd

from alvheim_tiein.economics import EconomicsConfig, Reference

VALUE_COLUMNS = ("oil_sm3", "gas_sm3", "water_sm3", "oe_sm3", "revenue", "opex", "cash_flow", "pv")
LEDGER_COLUMNS = ["case", "license", "period", "kind", "counterparty", "cash_flow", "pv"]
BASIS_PHASES = ("oil", "gas")
HOST_LICENCE = "203"


def calendar(valued: pd.DataFrame, *, case_col: str = "case_name") -> pd.DataFrame:
    """Per case and period: days and the discount factor used by the economics."""
    cal = valued[[case_col, "period", "days", "discount_factor"]].drop_duplicates(
        [case_col, "period"]
    )
    return cal.sort_values([case_col, "period"]).reset_index(drop=True)


def discount_factors(
    periods: pd.Series | Sequence[pd.Timestamp], days: Sequence[float], econ: EconomicsConfig
) -> np.ndarray:
    """Mid-period discount factors, as in :func:`alvheim_tiein.economics.value_volumes`."""
    p = pd.to_datetime(pd.Series(list(periods)))
    mid = p + pd.to_timedelta(np.asarray(days, dtype=float) / 2.0, unit="D")
    years = (mid - pd.Timestamp(econ.valuation_date)).dt.days / 365.25
    return np.power(1.0 + econ.discount_rate, -years.to_numpy())


# ------------------------------------------------------------------ resource
def resource_ledger(
    valued: pd.DataFrame,
    *,
    by: Sequence[str] = ("period",),
    case_col: str = "case_name",
    values: Sequence[str] = VALUE_COLUMNS,
) -> pd.DataFrame:
    """Hub totals per case (and ``by``): volumes, revenue, opex, cash flow and PV."""
    cols = [c for c in values if c in valued.columns]
    out = valued.groupby([case_col, *by], dropna=False)[cols].sum().reset_index()
    return out.rename(columns={case_col: "case"})


# --------------------------------------------------------------- participant
def tariff_rows(
    valued: pd.DataFrame, ref: Reference, *, case_col: str = "case_name"
) -> pd.DataFrame:
    """Each tariff per case and period, as a payment (negative) for the payer and a
    receipt (positive) for the payee. Taxed like the cash flows."""
    econ = ref.economics
    rows = []
    for t in econ.tariffs:
        part = valued[valued["license"] == t.payer_license]
        if part.empty:
            continue
        g = part.groupby([case_col, "period"]).agg(
            volume=(t.basis, "sum"), discount_factor=("discount_factor", "first")
        )
        cash = g["volume"] * t.rate * (1.0 - econ.tax_rate)
        for sign, lic, other in (
            (-1.0, t.payer_license, t.payee_license),
            (1.0, t.payee_license, t.payer_license),
        ):
            frame = pd.DataFrame(
                {
                    "license": lic,
                    "kind": "tariff",
                    "counterparty": other,
                    "cash_flow": sign * cash,
                    "pv": sign * cash * g["discount_factor"],
                }
            )
            rows.append(frame.reset_index().rename(columns={case_col: "case"}))
    if not rows:
        return pd.DataFrame(columns=LEDGER_COLUMNS)
    return pd.concat(rows, ignore_index=True)[LEDGER_COLUMNS]


def participant_ledger(
    valued: pd.DataFrame,
    ref: Reference,
    *,
    transfers: pd.DataFrame | None = None,
    include_tariffs: bool = True,
    case_col: str = "case_name",
) -> pd.DataFrame:
    """Per case, licence, period and kind (``production``, ``tariff``, ``transfer``):
    cash flow and PV. ``transfers`` has case, license, period and pv (a settlement
    profile, :func:`alvheim_tiein.settlement.transfer_profile`), positive received."""
    prod = (
        valued.groupby([case_col, "license", "period"], as_index=False)[["cash_flow", "pv"]]
        .sum()
        .rename(columns={case_col: "case"})
        .assign(kind="production", counterparty="")
    )
    parts = [prod[LEDGER_COLUMNS]]
    if include_tariffs:
        parts.append(tariff_rows(valued, ref, case_col=case_col))
    if transfers is not None and not transfers.empty:
        cal = calendar(valued, case_col=case_col).rename(columns={case_col: "case"})
        t = transfers.merge(
            cal[["case", "period", "discount_factor"]], on=["case", "period"], how="left"
        )
        t = t.assign(
            kind="transfer",
            counterparty="",
            cash_flow=t["pv"] / t["discount_factor"].where(t["discount_factor"] > 0),
        )
        parts.append(t[LEDGER_COLUMNS])
    out = pd.concat([p for p in parts if not p.empty], ignore_index=True)
    return out.sort_values(["case", "license", "period", "kind"]).reset_index(drop=True)


def to_companies(
    ledger: pd.DataFrame, shares: pd.DataFrame, *, values: Sequence[str] = ("cash_flow", "pv")
) -> pd.DataFrame:
    """Licence rows spread over the equity valid in each row's period."""
    df = ledger.merge(shares, on="license", how="inner")
    active = (df["valid_from"] <= df["period"]) & (
        df["valid_to"].isna() | (df["valid_to"] > df["period"])
    )
    df = df[active].copy()
    for v in values:
        df[v] = df[v] * df["share"]
    keep = [c for c in ledger.columns if c not in values]
    return df[[*keep, "company", "share", *values]].reset_index(drop=True)


def reconcile(
    valued: pd.DataFrame,
    ledger: pd.DataFrame,
    *,
    case_col: str = "case_name",
    tol: float = 1e-6,
) -> pd.DataFrame:
    """Per case: hub PV, the sum of the participant ledger and the difference. Tariffs
    and transfers must cancel; ``ok`` is False where they don't."""
    hub = valued.groupby(case_col)["pv"].sum().rename("resource_pv")
    part = ledger.groupby("case")["pv"].sum().rename("participant_pv")
    out = pd.concat([hub, part], axis=1).fillna(0.0)
    out["difference"] = out["participant_pv"] - out["resource_pv"]
    scale = out["resource_pv"].abs().clip(lower=1.0)
    out["ok"] = (out["difference"].abs() / scale) <= tol
    return out.rename_axis("case").reset_index()


def licence_values(ledger: pd.DataFrame, *, value: str = "pv") -> pd.DataFrame:
    """Case (rows) x licence (columns) totals of the participant ledger."""
    return ledger.pivot_table(
        index="case", columns="license", values=value, aggfunc="sum", fill_value=0.0
    )


def company_values(
    ledger: pd.DataFrame, shares: pd.DataFrame, *, value: str = "pv"
) -> pd.DataFrame:
    """Case (rows) x company (columns) totals of the participant ledger."""
    comp = to_companies(ledger, shares)
    return comp.pivot_table(
        index="case", columns="company", values=value, aggfunc="sum", fill_value=0.0
    )


# ------------------------------------------------------------ booked capacity
def group_licence_split(
    members: Mapping[str, Sequence[str]],
    entities: pd.DataFrame,
    production: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """``s_{l,g,t}``: licence l's part of group g in period t.

    Production-weighted (``production`` has identifier, period and oe_sm3: the
    reference case's), or an equal split over the group's licences where the group
    produced nothing (or no production is given). Rows: group, license, period (NaT
    for the equal split), share."""
    lic = entities[["identifier", "license"]].drop_duplicates("identifier")
    wg = pd.DataFrame(
        [(g, w) for g, ws in members.items() for w in ws], columns=["group", "identifier"]
    ).merge(lic, on="identifier", how="left")
    unmapped = sorted(wg.loc[wg["license"].isna(), "identifier"].unique())
    if unmapped:
        raise ValueError(f"group wells without a licence in entities.csv: {unmapped}")
    equal = wg.drop_duplicates(["group", "license"])[["group", "license"]]
    equal = equal.assign(
        share=1.0 / equal.groupby("group")["license"].transform("count"), period=pd.NaT
    )
    if production is None:
        return equal[["group", "license", "period", "share"]]
    p = production.merge(wg, on="identifier", how="inner")
    p["period"] = pd.to_datetime(p["period"]).astype("datetime64[ns]")
    p = p.groupby(["group", "license", "period"], as_index=False)["oe_sm3"].sum()
    total = p.groupby(["group", "period"])["oe_sm3"].transform("sum")
    p = p[total > 0].assign(share=lambda f: f["oe_sm3"] / total[total > 0])
    return pd.concat([p[["group", "license", "period", "share"]], equal], ignore_index=True)


def split_for_periods(split: pd.DataFrame, periods: Iterable[pd.Timestamp]) -> pd.DataFrame:
    """The split per group and period: production-weighted where there is one, else
    equal."""
    weighted = split[split["period"].notna()].copy()
    weighted["period"] = pd.to_datetime(weighted["period"]).astype("datetime64[ns]")
    equal = split[split["period"].isna()].drop(columns="period")
    frame = pd.DataFrame({"period": pd.to_datetime(sorted(set(periods))).astype("datetime64[ns]")})
    grid = equal[["group"]].drop_duplicates().merge(frame, how="cross")
    have = weighted[["group", "period"]].drop_duplicates().assign(_w=True)
    grid = grid.merge(have, on=["group", "period"], how="left")
    fallback = grid[grid["_w"].isna()].drop(columns="_w").merge(equal, on="group")
    return pd.concat([weighted, fallback], ignore_index=True)


def booked_basis(
    booked: pd.DataFrame,
    split: pd.DataFrame,
    days_df: pd.DataFrame,
    *,
    limits: Mapping[str, float] | None = None,
    host: str = HOST_LICENCE,
    host_basis: Literal["residual", "none"] = "residual",
    gas_sm3_per_sm3oe: float = 1000.0,
) -> pd.DataFrame:
    """Booked capacity per licence and period in discounted Sm3 oe:
    ``Σ_g s_{l,g,t} (B_oil + B_gas / 1000) days_t DF_t``.

    ``booked`` has group, period, phase, booked_sm3d (the case's own bookings);
    ``split`` from :func:`group_licence_split`; ``days_df`` has period, days and
    discount_factor. With ``host_basis="residual"`` the host licence (which holds no
    booking) gets ``(L - Σ_g B_g)⁺`` per phase, in periods where that phase is booked
    at all: ``limits`` are the FPSO limits in Sm3/d. Rows: license, period, basis."""
    b = booked[booked["phase"].isin(BASIS_PHASES)].dropna(subset=["booked_sm3d"]).copy()
    b["period"] = pd.to_datetime(b["period"]).astype("datetime64[ns]")
    to_oe = np.where(b["phase"] == "gas", 1.0 / gas_sm3_per_sm3oe, 1.0)
    b["oe_sm3d"] = b["booked_sm3d"] * to_oe
    cal = days_df[["period", "days", "discount_factor"]].drop_duplicates("period").copy()
    cal["period"] = pd.to_datetime(cal["period"]).astype("datetime64[ns]")
    s = split_for_periods(split, b["period"].unique())
    s["period"] = pd.to_datetime(s["period"]).astype("datetime64[ns]")
    g = b.groupby(["group", "period"], as_index=False)["oe_sm3d"].sum()
    rows = g.merge(s, on=["group", "period"]).merge(cal, on="period")
    rows["basis"] = rows["oe_sm3d"] * rows["share"] * rows["days"] * rows["discount_factor"]
    out = rows.groupby(["license", "period"], as_index=False)["basis"].sum()
    if host_basis == "residual":
        if not limits:
            raise ValueError("host_basis='residual' needs the FPSO limits")
        tot = b.groupby(["period", "phase"], as_index=False)["booked_sm3d"].sum()
        tot["limit"] = tot["phase"].map(limits).astype(float)
        tot["oe_sm3d"] = (tot["limit"] - tot["booked_sm3d"]).clip(lower=0.0) * np.where(
            tot["phase"] == "gas", 1.0 / gas_sm3_per_sm3oe, 1.0
        )
        res = tot.groupby("period", as_index=False)["oe_sm3d"].sum().merge(cal, on="period")
        res = res.assign(license=host, basis=res["oe_sm3d"] * res["days"] * res["discount_factor"])
        out = pd.concat([out, res[["license", "period", "basis"]]], ignore_index=True)
        out = out.groupby(["license", "period"], as_index=False)["basis"].sum()
    return out.sort_values(["license", "period"]).reset_index(drop=True)


def basis_totals(basis: pd.DataFrame) -> pd.Series:
    """``r_l``: booked capacity per licence over all periods."""
    return basis.groupby("license")["basis"].sum().rename("basis")
