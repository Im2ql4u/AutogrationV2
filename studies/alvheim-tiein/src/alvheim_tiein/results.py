"""Load downloaded Autogration results and turn rates into period volumes.

Rows follow Autogration's per-task Parquet contract (``GET /runs/{task_id}/results/parquet``):
module, system, identifier, identifier_type, timestamp, run_number, property_name, value,
unit. Units follow the model's own unit system, so conversion is explicit and unknown
units are an error rather than a silent pass-through.
"""

from __future__ import annotations

import shutil
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

SENTINEL_ABS = 1e35  # GAP/RESOLVE "no value"
SM3_PER_BBL = 0.158987295
SM3_PER_SCF = 0.0283168466

# Rate unit -> factor to Sm3/d.
RATE_TO_SM3D: dict[str, float] = {
    "sm3/day": 1.0,
    "sm3/d": 1.0,
    "ksm3/day": 1e3,
    "ksm3/d": 1e3,
    "1000sm3/day": 1e3,
    "1000sm3/d": 1e3,
    "e3sm3/d": 1e3,
    "msm3/day": 1e6,
    "msm3/d": 1e6,
    "stb/day": SM3_PER_BBL,
    "stb/d": SM3_PER_BBL,
    "bbl/day": SM3_PER_BBL,
    "bbl/d": SM3_PER_BBL,
    "scf/day": SM3_PER_SCF,
    "mscf/day": 1e3 * SM3_PER_SCF,
    "mmscf/day": 1e6 * SM3_PER_SCF,
}
# Cumulative unit -> factor to Sm3.
CUM_TO_SM3: dict[str, float] = {
    "sm3": 1.0,
    "ksm3": 1e3,
    "1000sm3": 1e3,
    "msm3": 1e6,
    "gsm3": 1e9,
    "stb": SM3_PER_BBL,
    "mstb": 1e3 * SM3_PER_BBL,
    "mmstb": 1e6 * SM3_PER_BBL,
    "mscf": 1e3 * SM3_PER_SCF,
    "mmscf": 1e6 * SM3_PER_SCF,
    "bscf": 1e9 * SM3_PER_SCF,
}
PHASES = {"oil": "Oil", "gas": "Gas", "water": "Wat"}


def load_task_results(case_rows: Iterable[Mapping[str, Any]], results_dir: Path) -> pd.DataFrame:
    """Concatenate ``<results_dir>/<task_id>.parquet`` for completed cases, tagged with
    ``case_name``, ``arm`` and ``task_id``."""
    frames = []
    for row in case_rows:
        path = results_dir / f"{row['task_id']}.parquet"
        if row.get("status") != "Completed" or not path.exists():
            continue
        df = pd.read_parquet(path)
        frames.append(
            df.assign(case_name=row["case_name"], arm=row.get("arm"), task_id=row["task_id"])
        )
    if not frames:
        raise FileNotFoundError(f"no downloaded results of completed cases in {results_dir}")
    out = pd.concat(frames, ignore_index=True)
    out["timestamp"] = pd.to_datetime(out["timestamp"])
    return out


def export_workbench_folder(
    case_rows: list[Mapping[str, Any]],
    results_dir: Path,
    out_dir: Path,
    *,
    baseline: str,
    entities_csv: Path | None = None,
) -> Path:
    """Write a results-workbench study folder (results/*.parquet, cases.csv, entities.csv).

    Each task's cases restart at 1, so cases get study-wide run numbers here."""
    target = out_dir / "results"
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)
    cases = []
    for run_number, row in enumerate(case_rows, start=1):
        src = results_dir / f"{row['task_id']}.parquet"
        if row["status"] == "Completed" and src.exists():
            df = pd.read_parquet(src)
            df["run_number"] = np.int32(run_number)
            df.to_parquet(target / f"{row['task_id']}.parquet", index=False)
        cases.append(
            {
                "run_number": run_number,
                "case_name": row["case_name"],
                "task_id": row["task_id"],
                "status": row["status"],
                "is_baseline": row["case_name"] == baseline,
                "arm": row.get("arm"),
            }
        )
    pd.DataFrame(cases).to_csv(out_dir / "cases.csv", index=False)
    if entities_csv is not None and entities_csv.exists():
        shutil.copyfile(entities_csv, out_dir / "entities.csv")
    return out_dir


def _factor(units: pd.Series, table: Mapping[str, float], what: str) -> pd.Series:
    keys = units.fillna("").str.strip().str.lower()
    unknown = sorted(set(keys) - set(table))
    if unknown:
        raise ValueError(f"unknown {what} unit(s) {unknown}; add them to the conversion table")
    return keys.map(table).astype(float)


def _period_days(timestamps: pd.Series) -> pd.DataFrame:
    """Days each timestep's rate applies for: to the next timestep; the last step gets
    its calendar month if the grid is monthly, otherwise the previous step's length."""
    ts = pd.Series(sorted(timestamps.unique()))
    days = (ts.shift(-1) - ts).dt.days.astype(float)
    if len(ts):
        monthly = bool((ts.dt.day == 1).all())
        last = ts.iloc[-1]
        days.iloc[-1] = (
            float(last.days_in_month) if monthly or len(ts) == 1 else float(days.iloc[-2])
        )
    return pd.DataFrame({"timestamp": ts, "days": days})


def period_volumes(
    results: pd.DataFrame,
    *,
    case_col: str = "case_name",
    identifier_type: str | None = "WELL",
    prefer_average: bool = True,
) -> pd.DataFrame:
    """Oil, gas and water volumes (Sm3) per case, identifier and timestep.

    Uses calendar-day ``Avg*Rate`` (including downtime) when present, as results-workbench
    does, times the days to the next timestep. Check the convention against cumulative
    series with :func:`volume_convention_check` on the first real run."""
    df = (
        results
        if identifier_type is None
        else results[results["identifier_type"] == identifier_type]
    )
    out = None
    for phase, prop in PHASES.items():
        names = [f"Avg{prop}Rate", f"{prop}Rate"] if prefer_average else [f"{prop}Rate"]
        part = df[df["property_name"].isin(names)].copy()
        if part.empty:
            continue
        part["rank"] = part["property_name"].map({n: i for i, n in enumerate(names)})
        best = part.groupby([case_col, "identifier"])["rank"].transform("min")
        part = part[part["rank"] == best]
        value = part["value"].where(part["value"].abs() < SENTINEL_ABS)
        part[f"{phase}_rate_sm3d"] = value * _factor(part["unit"], RATE_TO_SM3D, "rate")
        part = part[[case_col, "identifier", "timestamp", f"{phase}_rate_sm3d"]]
        out = (
            part
            if out is None
            else out.merge(part, on=[case_col, "identifier", "timestamp"], how="outer")
        )
    if out is None:
        raise ValueError("no oil, gas or water rate series in the results")
    days = pd.concat(
        [_period_days(g["timestamp"]).assign(**{case_col: c}) for c, g in out.groupby(case_col)],
        ignore_index=True,
    )
    out = out.merge(days, on=[case_col, "timestamp"], how="left")
    for phase in PHASES:
        col = f"{phase}_rate_sm3d"
        out[f"{phase}_sm3"] = out[col].fillna(0.0) * out["days"] if col in out else 0.0
    keep = [case_col, "identifier", "timestamp", "days", *(f"{p}_sm3" for p in PHASES)]
    out = out[keep].rename(columns={"timestamp": "period"})
    return out.sort_values([case_col, "identifier", "period"]).reset_index(drop=True)


def volume_convention_check(results: pd.DataFrame, *, case_col: str = "case_name") -> pd.DataFrame:
    """Compare oil volumes from rates with cumulative-oil increments.

    ``forward`` assumes a timestep's rate applies until the next timestep (what
    :func:`period_volumes` does); ``backward`` assumes it applies since the previous one.
    The convention with the smaller relative error is the one the model follows."""
    wells = results[results["identifier_type"] == "WELL"]
    rates = wells[wells["property_name"].isin(["AvgOilRate", "OilRate"])].copy()
    rates = rates[
        rates["property_name"]
        == rates.groupby([case_col, "identifier"])["property_name"].transform("min")
    ]
    cums = wells[wells["property_name"] == "CumOil"].copy()
    if rates.empty or cums.empty:
        return pd.DataFrame(columns=["convention", "relative_error"])
    rates["q"] = rates["value"].where(rates["value"].abs() < SENTINEL_ABS) * _factor(
        rates["unit"], RATE_TO_SM3D, "rate"
    )
    cums["c"] = cums["value"].where(cums["value"].abs() < SENTINEL_ABS) * _factor(
        cums["unit"], CUM_TO_SM3, "cumulative"
    )
    df = rates[[case_col, "identifier", "timestamp", "q"]].merge(
        cums[[case_col, "identifier", "timestamp", "c"]], on=[case_col, "identifier", "timestamp"]
    )
    df = df.sort_values([case_col, "identifier", "timestamp"])
    g = df.groupby([case_col, "identifier"])
    dt_days = (g["timestamp"].shift(-1) - df["timestamp"]).dt.days
    dcum = g["c"].shift(-1) - df["c"]
    forward = (df["q"] * dt_days - dcum).abs().sum()
    backward = (g["q"].shift(-1) * dt_days - dcum).abs().sum()
    total = dcum.abs().sum()
    return pd.DataFrame(
        {
            "convention": ["forward", "backward"],
            "relative_error": [forward / total, backward / total],
        }
    )
