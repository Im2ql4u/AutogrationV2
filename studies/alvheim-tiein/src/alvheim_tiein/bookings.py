"""Bookings: how production compares with the capacity each tie-back has booked.

The Alvheim model books FPSO capacity per tie-back group (GAP groups such as
``Boyla+Frosk``). Its workflow writes the booking tables into the groups' rate limits
every timestep, reading row *k* at step *k* (by step number, not by date):

- oil, gas and water limits (``Bookings_oil``, ``Bookings_gas``, ``Bookings_water``)
  until the last month in those tables;
- then total-gas and liquid limits (``Future_Bookings_TotGas``,
  ``Future_Bookings_Liquid``, or the flat ``Bookings_future``).

Autogration reads the tables in metric units: Sm3/d, gas in 1000 Sm3/d. Everything
here is in Sm3/d. A run that tracked the limits the model actually applied (see
``Project.booking_tracked_variables``) is compared with those; the tables are only a
fallback. Gas bookings limit total gas, lift gas included, so gas is only compared
fully when the run tracked each group's lift gas.

``booked`` is per group. Per company it is split by the licence shares of the group's
wells, weighted by what each well produced (a group with one licence simply splits by
its shares), so per company ``delta = (produced - booked) x weight``. Wells outside the
booking groups, such as a new tie-in, can be added as unbooked groups (booked 0).
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any, Protocol

import numpy as np
import pandas as pd

from alvheim_tiein.results import RATE_TO_SM3D, SENTINEL_ABS

PHASES = ("oil", "gas", "water", "liquid")
RATE_PROPERTY = {"oil": "OilRate", "gas": "GasRate", "water": "WatRate", "liquid": "LiqRate"}
GAS_TABLE_TO_SM3D = 1e3
MONTHLY_TABLES = {"oil": "Bookings_oil", "gas": "Bookings_gas", "water": "Bookings_water"}
FUTURE_TABLES = {"gas": "Future_Bookings_TotGas", "liquid": "Future_Bookings_Liquid"}
FLAT_FUTURE = "Bookings_future"
CONSTRAINT_PHASE = {"maxqoil": "oil", "maxqtotgas": "gas", "maxqwat": "water", "maxqliq": "liquid"}
_TRACKED = re.compile(r"GROUP\[\{(?P<group>[^}]+)\}\]\.(?P<constraint>\w+)$", re.IGNORECASE)
_TOL = 0.01


class Browser(Protocol):
    def browse(
        self, model_id: str, path: str | None = None, *, search: str | None = None, limit: int = 50
    ) -> dict[str, Any]: ...


# ----------------------------------------------------------------------- booked
def _columns(tables: Mapping[str, Any], alias: str) -> dict[str, list[Any]]:
    return {
        t["table_name"]: list(t.get("values") or [])
        for t in tables.get("tables") or []
        if t.get("object_alias") == alias
    }


def _months(values: Sequence[Any]) -> pd.DatetimeIndex:
    """Month column cells. RESOLVE stores local midnight in UTC (``30 June 2026
    22:00`` is 1 July 2026 in Norway), so times are rounded to the nearest day."""
    cleaned = [re.sub(r"\.\d+$", "", str(v)).strip() for v in values]
    parsed = pd.to_datetime(cleaned, dayfirst=True, format="mixed")
    return pd.DatetimeIndex(parsed).round("D")


def booking_groups(tables: Mapping[str, Any]) -> list[str]:
    """Group columns of the monthly booking tables."""
    cols = _columns(tables, MONTHLY_TABLES["gas"]) or _columns(tables, MONTHLY_TABLES["oil"])
    return [name for name in cols if name != "Month"]


def _cell(cols: Mapping[str, list[Any]], group: str, row: int) -> float:
    column = cols.get(group) or []
    if row >= len(column) or column[row] is None:
        return np.nan
    try:
        return float(column[row])
    except (TypeError, ValueError):
        return np.nan


def future_start(tables: Mapping[str, Any]) -> pd.Timestamp:
    """First date the workflow applies the future bookings: the first ``Month`` of the
    ``Future_Bookings`` tables, or the month after the monthly tables end, whichever is
    earlier. Alvheim's monthly tables run to Jun 2028 but the applied limits switch to
    total gas and liquid on 1 Oct 2027, the first future month (tracked limits, T6)."""
    month_col = (
        _columns(tables, MONTHLY_TABLES["oil"]).get("Month")
        or _columns(tables, MONTHLY_TABLES["gas"]).get("Month")
        or []
    )
    end = _months(month_col).max() + pd.offsets.MonthBegin(1) if month_col else pd.Timestamp.min
    for alias in FUTURE_TABLES.values():
        future_months = _columns(tables, alias).get("Month") or []
        if future_months:
            end = min(end, _months(future_months).min()) if month_col else end
    return end


CELL_COLUMNS = [
    "group",
    "period",
    "phase",
    "object_alias",
    "table_name",
    "row",
    "table_value",
    "factor",
]


def booking_cells(
    tables: Mapping[str, Any], periods: Sequence[pd.Timestamp], groups: Sequence[str] | None = None
) -> pd.DataFrame:
    """Where each group's booking for each step and phase lives in the model's tables,
    looked up the way the Alvheim workflow does: by step number, not by date.

    ``periods`` are one run's step dates; step *k* reads row *k*. Before
    :func:`future_start` the monthly oil, gas and water tables apply; from it gas and
    liquid from ``Future_Bookings_*`` (row *k* again), or the flat ``Bookings_future``
    where those have no row *k* (one cell shared by every step that falls back to it).

    One row per group, step and phase: the cell (``object_alias``, ``table_name`` =
    column, ``row``), its value in table units and the ``factor`` to Sm3/d. Phases a
    window doesn't book, and groups the tables have no column for (an unbooked tie-in),
    have no cell (``object_alias`` is None, value NaN)."""
    groups = list(groups or booking_groups(tables))
    steps = sorted({pd.Timestamp(p) for p in periods})
    monthly = {phase: _columns(tables, alias) for phase, alias in MONTHLY_TABLES.items()}
    future = {phase: _columns(tables, alias) for phase, alias in FUTURE_TABLES.items()}
    flat = _columns(tables, FLAT_FUTURE)
    monthly_end = future_start(tables)
    flat_groups = list(flat.get("Booking") or [])
    rows = []
    for k, period in enumerate(steps):
        in_monthly = period < monthly_end
        for g in groups:
            for phase in PHASES:
                factor = GAS_TABLE_TO_SM3D if phase == "gas" else 1.0
                cell: tuple[str | None, str | None, int | None] = (None, None, None)
                value = np.nan
                # A group with no column (an unbooked tie-in) has no cell to write.
                if in_monthly and g in monthly.get(phase, {}):
                    cell, value = (MONTHLY_TABLES[phase], g, k), _cell(monthly[phase], g, k)
                elif not in_monthly and phase in future:
                    if g in future[phase]:
                        cell, value = (FUTURE_TABLES[phase], g, k), _cell(future[phase], g, k)
                    if np.isnan(value) and g in flat_groups and phase in flat:
                        row = flat_groups.index(g)
                        cell, value = (FLAT_FUTURE, phase, row), _cell(flat, phase, row)
                rows.append(
                    {
                        "group": g,
                        "period": period,
                        "phase": phase,
                        "object_alias": cell[0],
                        "table_name": cell[1],
                        "row": cell[2],
                        "table_value": value,
                        "factor": factor,
                    }
                )
    out = pd.DataFrame(rows, columns=CELL_COLUMNS)
    out["period"] = pd.to_datetime(out["period"]).astype("datetime64[ns]")
    out["table_value"] = out["table_value"].astype(float)
    out["row"] = out["row"].astype("Int64")
    return out


def booked_from_tables(
    tables: Mapping[str, Any], periods: Sequence[pd.Timestamp], groups: Sequence[str] | None = None
) -> pd.DataFrame:
    """Booked rate (Sm3/d) per group, step and phase from the model's tables, read by
    step number like the workflow (see :func:`booking_cells`). Coarse time steps
    therefore read the wrong months unless the tables were remapped for that grid,
    exactly as in the model. This is a fallback: the limits a run tracked
    (``booked_from_steps``) are what was applied."""
    cells = booking_cells(tables, periods, groups)
    out = cells[["group", "period", "phase"]].copy()
    out["booked_sm3d"] = (cells["table_value"] * cells["factor"]).astype(float)
    return out


def booked_from_steps(steps: pd.DataFrame) -> pd.DataFrame:
    """Booked rate (Sm3/d) per group, period and phase from tracked group limits.

    ``steps`` has ``time`` (datetime), ``variable`` (the tracked tag) and ``value``. A
    limit GAP reports as unset (very large) is not booked. Gas limits are taken to be
    in 1000 Sm3/d like the tables."""
    rows = []
    for row in steps.itertuples(index=False):
        m = _TRACKED.search(str(row.variable))
        phase = CONSTRAINT_PHASE.get(m.group("constraint").lower()) if m else None
        if m is None or phase is None:
            continue
        value = row.value
        if value is None or not np.isfinite(value) or abs(value) >= SENTINEL_ABS / 1e5:
            value = np.nan
        factor = GAS_TABLE_TO_SM3D if phase == "gas" else 1.0
        rows.append(
            {
                "group": m.group("group"),
                "period": pd.Timestamp(row.time),
                "phase": phase,
                "booked_sm3d": value * factor,
            }
        )
    out = pd.DataFrame(rows, columns=["group", "period", "phase", "booked_sm3d"])
    out["period"] = pd.to_datetime(out["period"]).astype("datetime64[ns]")
    return out


def group_series_from_steps(
    steps: pd.DataFrame, suffix: str, *, factor: float = GAS_TABLE_TO_SM3D
) -> pd.DataFrame:
    """A tracked per-group series (e.g. lift gas, in 1000 Sm3/d) as Sm3/d: rows of
    ``GROUP[{g}].<suffix>`` become ``group, period, rate_sm3d``."""
    pattern = re.compile(r"GROUP\[\{(?P<group>[^}]+)\}\]\." + re.escape(suffix) + r"$", re.I)
    rows = []
    for row in steps.itertuples(index=False):
        m = pattern.search(str(row.variable))
        if m is None or row.value is None or not np.isfinite(row.value):
            continue
        if abs(row.value) >= SENTINEL_ABS / 1e5:
            continue
        rows.append(
            {
                "group": m.group("group"),
                "period": pd.Timestamp(row.time),
                "rate_sm3d": row.value * factor,
            }
        )
    out = pd.DataFrame(rows, columns=["group", "period", "rate_sm3d"])
    out["period"] = pd.to_datetime(out["period"]).astype("datetime64[ns]")
    return out


# ------------------------------------------------------------------ membership
def group_members(
    api: Browser,
    model_id: str,
    groups: Sequence[str],
    system_path: str = "RESOLVE.MODULE[0].MOD[0]",
) -> dict[str, list[str]]:
    """Wells in each GAP group, expanding member groups. Members are equipment indices
    in the model."""
    names: dict[int, tuple[str, str | None]] = {}

    def node(index: int) -> tuple[str, str | None]:
        if index not in names:
            n = api.browse(model_id, path=f"{system_path}.EQUIP[{index}]", limit=1)["node"]
            names[index] = (n.get("name") or f"EQUIP[{index}]", n.get("equipment_type"))
        return names[index]

    by_name: dict[str, int] = {}
    for g in groups:
        for m in api.browse(model_id, search=g, limit=50).get("matches") or []:
            if m.get("equipment_type") == "GROUP" and m.get("name") == g:
                by_name[g] = int(re.search(r"EQUIP\[(\d+)\]$", m["path"]).group(1))  # type: ignore[union-attr]

    def wells(index: int, seen: set[int]) -> list[str]:
        if index in seen:
            return []
        seen.add(index)
        n = api.browse(model_id, path=f"{system_path}.EQUIP[{index}]", limit=1)["node"]
        members = (n.get("properties", {}).get("member") or {}).get("value") or []
        out: list[str] = []
        for raw in members:
            i = int(raw)
            name, kind = node(i)
            if kind == "GROUP":
                out += wells(i, seen)
            elif kind == "WELL":
                out.append(name)
        return out

    missing = [g for g in groups if g not in by_name]
    if missing:
        raise LookupError(f"no GAP group named {missing} in model {model_id}")
    return {g: sorted(set(wells(by_name[g], set()))) for g in groups}


# ------------------------------------------------------------------ production
def well_rates(
    results: pd.DataFrame, members: Mapping[str, Sequence[str]], *, case_col: str = "case_name"
) -> pd.DataFrame:
    """Instantaneous solver rates (Sm3/d) of each group's wells: the rates the group
    limits apply to. Liquid is oil + water where the results have no ``LiqRate``."""
    well_group = pd.DataFrame(
        [(g, w) for g, ws in members.items() for w in ws], columns=["group", "identifier"]
    )
    df = results[
        (results["identifier_type"] == "WELL")
        & results["identifier"].isin(well_group["identifier"])
        & results["property_name"].isin(RATE_PROPERTY.values())
    ].copy()
    if df.empty:
        return pd.DataFrame(
            columns=[case_col, "group", "identifier", "period", "phase", "rate_sm3d"]
        )
    units = df["unit"].fillna("").str.strip().str.lower()
    unknown = sorted(set(units) - set(RATE_TO_SM3D))
    if unknown:
        raise ValueError(f"unknown rate unit(s) {unknown}; add them to results.RATE_TO_SM3D")
    value = df["value"].where(df["value"].abs() < SENTINEL_ABS)
    df["rate_sm3d"] = value * units.map(RATE_TO_SM3D).astype(float)
    df["phase"] = df["property_name"].map({v: k for k, v in RATE_PROPERTY.items()})
    df = df.rename(columns={"timestamp": "period"})
    df["period"] = pd.to_datetime(df["period"]).astype("datetime64[ns]")
    wide = df.pivot_table(
        index=[case_col, "identifier", "period"],
        columns="phase",
        values="rate_sm3d",
        aggfunc="first",
    )
    if "liquid" not in wide:
        wide["liquid"] = np.nan
    if {"oil", "water"} <= set(wide.columns):
        wide["liquid"] = wide["liquid"].fillna(wide["oil"].fillna(0) + wide["water"].fillna(0))
    long = wide.reset_index().melt(
        id_vars=[case_col, "identifier", "period"], var_name="phase", value_name="rate_sm3d"
    )
    return long.merge(well_group, on="identifier").fillna({"rate_sm3d": 0.0})[
        [case_col, "group", "identifier", "period", "phase", "rate_sm3d"]
    ]


def _company_rates(
    rates: pd.DataFrame, entities: pd.DataFrame, shares: pd.DataFrame
) -> pd.DataFrame:
    licence = entities[["identifier", "license"]].drop_duplicates("identifier")
    df = rates.merge(licence, on="identifier", how="left")
    unmapped = sorted(df.loc[df["license"].isna(), "identifier"].unique())
    if unmapped:
        raise ValueError(f"wells without a licence in entities.csv: {unmapped}")
    df = df.merge(shares, on="license", how="inner")
    active = (df["valid_from"] <= df["period"]) & (
        df["valid_to"].isna() | (df["valid_to"] > df["period"])
    )
    df = df[active].copy()
    df["company_rate_sm3d"] = df["rate_sm3d"] * df["share"]
    return df


# ---------------------------------------------------------------------- report
class BookingReport:
    """Booked vs produced for every case of a project (rates in Sm3/d)."""

    def __init__(
        self,
        results: pd.DataFrame,
        booked: pd.DataFrame,
        members: Mapping[str, Sequence[str]],
        entities: pd.DataFrame,
        shares: pd.DataFrame,
        *,
        baseline: str,
        unbooked: Mapping[str, Sequence[str]] | None = None,
        lift_gas: pd.DataFrame | None = None,
        case_col: str = "case_name",
    ) -> None:
        self.case_col = case_col
        self.baseline = baseline
        self.lift_gas = lift_gas
        """Per case, group and period: tracked lift-gas injection (Sm3/d), or None."""
        all_members = {**members, **(unbooked or {})}
        self.wells = well_rates(results, all_members, case_col=case_col)
        periods = self.wells[[case_col, "period"]].drop_duplicates()
        if "case_name" in booked.columns and case_col != "case_name":
            booked = booked.rename(columns={"case_name": case_col})
        per_case = case_col in booked.columns
        b = booked if per_case else periods.merge(booked, on="period")
        zero = (
            pd.DataFrame(
                [(g, ph) for g in (unbooked or {}) for ph in PHASES], columns=["group", "phase"]
            )
            .merge(periods, how="cross")
            .assign(booked_sm3d=0.0)
        )
        self.booked = pd.concat([b, zero], ignore_index=True)
        self.company_wells = _company_rates(self.wells, entities, shares)
        self.sources: pd.DataFrame | None = None
        """Per case, where its booked rates came from (``applied`` or ``tables``)."""

    def satisfaction(self) -> pd.DataFrame:
        """Per case, group, period and phase: booked, produced, delta, utilisation,
        whether the limit binds (within 1 %) and whether it was exceeded (by more than
        2 %). Gas bookings limit total gas (formation + lift gas): with tracked lift gas
        produced gas includes it (``basis`` formation+lift), otherwise it is formation
        gas only and understates how close the group is to its gas booking."""
        c = self.case_col
        keys = [c, "group", "period", "phase"]
        produced = self.wells.groupby(keys, as_index=False)["rate_sm3d"].sum()
        df = produced.rename(columns={"rate_sm3d": "produced_sm3d"}).merge(
            self.booked, on=keys, how="left"
        )
        if self.lift_gas is not None and not self.lift_gas.empty:
            lift = self.lift_gas.rename(columns={"rate_sm3d": "lift_sm3d"}).assign(phase="gas")
            df = df.merge(lift[[*keys, "lift_sm3d"]], on=keys, how="left")
        else:
            df["lift_sm3d"] = np.nan
        gas = df["phase"] == "gas"
        df.loc[gas, "produced_sm3d"] += df.loc[gas, "lift_sm3d"].fillna(0.0)
        df["basis"] = np.where(
            gas, np.where(df["lift_sm3d"].notna(), "formation+lift", "formation only"), ""
        )
        df["delta_sm3d"] = df["produced_sm3d"] - df["booked_sm3d"]
        df["utilisation"] = df["produced_sm3d"] / df["booked_sm3d"].where(df["booked_sm3d"] > 0)
        df["binding"] = df["utilisation"].ge(1 - _TOL)
        df["violated"] = df["utilisation"].gt(1 + 2 * _TOL)
        return df.sort_values([c, "group", "phase", "period"]).reset_index(drop=True)

    def well_contributions(self) -> pd.DataFrame:
        """Each well's production per company (its licence share), by group."""
        c = self.case_col
        cols = [
            c,
            "group",
            "identifier",
            "license",
            "company",
            "period",
            "phase",
            "company_rate_sm3d",
        ]
        return self.company_wells[cols].rename(columns={"company_rate_sm3d": "produced_sm3d"})

    def company_delta(self) -> pd.DataFrame:
        """Per case, group, company, period and phase: produced, the company's part of the
        booking (production-weighted licence shares) and the delta."""
        c = self.case_col
        keys = [c, "group", "period", "phase"]
        comp = self.company_wells.groupby([*keys, "company"], as_index=False)[
            "company_rate_sm3d"
        ].sum()
        total = comp.groupby(keys)["company_rate_sm3d"].transform("sum")
        # With nothing produced, weight by the wells' licence shares equally.
        equal = (
            (
                self.company_wells.groupby([*keys, "company"])["share"].sum()
                / self.company_wells.groupby(keys)["identifier"].nunique()
            )
            .rename("equal_weight")
            .reset_index()
        )
        comp = comp.merge(equal, on=[*keys, "company"], how="left")
        comp["weight"] = (comp["company_rate_sm3d"] / total.where(total > 0)).fillna(
            comp["equal_weight"]
        )
        comp = comp.merge(self.booked, on=keys, how="left")
        comp["booked_sm3d"] = comp["booked_sm3d"] * comp["weight"]
        comp = comp.rename(columns={"company_rate_sm3d": "produced_sm3d"})
        comp["delta_sm3d"] = comp["produced_sm3d"] - comp["booked_sm3d"]
        cols = [
            *keys[:2],
            "company",
            "period",
            "phase",
            "produced_sm3d",
            "booked_sm3d",
            "delta_sm3d",
            "weight",
        ]
        return (
            comp[cols]
            .sort_values([c, "group", "company", "phase", "period"])
            .reset_index(drop=True)
        )

    def change_vs_baseline(self) -> pd.DataFrame:
        """How each company's delta moves from the baseline to every other case."""
        c = self.case_col
        d = self.company_delta()
        keys = ["group", "company", "period", "phase"]
        base = d[d[c] == self.baseline][[*keys, "produced_sm3d", "delta_sm3d"]].rename(
            columns={"produced_sm3d": "baseline_produced_sm3d", "delta_sm3d": "baseline_delta_sm3d"}
        )
        other = d[d[c] != self.baseline]
        out = other.merge(base, on=keys, how="outer")
        out[c] = out[c].fillna("(missing)")
        for col in ("produced_sm3d", "delta_sm3d", "baseline_produced_sm3d", "baseline_delta_sm3d"):
            out[col] = out[col].fillna(0.0)
        out["change_in_delta_sm3d"] = out["delta_sm3d"] - out["baseline_delta_sm3d"]
        out["change_in_produced_sm3d"] = out["produced_sm3d"] - out["baseline_produced_sm3d"]
        return out.sort_values([c, "group", "company", "phase", "period"]).reset_index(drop=True)

    def summary(self) -> pd.DataFrame:
        """Per case, group and phase: mean booked and produced, mean delta, the share of
        periods below and at the booking, the share above it (GAP not honouring the
        limit), and what gas was compared (total gas needs tracked lift gas)."""
        c = self.case_col
        s = self.satisfaction()
        s = s[s["booked_sm3d"].notna()]
        return (
            s.groupby([c, "group", "phase"])
            .agg(
                periods=("period", "nunique"),
                booked_sm3d=("booked_sm3d", "mean"),
                produced_sm3d=("produced_sm3d", "mean"),
                delta_sm3d=("delta_sm3d", "mean"),
                below_booking=("utilisation", lambda u: float((u < 1 - _TOL).mean())),
                at_booking=("binding", "mean"),
                above_booking=("violated", "mean"),
                basis=("basis", "first"),
            )
            .reset_index()
        )

    def violations(self) -> pd.DataFrame:
        """Steps where a group produced more than its applied limit allows: GAP's solve
        did not honour the constraint, so that step (and comparisons using it) is
        suspect. Gas is only checked when lift gas is tracked."""
        s = self.satisfaction()
        checkable = (s["phase"] != "gas") | (s["basis"] == "formation+lift")
        return s[s["violated"] & checkable].reset_index(drop=True)
