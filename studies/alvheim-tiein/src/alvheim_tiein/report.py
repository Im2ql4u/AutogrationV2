"""Load a project's runs and model data for analysis, from the CLI or a notebook.

Model data is cached per registered model in ``data/models/<model_id>/``
(``dataobject-tables.json``, ``groups.json``); results and tracked steps per project.
With an API client, what is missing is fetched; without one, the caches must exist.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from alvheim_tiein import bookings
from alvheim_tiein.client import AutogrationClient, step_results_frame
from alvheim_tiein.economics import load_shares
from alvheim_tiein.project import Project, ProjectPaths, Workspace
from alvheim_tiein.results import load_task_results


@dataclass
class ProjectData:
    slug: str
    project: Project
    paths: ProjectPaths
    runs: pd.DataFrame
    """One row per run of the current revision of each case (see ``RunLog.rows``)."""

    @property
    def baseline_name(self) -> str:
        names = self.runs.loc[self.runs["is_baseline"], "case_name"].unique()
        if len(names) != 1:
            raise ValueError(f"the baseline should be one run, found {list(names)}")
        return str(names[0])

    def completed(self) -> pd.DataFrame:
        return self.runs[self.runs["status"] == "Completed"]


def load_project(ws: Workspace, slug: str | None = None) -> ProjectData:
    project, paths, log = ws.load(slug)
    rows = pd.DataFrame(
        log.rows(project),
        columns=[
            "case",
            "run",
            "case_name",
            "is_baseline",
            "switch",
            "based_on",
            "revision",
            "imported",
            "task_id",
            "status",
        ],
    )
    return ProjectData(ws.resolve(slug), project, paths, rows)


def _model_dir(ws: Workspace, model_id: str) -> Path:
    return ws.data_dir / "models" / model_id


def dataobject_tables(
    ws: Workspace, model_id: str, api: AutogrationClient | None = None
) -> dict[str, Any]:
    path = _model_dir(ws, model_id) / "dataobject-tables.json"
    if not path.exists():
        if api is None:
            raise FileNotFoundError(f"{path}: run `tiein bookings` once with API access")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(api.dataobject_tables(model_id), indent=2), encoding="utf-8")
    return json.loads(path.read_text(encoding="utf-8"))


def group_members(
    ws: Workspace, model_id: str, groups: list[str], api: AutogrationClient | None = None
) -> dict[str, list[str]]:
    path = _model_dir(ws, model_id) / "groups.json"
    cached: dict[str, list[str]] = (
        json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    )
    missing = [g for g in groups if g not in cached]
    if missing:
        if api is None:
            raise FileNotFoundError(f"{path} lacks {missing}: run `tiein bookings` with API access")
        cached.update(bookings.group_members(api, model_id, missing))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(cached, indent=2, sort_keys=True), encoding="utf-8")
    return {g: cached[g] for g in groups}


def steps(data: ProjectData, task_id: str, api: AutogrationClient | None = None) -> pd.DataFrame:
    """Tracked variables of a run, cached in the project's steps folder once it finished."""
    path = data.paths.steps / f"{task_id}.csv"
    if path.exists():
        return pd.read_csv(path, parse_dates=["time"])
    if api is None:
        return pd.DataFrame(columns=["task_id", "vm_id", "time", "variable", "value"])
    frame = step_results_frame(api.step_results(task_id))
    status = data.runs.loc[data.runs["task_id"] == task_id, "status"]
    if not status.empty and status.iloc[0] == "Completed":
        path.parent.mkdir(parents=True, exist_ok=True)
        frame.to_csv(path, index=False)
    return frame


def booking_report(
    ws: Workspace, data: ProjectData, api: AutogrationClient | None = None
) -> bookings.BookingReport:
    """Booked vs produced for the project's completed runs. Runs that tracked the
    applied group limits use those; the others fall back to the model's booking
    tables, read by step number on that run's own time steps (as the workflow does)."""
    project = data.project
    done = data.completed()
    results = load_task_results(done.to_dict("records"), data.paths.results)
    tables = dataobject_tables(ws, project.model_id, api)
    groups = project.bookings.groups or bookings.booking_groups(tables)
    members = group_members(ws, project.model_id, groups, api)

    booked, lift = [], []
    for row in done.itertuples():
        tracked = steps(data, row.task_id, api)
        applied = bookings.booked_from_steps(tracked)
        applied = applied[applied["group"].isin(groups)]
        if applied.empty:
            periods = results.loc[results["task_id"] == row.task_id, "timestamp"].unique()
            source, kind = bookings.booked_from_tables(tables, periods, groups), "tables"
        else:
            source, kind = applied, "applied"
        booked.append(source.assign(case_name=row.case_name, source=kind))
        if project.bookings.lift_gas_property:
            series = bookings.group_series_from_steps(tracked, project.bookings.lift_gas_property)
            lift.append(series[series["group"].isin(groups)].assign(case_name=row.case_name))
    booked_frame = pd.concat(booked, ignore_index=True)
    lift_frame = pd.concat(lift, ignore_index=True) if lift else None

    ref = ws.reference_dir(data.paths)
    entities = pd.read_csv(ref / "entities.csv", dtype={"identifier": str, "license": str})
    shares = load_shares(ref / "licence_shares.csv")
    unbooked = (
        {project.switch.label: [w.name for w in project.switch.wells]} if project.switch else {}
    )
    report = bookings.BookingReport(
        results,
        booked_frame.drop(columns=["source"]),
        members,
        entities,
        shares,
        baseline=data.baseline_name,
        unbooked=unbooked,
        lift_gas=lift_frame,
    )
    report.sources = booked_frame[["case_name", "source"]].drop_duplicates()
    return report


def write_booking_report(report: bookings.BookingReport, out_dir: Path) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    frames = {
        "summary": report.summary(),
        "satisfaction": report.satisfaction(),
        "violations": report.violations(),
        "company_delta": report.company_delta(),
        "change_vs_baseline": report.change_vs_baseline(),
        "well_contributions": report.well_contributions(),
    }
    written = {}
    for name, frame in frames.items():
        path = out_dir / f"{name}.csv"
        frame.to_csv(path, index=False)
        written[name] = path
    return written


__all__ = [
    "ProjectData",
    "booking_report",
    "dataobject_tables",
    "group_members",
    "load_project",
    "steps",
    "write_booking_report",
]
