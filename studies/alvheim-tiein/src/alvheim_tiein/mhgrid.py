"""Coarse time grids for a model whose workflow reads tables by step index (M2).

The Alvheim workflow reads ``Uptime_base.Uptime[k]``, ``Bookings_*[k]`` and
``Future_Bookings_*[k]`` at step *k*, not at the step's date. The tables hold one row
per month from the forecast start. On any grid other than monthly, row *k* must hold the
step's own average, otherwise uptime and bookings land on the wrong dates.

- :func:`predict_steps` gives a grid's step dates. RESOLVE forces a step at each
  workflow well-opening date (:data:`FORCED_STEPS`) and restarts the fixed step from
  there; this reproduces the observed step counts (MH 45, MY 32, QY 25, Y 23).
- :func:`remap_cells` turns the model's tables, plus any monthly overrides (a lever's
  cells, a booking plan), into the cells for a grid: row *k* is the mean of the monthly
  rows that step *k* spans, each whole month weighted the same (``weights="days"``
  weights them by days instead). The monthly booking tables are averaged only up to the
  future switch (1 Oct 2027) and ``Future_Bookings`` only from it, as the workflow reads
  them. Rows past the last step, and months a table has no row for, are left alone.
  This reproduces the cells of Kristoffer's H, Q, Y and QY runs to 5e-10.
- Cells for tables that aren't step-indexed pass through unchanged.
- :func:`resolve_settings` gives a grid's RESOLVE schedule settings. A grid that is
  monthly first ends ``ScheduleList[0]`` at the switch and adds ``ScheduleList[1]`` with
  the coarse step, as Kristoffer's QY run does.

Prefer the steps of a finished run on the grid (``results.timestamp``, less the end date
that results also report) over the prediction once one exists.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

import numpy as np
import pandas as pd

from alvheim_tiein.bookings import FUTURE_TABLES, MONTHLY_TABLES, future_start
from alvheim_tiein.levers import ModelTables, cell, cell_key

Weights = Literal["days", "months"]

FORECAST_START = pd.Timestamp("2026-07-01")
FORECAST_END = pd.Timestamp("2041-01-01")
FORCED_STEPS: tuple[pd.Timestamp, ...] = tuple(
    pd.Timestamp(d)
    for d in (
        "2026-09-01",
        "2026-10-01",
        "2027-05-01",
        "2027-06-01",
        "2027-07-01",
        "2028-08-01",
        "2028-10-01",
        "2029-01-01",
        "2029-02-01",
        "2029-04-01",
        "2030-01-01",
    )
)
"""Workflow well-opening dates where RESOLVE forces a step (comparison.md)."""

STEP_TABLES: dict[str, tuple[str, ...] | None] = {
    "Uptime_base": ("Uptime",),
    "Bookings_oil": None,
    "Bookings_gas": None,
    "Bookings_water": None,
    "Future_Bookings_TotGas": None,
    "Future_Bookings_Liquid": None,
}
"""Tables read by step index; None: every numeric column but the keys."""
KEY_COLUMNS = frozenset({"Month", "Date", "Booking", "Well"})
_TOL = 1e-6


@dataclass(frozen=True)
class Grid:
    """``step_months`` from ``monthly_until`` on (monthly before it); without
    ``monthly_until`` the whole forecast uses ``first_months`` steps."""

    name: str
    step_months: int
    monthly_until: pd.Timestamp | None = None
    first_months: int = 1

    def step_at(self, when: pd.Timestamp) -> int:
        if self.monthly_until is not None and when < self.monthly_until:
            return self.first_months
        return self.step_months if self.monthly_until is not None else self.first_months


GRIDS: dict[str, Grid] = {
    "monthly": Grid("monthly", 1),
    "mh": Grid("mh", 6, pd.Timestamp("2027-10-01")),
    "my": Grid("my", 12, pd.Timestamp("2027-10-01")),
    "mq": Grid("mq", 3, pd.Timestamp("2027-10-01")),
    "qy": Grid("qy", 12, pd.Timestamp("2027-10-01"), first_months=3),
    "q": Grid("q", 3, None, first_months=3),
    "h": Grid("h", 6, None, first_months=6),
    "y": Grid("y", 12, None, first_months=12),
}


def grid(name: str) -> Grid:
    if name not in GRIDS:
        raise KeyError(f"no grid {name!r}; grids: {', '.join(GRIDS)}")
    return GRIDS[name]


def predict_steps(
    g: Grid | str,
    *,
    start: pd.Timestamp = FORECAST_START,
    end: pd.Timestamp = FORECAST_END,
    forced: Iterable[pd.Timestamp] = FORCED_STEPS,
) -> list[pd.Timestamp]:
    """Step start dates: the fixed step from each step, cut at the next forced date."""
    g = grid(g) if isinstance(g, str) else g
    forced_dates = sorted(pd.Timestamp(f) for f in forced)
    steps, s = [], pd.Timestamp(start)
    while s < end:
        steps.append(s)
        nxt = s + pd.DateOffset(months=g.step_at(s))
        cut = next((f for f in forced_dates if s < f < nxt), None)
        s = cut if cut is not None else nxt
    return steps


def resolve_settings(g: Grid | str, *, end: pd.Timestamp = FORECAST_END) -> list[dict[str, object]]:
    """The ``resolve_settings`` that put a run on the grid (none for monthly, the
    model's own schedule)."""
    g = grid(g) if isinstance(g, str) else g
    tag = "RESOLVE.ScheduleList[{i}].{name}"

    def item(key: str, i: int, name: str, value: object) -> dict[str, object]:
        return {
            "key": key + (f"__R{i}" if i else ""),
            "tag": tag.format(i=i, name=name),
            "value": value,
        }

    if g.monthly_until is None:
        if g.first_months == 1:
            return []
        return [
            item("INITIAL_TIMESTEP", 0, "InitialTimestep", float(g.first_months)),
            item("INITIAL_TIMESTEP_TYPE", 0, "InitialTimestepType", 2),
        ]
    return [
        item("END_DATE", 0, "EndDate", g.monthly_until.strftime("%Y-%m-%d")),
        item("INITIAL_TIMESTEP", 0, "InitialTimestep", float(g.first_months)),
        item("INITIAL_TIMESTEP_TYPE", 0, "InitialTimestepType", 2),
        item("END_DATE", 1, "EndDate", pd.Timestamp(end).strftime("%Y-%m-%d")),
        item("TIMESTEP_MODE", 1, "TimestepMode", 0),
        item("INITIAL_TIMESTEP", 1, "InitialTimestep", float(g.step_months)),
        item("INITIAL_TIMESTEP_TYPE", 1, "InitialTimestepType", 2),
        item("MAX_TIMESTEP_TYPE", 1, "MaxTimestepType", 0),
        item("OPTIMISATION_MODE", 1, "OptimisationMode", 0),
        item("OPTIMISATION_FREQUENCY_TYPE", 1, "OptimisationFrequencyType", 0),
    ]


# ------------------------------------------------------------------- remap
def month_spans(start: pd.Timestamp, n: int) -> tuple[np.ndarray, np.ndarray]:
    """Start and end (exclusive) of monthly rows 0..n-1 as datetime64[ns]."""
    starts = pd.date_range(pd.Timestamp(start), periods=n + 1, freq="MS")
    return starts[:-1].to_numpy("datetime64[ns]"), starts[1:].to_numpy("datetime64[ns]")


def step_spans(steps: Sequence[pd.Timestamp], end: pd.Timestamp | None = None) -> np.ndarray:
    """Each step's end: the next step, or for the last one ``end`` (default: one more
    step of the previous length)."""
    s = pd.DatetimeIndex(sorted(pd.Timestamp(t) for t in steps))
    if len(s) == 0:
        return np.array([], dtype="datetime64[ns]")
    if end is None:
        end = s[-1] + (s[-1] - s[-2]) if len(s) > 1 else s[-1] + pd.offsets.MonthBegin(1)
    ends = [*s[1:], pd.Timestamp(end)]
    return pd.DatetimeIndex(ends).to_numpy("datetime64[ns]")


def overlap_weights(
    steps: Sequence[pd.Timestamp],
    n_rows: int,
    *,
    start: pd.Timestamp = FORECAST_START,
    end: pd.Timestamp | None = None,
    window: tuple[pd.Timestamp | None, pd.Timestamp | None] = (None, None),
    weights: Weights = "months",
) -> np.ndarray:
    """Weight of monthly row m in step k: a (steps x rows) matrix.

    ``days``: days of the month inside the step; ``months``: the fraction of the month
    inside it (every whole month counts the same, as in Kristoffer's remap). Only steps
    that start inside ``window`` (from, to) get weights, and only for the part of the
    step inside it: a table the workflow stops reading at a date is averaged up to it."""
    s = pd.DatetimeIndex(sorted(pd.Timestamp(t) for t in steps)).to_numpy("datetime64[ns]")
    e = step_spans(steps, end)
    lo_w, hi_w = window
    if hi_w is not None:
        e = np.minimum(e, np.datetime64(pd.Timestamp(hi_w), "ns"))
    m0, m1 = month_spans(start, n_rows)
    lo = np.maximum(s[:, None], m0[None, :])
    hi = np.minimum(e[:, None], m1[None, :])
    w = np.clip((hi - lo) / np.timedelta64(1, "D"), 0.0, None)
    if weights == "months":
        w = w / ((m1 - m0) / np.timedelta64(1, "D"))[None, :]
    inside = np.ones(len(s), dtype=bool)
    if lo_w is not None:
        inside &= s >= np.datetime64(pd.Timestamp(lo_w), "ns")
    if hi_w is not None:
        inside &= s < np.datetime64(pd.Timestamp(hi_w), "ns")
    return np.where(inside[:, None], w, 0.0)


def remap_values(
    values: Sequence[float],
    steps: Sequence[pd.Timestamp],
    *,
    start: pd.Timestamp = FORECAST_START,
    end: pd.Timestamp | None = None,
    window: tuple[pd.Timestamp | None, pd.Timestamp | None] = (None, None),
    weights: Weights = "months",
) -> np.ndarray:
    """Row k := weighted mean of the monthly rows step k spans (NaN where none, or where
    step k is outside ``window``)."""
    v = np.asarray([np.nan if x is None else float(x) for x in values], dtype=float)
    w = overlap_weights(steps, len(v), start=start, end=end, window=window, weights=weights)
    w = np.where(np.isnan(v)[None, :], 0.0, w)
    total = w.sum(axis=1)
    num = (w * np.nan_to_num(v)[None, :]).sum(axis=1)
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(total > 0, num / total, np.nan)


def table_window(
    tables: ModelTables, alias: str
) -> tuple[pd.Timestamp | None, pd.Timestamp | None]:
    """When the workflow reads a table: the monthly bookings before the future switch,
    the future bookings from it, anything else always."""
    if alias in MONTHLY_TABLES.values() or alias in FUTURE_TABLES.values():
        switch = future_start(tables.payload)
        return (None, switch) if alias in MONTHLY_TABLES.values() else (switch, None)
    return (None, None)


def _numeric(values: Sequence[object]) -> bool:
    for x in values:
        if x is None:
            continue
        try:
            float(x)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return False
    return True


def step_columns(
    tables: ModelTables, step_tables: Mapping[str, tuple[str, ...] | None] = STEP_TABLES
) -> list[tuple[str, str]]:
    """(alias, column) of every step-indexed column the model has."""
    out = []
    for alias, columns in step_tables.items():
        if not tables.has(alias):
            continue
        cols = tables.columns(alias)
        names = columns or [c for c in cols if c not in KEY_COLUMNS and _numeric(cols[c])]
        out += [(alias, c) for c in names if c in cols]
    return out


def effective_column(
    tables: ModelTables, alias: str, column: str, overrides: Iterable[Mapping[str, object]]
) -> list[float]:
    """The column's monthly values with override cells applied."""
    base = [tables.value(alias, column, r) for r in range(len(tables.column(alias, column)))]
    for item in overrides:
        if item["object_alias"] == alias and item["table_name"] == column:
            row = int(item["index"])  # type: ignore[arg-type]
            vals = item.get("values") or [np.nan]
            if row < len(base):
                base[row] = float(vals[0])  # type: ignore[index, arg-type]
    return base


def remap_cells(
    tables: ModelTables,
    steps: Sequence[pd.Timestamp],
    *,
    overrides: Iterable[Mapping[str, object]] = (),
    start: pd.Timestamp = FORECAST_START,
    end: pd.Timestamp | None = FORECAST_END,
    step_tables: Mapping[str, tuple[str, ...] | None] = STEP_TABLES,
    weights: Weights = "months",
) -> list[dict[str, object]]:
    """Cells that put a monthly plan (the model plus ``overrides``) on a grid.

    Step-indexed rows the workflow reads (see :func:`table_window`) that differ from the
    model's are written; override cells for other tables pass through. On the monthly
    grid this gives back the overrides of rows the workflow reads."""
    overrides = list(overrides)
    stepped = set(step_columns(tables, step_tables))
    out: dict[tuple[str, str, int], dict[str, object]] = {}
    for item in overrides:
        if (str(item["object_alias"]), str(item["table_name"])) not in stepped:
            out[cell_key(item)] = dict(item)
    n_steps = len(steps)
    for alias, column in sorted(stepped):
        monthly = effective_column(tables, alias, column, overrides)
        remapped = remap_values(
            monthly,
            steps,
            start=start,
            end=end,
            window=table_window(tables, alias),
            weights=weights,
        )
        for k in range(min(n_steps, len(monthly))):
            new = remapped[k]
            old = tables.value(alias, column, k)
            if np.isnan(new) or (not np.isnan(old) and abs(new - old) <= _TOL * max(1, abs(old))):
                continue
            out[(alias, column, k)] = cell(alias, column, k, float(new))
    return list(out.values())


def remap_table(
    tables: ModelTables,
    steps: Sequence[pd.Timestamp],
    *,
    overrides: Iterable[Mapping[str, object]] = (),
    start: pd.Timestamp = FORECAST_START,
    end: pd.Timestamp | None = FORECAST_END,
    weights: Weights = "months",
) -> pd.DataFrame:
    """Long table of every step-indexed row read on the grid: step, date, monthly value
    at row k (what an unremapped run would read) and the remapped value."""
    overrides = list(overrides)
    rows = []
    ordered = sorted(pd.Timestamp(t) for t in steps)
    for alias, column in step_columns(tables):
        monthly = effective_column(tables, alias, column, overrides)
        window = table_window(tables, alias)
        remapped = remap_values(
            monthly, ordered, start=start, end=end, window=window, weights=weights
        )
        for k in range(min(len(ordered), len(monthly))):
            if np.isnan(remapped[k]):
                continue
            rows.append(
                {
                    "object_alias": alias,
                    "table_name": column,
                    "row": k,
                    "step": ordered[k],
                    "unmapped": monthly[k],
                    "remapped": remapped[k],
                }
            )
    return pd.DataFrame(rows)
