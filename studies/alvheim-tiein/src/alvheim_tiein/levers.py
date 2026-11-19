"""Levers: bounded parameters written into the model's DataObject tables.

The Alvheim workflow rewrites well and group settings from DataObject tables at every
step, so a lever is a set of table cells, the ``dataobject_tables`` of a simulate
request: ``{object_alias, table_name (the column), index (the row), values: [v]}``.
Values are in table units: rates in Sm3/d, gas in 1000 Sm3/d.

Transforms (research/22, "Shared Building Blocks"):

- weights ``w(alpha) = 1 + alpha (w0 - 1)``: alpha = 1 is today, 0 is neutral;
- released caps ``cap(beta) = B + beta (L - B)`` per group, phase and window, with L
  the FPSO limit of the phase;
- the future liquid booking scale ``gamma``;
- single per-well cells (``Wells_constraints`` ``MaxGasInj``, ``MaxLiquidRate``, ...);
- any booking plan in Sm3/d (scheme 4 restructuring) written to the cells the
  workflow reads for each step (:func:`alvheim_tiein.bookings.booking_cells`).

:func:`cells_for` turns an optimisation point (lever name to value) into cells.
"""

from __future__ import annotations

import json
import math
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any, Literal

import pandas as pd
from pydantic import BaseModel, Field, model_validator

from alvheim_tiein.bookings import (
    FLAT_FUTURE,
    FUTURE_TABLES,
    GAS_TABLE_TO_SM3D,
    MONTHLY_TABLES,
    booking_cells,
    booking_groups,
)

WEIGHT_TABLES = ("Weightings", "Weightings2025")
WELL_TABLES = ("Wells_constraints", "Wells_data")
Window = Literal["booking", "future", "all"]
_DIGITS = 6


def cell(alias: str, column: str, row: int, value: float) -> dict[str, Any]:
    """One DataObject cell in the simulate request's format."""
    return {
        "object_alias": alias,
        "table_name": column,
        "index": int(row),
        "values": [round(float(value), _DIGITS)],
    }


def cell_key(item: Mapping[str, Any]) -> tuple[str, str, int]:
    return (str(item["object_alias"]), str(item["table_name"]), int(item["index"]))


def merge_cells(*lists: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Cells from several levers; a later list wins where two write the same cell."""
    out: dict[tuple[str, str, int], dict[str, Any]] = {}
    for items in lists:
        for item in items:
            out[cell_key(item)] = dict(item)
    return list(out.values())


class ModelTables:
    """The model's DataObject tables (``GET /models/{id}/dataobject-tables``)."""

    def __init__(self, payload: Mapping[str, Any]) -> None:
        self.payload = payload
        self._cols: dict[str, dict[str, list[Any]]] = {}
        for t in payload.get("tables") or []:
            self._cols.setdefault(t["object_alias"], {})[t["table_name"]] = list(
                t.get("values") or []
            )

    @classmethod
    def from_file(cls, path: Path) -> ModelTables:
        return cls(json.loads(path.read_text(encoding="utf-8")))

    def has(self, alias: str) -> bool:
        return alias in self._cols

    def columns(self, alias: str) -> dict[str, list[Any]]:
        if alias not in self._cols:
            raise KeyError(f"no DataObject {alias!r} in the model")
        return self._cols[alias]

    def column(self, alias: str, name: str) -> list[Any]:
        cols = self.columns(alias)
        if name not in cols:
            raise KeyError(f"{alias} has no column {name!r}; columns: {sorted(cols)}")
        return cols[name]

    def value(self, alias: str, name: str, row: int) -> float:
        col = self.column(alias, name)
        if row >= len(col) or col[row] is None:
            return math.nan
        try:
            return float(col[row])
        except (TypeError, ValueError):
            return math.nan

    def row_of(self, alias: str, key_column: str, key: str) -> int:
        keys = [str(k) for k in self.column(alias, key_column)]
        if key not in keys:
            raise KeyError(f"{alias}.{key_column} has no {key!r}")
        return keys.index(key)


# ---------------------------------------------------------------- FPSO limits
def fpso_limits(tables: ModelTables, *, gas_upgrade: bool = True) -> dict[str, float]:
    """FPSO limits per phase in Sm3/d from ``Capacities`` (and ``Gas_upgrade``).

    The model has no liquid capacity cell; liquid is bounded by oil + water here, an
    upper bound only. Pass explicit limits where it matters."""
    cap = tables.columns("Capacities")
    oil = float(cap["TotalOil_Capacity"][0])
    water = float(cap["Maximumwaterrate"][0])
    gas = float(cap["TotalGas_Capacity"][0])
    if gas_upgrade and tables.has("Gas_upgrade"):
        gas = float(tables.column("Gas_upgrade", "TotalGas_capacity")[0])
    return {"oil": oil, "gas": gas * GAS_TABLE_TO_SM3D, "water": water, "liquid": oil + water}


# -------------------------------------------------------------------- weights
def weight_cells(
    tables: ModelTables,
    alpha: float,
    *,
    aliases: Sequence[str] = WEIGHT_TABLES,
    wells: Sequence[str] | None = None,
) -> list[dict[str, Any]]:
    """``w = 1 + alpha (w0 - 1)`` for every listed well in each weight table (both by
    default: which one applies when is not known yet, M6)."""
    out = []
    for alias in aliases:
        if not tables.has(alias):
            continue
        names = tables.column(alias, "Well")
        for row, well in enumerate(names):
            if wells is not None and str(well) not in wells:
                continue
            w0 = tables.value(alias, "Weight", row)
            if math.isnan(w0):
                continue
            out.append(cell(alias, "Weight", row, 1.0 + alpha * (w0 - 1.0)))
    return out


# ------------------------------------------------------------------- bookings
def _window_aliases(window: Window) -> set[str]:
    booking = set(MONTHLY_TABLES.values())
    future = {*FUTURE_TABLES.values(), FLAT_FUTURE}
    return {"booking": booking, "future": future, "all": booking | future}[window]


def _booking_map(
    tables: ModelTables, periods: Sequence[pd.Timestamp], groups: Sequence[str] | None
) -> pd.DataFrame:
    cells = booking_cells(tables.payload, periods, groups)
    return cells[cells["object_alias"].notna()].reset_index(drop=True)


def _unique_cells(frame: pd.DataFrame, column: str) -> list[dict[str, Any]]:
    """One cell per (alias, column, row). A cell several steps share (the flat future
    table) must get one value."""
    out: dict[tuple[str, str, int], float] = {}
    for r in frame.itertuples(index=False):
        key = (str(r.object_alias), str(r.table_name), int(r.row))
        value = float(getattr(r, column))
        if key in out and not math.isclose(out[key], value, rel_tol=1e-9, abs_tol=1e-9):
            raise ValueError(
                f"{key[0]}.{key[1]} row {key[2]} is read by several steps that would need "
                f"different values ({out[key]:g}, {value:g}); give one value for it"
            )
        out[key] = value
    return [cell(a, c, r, v) for (a, c, r), v in out.items()]


def release_cells(
    tables: ModelTables,
    periods: Sequence[pd.Timestamp],
    beta: float | Mapping[str, float],
    *,
    limits: Mapping[str, float],
    window: Window = "booking",
    phases: Sequence[str] | None = None,
    groups: Sequence[str] | None = None,
) -> list[dict[str, Any]]:
    """``cap = B + beta (L - B)`` for the cells the run's steps read in ``window``.

    ``beta`` is one value or one per group (groups not given keep their booking)."""
    if groups is None:
        groups = list(beta) if isinstance(beta, Mapping) else booking_groups(tables.payload)
    m = _booking_map(tables, periods, groups)
    m = m[m["object_alias"].isin(_window_aliases(window))]
    if phases is not None:
        m = m[m["phase"].isin(phases)]
    if m.empty:
        return []
    b = m["group"].map(beta) if isinstance(beta, Mapping) else pd.Series(float(beta), m.index)
    m = m.assign(beta=b.astype(float)).dropna(subset=["beta", "table_value"])
    limit = m["phase"].map(limits).astype(float) / m["factor"]
    m = m.assign(new=m["table_value"] + m["beta"] * (limit - m["table_value"]))
    return _unique_cells(m, "new")


def liquid_scale_cells(
    tables: ModelTables,
    periods: Sequence[pd.Timestamp],
    gamma: float,
    *,
    groups: Sequence[str] | None = None,
) -> list[dict[str, Any]]:
    """Future liquid bookings times ``gamma`` (the water/liquid balancing lever)."""
    m = _booking_map(tables, periods, groups)
    m = m[(m["phase"] == "liquid") & m["object_alias"].isin(_window_aliases("future"))]
    m = m.dropna(subset=["table_value"]).assign(new=lambda f: f["table_value"] * gamma)
    return _unique_cells(m, "new")


def booking_plan_cells(
    tables: ModelTables,
    periods: Sequence[pd.Timestamp],
    plan: pd.DataFrame,
    *,
    rel_tol: float = 1e-6,
) -> list[dict[str, Any]]:
    """Cells that make the model book ``plan`` (``group, period, phase, booked_sm3d``).

    Only cells whose value changes are returned. A plan value for a phase the window
    doesn't book (oil after the monthly tables) is an error, as is a shared flat cell
    asked for different values by different steps."""
    groups = sorted(plan["group"].unique())
    m = _booking_map(tables, periods, groups)
    p = plan.assign(period=pd.to_datetime(plan["period"]).astype("datetime64[ns]"))
    joined = p.merge(m, on=["group", "period", "phase"], how="left")
    unmapped = joined[joined["object_alias"].isna() & joined["booked_sm3d"].notna()]
    if not unmapped.empty:
        first = unmapped.iloc[0]
        raise ValueError(
            f"no booking cell for {first['group']} {first['phase']} at "
            f"{pd.Timestamp(first['period']).date()} ({len(unmapped)} such rows): that "
            "window doesn't book this phase"
        )
    joined = joined.dropna(subset=["object_alias", "booked_sm3d"])
    joined = joined.assign(new=joined["booked_sm3d"] / joined["factor"])
    changed = ~pd.Series(
        [
            math.isclose(n, o, rel_tol=rel_tol, abs_tol=1e-9) if not math.isnan(o) else False
            for n, o in zip(joined["new"], joined["table_value"], strict=True)
        ],
        index=joined.index,
    )
    keys = ["object_alias", "table_name", "row"]
    touched = joined.loc[changed, keys].drop_duplicates()
    return _unique_cells(joined.merge(touched, on=keys), "new")


# ------------------------------------------------------------------ well cells
def well_cell(
    tables: ModelTables,
    well: str,
    column: str,
    value: float,
    *,
    alias: str = "Wells_constraints",
) -> dict[str, Any]:
    """One per-well cell, found by the table's ``Well`` column."""
    tables.column(alias, column)
    return cell(alias, column, tables.row_of(alias, "Well", well), value)


# ------------------------------------------------------------ optimisation map
LeverKind = Literal["weights", "release", "liquid_scale", "well_cell"]


class LeverDef(BaseModel):
    """A named lever, its bounds and what it writes.

    - ``weights``: alpha on the weight tables (``wells`` optional);
    - ``release``: beta for ``groups`` in ``window`` (``phases`` optional);
    - ``liquid_scale``: gamma on future liquid bookings (``groups`` optional);
    - ``well_cell``: the value of ``column`` for each of ``wells`` in ``alias``."""

    name: str = Field(pattern=r"^[A-Za-z0-9_.+-]+$")
    kind: LeverKind
    lower: float
    upper: float
    baseline: float | None = None
    levels: list[float] | None = None
    groups: list[str] | None = None
    wells: list[str] | None = None
    window: Window = "booking"
    phases: list[str] | None = None
    column: str | None = None
    alias: str = "Wells_constraints"

    @model_validator(mode="after")
    def _check(self) -> LeverDef:
        if self.lower > self.upper:
            raise ValueError(f"lever {self.name}: lower {self.lower} > upper {self.upper}")
        if self.kind == "well_cell" and (not self.wells or not self.column):
            raise ValueError(f"lever {self.name}: well_cell needs `wells` and `column`")
        if self.baseline is not None and not self.lower <= self.baseline <= self.upper:
            raise ValueError(f"lever {self.name}: baseline outside its bounds")
        return self


def cells_for(
    theta: Mapping[str, float],
    levers: Sequence[LeverDef],
    tables: ModelTables,
    periods: Sequence[pd.Timestamp],
    *,
    limits: Mapping[str, float] | None = None,
) -> list[dict[str, Any]]:
    """The cells for one point. Every lever must have a value inside its bounds."""
    out: list[list[dict[str, Any]]] = []
    for lever in levers:
        if lever.name not in theta:
            raise KeyError(f"no value for lever {lever.name}")
        v = float(theta[lever.name])
        if not lever.lower - 1e-12 <= v <= lever.upper + 1e-12:
            raise ValueError(f"lever {lever.name}={v} outside [{lever.lower}, {lever.upper}]")
        if lever.kind == "weights":
            out.append(weight_cells(tables, v, wells=lever.wells))
        elif lever.kind == "release":
            lim = limits or fpso_limits(tables)
            groups = lever.groups or booking_groups(tables.payload)
            out.append(
                release_cells(
                    tables,
                    periods,
                    dict.fromkeys(groups, v),
                    limits=lim,
                    window=lever.window,
                    phases=lever.phases,
                )
            )
        elif lever.kind == "liquid_scale":
            out.append(liquid_scale_cells(tables, periods, v, groups=lever.groups))
        else:
            assert lever.wells is not None and lever.column is not None
            out.append(
                [well_cell(tables, w, lever.column, v, alias=lever.alias) for w in lever.wells]
            )
    return merge_cells(*out)
