"""Projects: an optional way to group Autogration runs with a type, a baseline and cases.

Runs don't have to belong to a project: ``tiein run`` submits a one-off request and
logs it in ``data/adhoc/``. A project adds structure when runs are compared. It lives
in ``data/projects/<slug>/``:

- ``project.yaml``: what it is (the definition below);
- ``runs.json``: the run log, which ties each case to the Autogration tasks it ran;
- ``results/``, ``steps/``, ``bundles/``, ``bookings/``, ``workbench/``: downloads and
  analysis output.

Every project compares cases against one baseline:

- a *case comparison* is about a new reservoir (the switch): the baseline has it
  switched off (its wells shut from the first step) and other cases switch it on;
- a *scenario comparison* has no switch: the cases differ only by their changes (for
  example bookings lifted or relaxed).

A case can build on another (``based_on``) and inherits its changes, so a tuned
baseline and the tie-in on top of it share the tuning by construction. A case can also
be *imported*: runs made elsewhere (by anyone, on the same environment) attached with
``tiein project add-run`` so they can be compared with the rest.

Each submitted case is one ``POST /models/{model_id}/simulate`` request; sweeps in its
changes expand into several runs. :func:`check_run_budget` refuses requests that would
start too many runs at once. A project names its environment, so its runs, model and
results never mix with another environment's.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
from collections.abc import Iterable, Mapping
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator

HARD_MAX_ACTIVE_RUNS = 50
"""No project may set a run limit above this: the shared dev/test VM pool is small."""

PETEX_EPOCH = dt.date(1899, 12, 31)
_SWITCH_EVENT_INDEX = 900
_GAP_PREFIX = re.compile(r"^\s*GAP(?=\.)", re.IGNORECASE)
_SLUG = r"^[a-z0-9][a-z0-9-]{0,62}$"
_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
CHANGE_KEYS = (
    "assumptions",
    "dataobject_tables",
    "resolve_settings",
    "module_settings",
    "schedule_ops",
    "exclude",
    "include_base_case",
)
_INHERITED_KEYS = CHANGE_KEYS[:5]
BOOKING_CONSTRAINTS = ("MaxQoil", "MaxQTotGas", "MaxQwat", "MaxQliq")


class ProjectError(ValueError):
    """A project is missing, invalid, or asked to do something it may not."""


class ProjectType(StrEnum):
    CASE_COMPARISON = "case_comparison"
    SCENARIO_COMPARISON = "scenario_comparison"


def petex_serial(day: dt.date | str) -> int:
    """OpenServer date serial (days since 1899-12-31). GAP rejects ISO dates in
    schedule events ("Invalid date") and Autogration passes them through as given."""
    if isinstance(day, str):
        day = dt.date.fromisoformat(day)
    return (day - PETEX_EPOCH).days


def resolve_tracked_variable(tag: str) -> str:
    """Address a GAP tag through RESOLVE, as the web app does: inside a run GAP is
    `resolve.module[0]`; a bare `GAP.` tag fails with OpenServer error 11."""
    return _GAP_PREFIX.sub("resolve.module[0]", tag.strip())


class SwitchWell(BaseModel):
    name: str = Field(min_length=1)
    path: str = Field(pattern=r"^RESOLVE\.", description="Equipment path in the model.")


class Switch(BaseModel):
    """What 'activating the new reservoir' means: its wells, shut in switched-off cases.

    WELL_OFF events from ``off_from`` (the forecast start) shut them, but a model that
    opens the wells itself (a RESOLVE workflow) undoes that. ``off_changes`` are then
    applied as well in every switched-off case: changes the model can't undo, such as
    zero rate limits in the tables its workflow reads."""

    label: str = Field(min_length=1)
    wells: list[SwitchWell] = Field(min_length=1)
    off_from: dt.date
    off_events: bool = Field(default=True, description="WELL_OFF events from off_from.")
    off_changes: dict[str, Any] = Field(default_factory=dict)

    @field_validator("off_changes")
    @classmethod
    def _single_valued(cls, changes: dict[str, Any]) -> dict[str, Any]:
        unknown = sorted(set(changes) - set(_INHERITED_KEYS))
        if unknown:
            raise ValueError(f"off_changes: unknown keys {unknown}; use {list(_INHERITED_KEYS)}")
        _expand("dataobject_tables", changes.get("dataobject_tables") or [])
        for key in ("assumptions", "dataobject_tables", "resolve_settings", "module_settings"):
            for item in changes.get(key) or []:
                if "values" in item and len(item["values"]) != 1:
                    raise ValueError(
                        f"off_changes: {key} entries take one value, got {item['values']}"
                    )
        return changes


class Bookings(BaseModel):
    """Booking groups (GAP groups whose rates the model limits to booked capacity)."""

    groups: list[str] = Field(default_factory=list)
    gap_system: str = Field(default="PROD", description="GAP system label in OpenServer tags.")
    track_applied: bool = Field(
        default=True,
        description="Record the group limits the model applies at every step, so the "
        "analysis compares production with what was enforced, not only the tables.",
    )
    lift_gas_property: str | None = Field(
        default=None,
        description="GAP group property with the lift-gas injection rate (1000 Sm3/d), "
        "e.g. 'SolverResults[0].<name>'. Gas bookings limit total gas, so without it gas "
        "is compared as formation gas only. Tracked for every booking group.",
    )


class Analysis(BaseModel):
    user_licenses: list[str] = Field(
        default_factory=list, description="Licence(s) of the new reservoir: the paying side."
    )


class Limits(BaseModel):
    max_runs_per_submit: int = Field(default=40, ge=1, le=HARD_MAX_ACTIVE_RUNS)
    max_active_runs: int = Field(
        default=40,
        ge=1,
        le=HARD_MAX_ACTIVE_RUNS,
        description="Your unfinished runs in Autogration (all projects) plus the new ones.",
    )


class Case(BaseModel):
    name: str = Field(pattern=r"^[A-Za-z0-9_.-]+$")
    description: str = ""
    baseline: bool = False
    imported: bool = Field(
        default=False,
        description="Runs made elsewhere and attached with `tiein project add-run`; "
        "never submitted from here.",
    )
    switch: Literal["on", "off"] | None = Field(
        default=None, description="New reservoir on or off; inherited from `based_on`."
    )
    based_on: str | None = Field(default=None, description="Case whose changes this one adds to.")
    changes: dict[str, Any] = Field(default_factory=dict)
    case_labels: dict[int, str] = Field(
        default_factory=dict, description="Names of a sweep's runs, by Autogration case number."
    )

    @field_validator("switch", mode="before")
    @classmethod
    def _yaml_booleans(cls, value: Any) -> Any:
        # YAML 1.1 reads unquoted on/off as booleans.
        if isinstance(value, bool):
            return "on" if value else "off"
        return value

    @field_validator("changes")
    @classmethod
    def _known_keys(cls, changes: dict[str, Any]) -> dict[str, Any]:
        unknown = sorted(set(changes) - set(CHANGE_KEYS))
        if unknown:
            raise ValueError(f"unknown change keys {unknown}; use {list(CHANGE_KEYS)}")
        _expand("dataobject_tables", changes.get("dataobject_tables") or [])
        return changes


class Project(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    type: ProjectType
    environment: str | None = Field(
        default=None,
        description="Named environment (AUTOGRATION_<NAME>_API_URL in .env) the model and "
        "runs live on; None: the default environment.",
    )
    asset: str = Field(min_length=1)
    model_id: str = Field(min_length=1)
    description: str = ""
    vm_size: str | None = None
    switch: Switch | None = None
    bookings: Bookings = Field(default_factory=Bookings)
    analysis: Analysis = Field(default_factory=Analysis)
    limits: Limits = Field(default_factory=Limits)
    tracked_variables: list[str] = Field(default_factory=list)
    cases: list[Case] = Field(min_length=1)

    @model_validator(mode="after")
    def _check(self) -> Project:
        names = [c.name for c in self.cases]
        dupes = sorted({n for n in names if names.count(n) > 1})
        if dupes:
            raise ValueError(f"case names must be unique: {dupes}")
        baselines = [c.name for c in self.cases if c.baseline]
        if len(baselines) != 1:
            raise ValueError(f"a project needs exactly one baseline case, found {baselines}")
        if self.type is ProjectType.CASE_COMPARISON and self.switch is None:
            raise ValueError("a case comparison needs a `switch` (the new reservoir's wells)")
        by_name = {c.name: c for c in self.cases}
        for case in self.cases:
            if case.based_on is not None and case.based_on not in by_name:
                raise ValueError(f"case {case.name}: based_on {case.based_on!r} is not a case")
            self._chain(case, by_name)
            if self.switch is None:
                if case.switch is not None:
                    raise ValueError(f"case {case.name}: `switch` needs a project switch")
            elif case.switch is None and case.based_on is None:
                raise ValueError(f"case {case.name}: say `switch: on` or `switch: off`")
            if case.imported and case.changes:
                raise ValueError(f"case {case.name}: an imported case has no `changes`")
        if self.switch is not None and self.switch_state(self.baseline_case) != "off":
            raise ValueError(
                f"the baseline ({self.baseline_case.name}) must have {self.switch.label} "
                "switched off"
            )
        return self

    def _chain(self, case: Case, by_name: Mapping[str, Case]) -> list[Case]:
        chain, seen = [case], {case.name}
        while chain[-1].based_on is not None:
            parent = by_name[chain[-1].based_on]
            if parent.name in seen:
                raise ValueError(f"case {case.name}: based_on loops through {parent.name}")
            seen.add(parent.name)
            chain.append(parent)
        return chain[::-1]

    # ------------------------------------------------------------------ access
    @classmethod
    def load(cls, path: Path) -> Project:
        if not path.exists():
            raise ProjectError(f"no project file {path}")
        try:
            return cls.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
        except ValueError as e:
            raise ProjectError(f"{path}: {e}") from e

    @property
    def baseline_case(self) -> Case:
        return next(c for c in self.cases if c.baseline)

    def case(self, name: str) -> Case:
        for case in self.cases:
            if case.name == name:
                return case
        raise ProjectError(f"no case {name!r}; cases: {', '.join(c.name for c in self.cases)}")

    def lineage(self, case: Case) -> list[Case]:
        """The case and the cases it builds on, root first."""
        return self._chain(case, {c.name: c for c in self.cases})

    def switch_state(self, case: Case) -> str | None:
        """ "on" or "off" for a case comparison; None when the project has no switch."""
        if self.switch is None:
            return None
        for c in reversed(self.lineage(case)):
            if c.switch is not None:
                return c.switch
        raise AssertionError("validated: every root case sets switch")

    # ---------------------------------------------------------------- requests
    def switch_off_assumptions(self) -> list[dict[str, Any]]:
        if self.switch is None:
            return []
        serial = str(petex_serial(self.switch.off_from))
        return [
            {
                "operation": "schedule",
                "path": well.path,
                "name": well.name,
                "schedule": {
                    "date": serial,
                    "event_type": "WELL_OFF",
                    "index": _SWITCH_EVENT_INDEX + i,
                    "comments": f"{self.name}: {self.switch.label} off",
                },
            }
            for i, well in enumerate(self.switch.wells)
        ]

    def booking_tracked_variables(self) -> list[str]:
        system = self.bookings.gap_system
        out = []
        if self.bookings.track_applied:
            out += [
                f"resolve.module[0].MOD[{{{system}}}].GROUP[{{{group}}}].{constraint}"
                for group in self.bookings.groups
                for constraint in BOOKING_CONSTRAINTS
            ]
        if self.bookings.lift_gas_property:
            out += [
                f"resolve.module[0].MOD[{{{system}}}].GROUP[{{{group}}}]."
                f"{self.bookings.lift_gas_property}"
                for group in self.bookings.groups
            ]
        return out

    def changes_for(self, case: Case) -> dict[str, Any]:
        """The case's changes on top of the cases it builds on; later ones replace
        earlier ones that change the same thing. Cell row ranges are expanded."""
        merged: dict[str, list[dict[str, Any]]] = {k: [] for k in _INHERITED_KEYS}
        for c in self.lineage(case):
            for key in _INHERITED_KEYS:
                merged[key] = _merge(key, merged[key], _expand(key, c.changes.get(key) or []))
        out: dict[str, Any] = {k: v for k, v in merged.items() if v}
        for key in ("exclude", "include_base_case"):
            if key in case.changes:
                out[key] = case.changes[key]
        return out

    def run_name(self, case: Case, revision: int = 1) -> str:
        return f"{self.name} | {case.name}" + ("" if revision == 1 else f" r{revision}")

    def simulate_request(self, case: Case, revision: int = 1) -> dict[str, Any]:
        if case.imported:
            raise ProjectError(f"case {case.name} is imported: its runs were made elsewhere")
        changes = self.changes_for(case)
        switched_off = self.switch is not None and self.switch_state(case) == "off"
        if switched_off:
            for key, items in self.switch.off_changes.items():
                changes[key] = _merge(key, changes.get(key) or [], _expand(key, items))
        assumptions = [_iso_schedule_dates(a) for a in changes.pop("assumptions", [])]
        if switched_off and self.switch.off_events:
            assumptions = _merge("assumptions", assumptions, self.switch_off_assumptions())
        body: dict[str, Any] = {
            "user_specified_name": self.run_name(case, revision),
            "asset": self.asset,
            "assumptions": assumptions,
            **changes,
        }
        if self.vm_size:
            body["vm_size"] = self.vm_size
        tracked = [resolve_tracked_variable(v) for v in self.tracked_variables]
        tracked += self.booking_tracked_variables()
        if tracked:
            body["tracked_variables"] = list(dict.fromkeys(tracked))
        return body


def _iso_schedule_dates(assumption: dict[str, Any]) -> dict[str, Any]:
    schedule = assumption.get("schedule")
    if assumption.get("operation") != "schedule" or not isinstance(schedule, dict):
        return assumption
    date = str(schedule.get("date", ""))
    if not _ISO_DATE.match(date):
        return assumption
    return {**assumption, "schedule": {**schedule, "date": str(petex_serial(date))}}


_ROW_RANGE = re.compile(r"^\s*(\d+)\s*(?:-\s*(\d+))?\s*$")


def _rows(spec: Any) -> list[int]:
    """Row numbers from ``3``, ``[0, 2]`` or ``"0-23"`` / ``"0-23,30"``."""
    if isinstance(spec, bool):
        raise ProjectError(f"rows {spec!r}: give a number, a list or a range like 0-23")
    if isinstance(spec, int):
        return [spec]
    if isinstance(spec, list):
        return [int(x) for x in spec]
    if isinstance(spec, str):
        out: list[int] = []
        for part in spec.split(","):
            m = _ROW_RANGE.match(part)
            if not m or int(m.group(2) or m.group(1)) < int(m.group(1)):
                raise ProjectError(f"rows {spec!r}: give ranges like 0-23 or 0-23,30")
            out.extend(range(int(m.group(1)), int(m.group(2) or m.group(1)) + 1))
        return out
    raise ProjectError(f"rows {spec!r}: give a number, a list or a range like 0-23")


def _expand(kind: str, items: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """DataObject cells given as ``{..., rows: "0-23", value: 99999}`` become one cell
    per row. A row range takes one value: Autogration sweeps each cell on its own, so
    several values over several rows would multiply the cases."""
    if kind != "dataobject_tables":
        return list(items)
    out: list[dict[str, Any]] = []
    for item in items:
        if "rows" not in item:
            out.append(item)
            continue
        values = [item["value"]] if "value" in item else list(item.get("values") or [])
        if len(values) != 1:
            raise ProjectError(
                f"{item.get('object_alias')}.{item.get('table_name')} rows {item['rows']!r}: "
                "a row range takes exactly one `value`"
            )
        rest = {k: v for k, v in item.items() if k not in ("rows", "value", "values")}
        out.extend({**rest, "index": i, "values": values} for i in _rows(item["rows"]))
    return out


def expand_cells(items: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """DataObject cells with row ranges expanded (see ``_expand``)."""
    return _expand("dataobject_tables", items)


def _key(kind: str, item: Mapping[str, Any]) -> tuple[Any, ...]:
    if kind == "assumptions":
        op = item.get("operation", "replace")
        if op == "schedule":
            return (op, item.get("path"), (item.get("schedule") or {}).get("index"))
        if op == "add":
            return (op, item.get("path"), item.get("unique_id"))
        return (op, item.get("path"), item.get("property_name"))
    if kind == "dataobject_tables":
        return (item.get("object_alias"), item.get("table_name"), item.get("index"))
    if kind in ("resolve_settings", "module_settings"):
        return (item.get("tag"),)
    return (json.dumps(item, sort_keys=True, default=str),)


def _merge(
    kind: str, earlier: list[dict[str, Any]], later: Iterable[dict[str, Any]]
) -> list[dict[str, Any]]:
    out = {_key(kind, item): item for item in earlier}
    for item in later:
        out[_key(kind, item)] = item
    return list(out.values())


# -------------------------------------------------------------------- run budget
def estimate_runs(body: Mapping[str, Any]) -> int:
    """Runs (petex_compute tasks) Autogration will start for a simulate request: every
    combination of the `replace` values and the setting sweeps."""
    n = 1
    for a in body.get("assumptions") or []:
        if a.get("operation", "replace") == "replace":
            n *= max(1, len(a.get("values") or []))
    for key in ("resolve_settings", "module_settings", "dataobject_tables"):
        for sweep in body.get(key) or []:
            n *= max(1, len(sweep.get("values") or []))
    n -= len(body.get("exclude") or [])
    if body.get("include_base_case"):
        n += 1
    return max(n, 1)


def check_run_budget(new_runs: int, active_runs: int, limits: Limits) -> str | None:
    """Why the runs may not start, or None."""
    per_submit = min(limits.max_runs_per_submit, HARD_MAX_ACTIVE_RUNS)
    active_cap = min(limits.max_active_runs, HARD_MAX_ACTIVE_RUNS)
    if new_runs > per_submit:
        return f"{new_runs} runs in one submission; the limit is {per_submit}"
    if active_runs + new_runs > active_cap:
        return (
            f"{active_runs} of your runs are unfinished; {new_runs} more would exceed "
            f"{active_cap}. Wait, or cancel some"
        )
    return None


# ----------------------------------------------------------------------- run log
def request_digest(body: Mapping[str, Any]) -> str:
    return hashlib.sha256(json.dumps(body, sort_keys=True, default=str).encode()).hexdigest()[:16]


class RunLog:
    """``runs.json``: per case, the submitted request and the tasks it produced, with
    earlier revisions in ``history``."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.data: dict[str, Any] = (
            json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"cases": {}}
        )

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, indent=2, sort_keys=True), encoding="utf-8")
        tmp.replace(self.path)

    @property
    def cases(self) -> dict[str, dict[str, Any]]:
        return self.data.setdefault("cases", {})

    def next_revision(self, case: str) -> int:
        entry = self.cases.get(case)
        if entry is None:
            return 1
        return (
            max(
                [
                    entry.get("revision", 1),
                    *(h.get("revision", 1) for h in entry.get("history", [])),
                ]
            )
            + 1
        )

    def record_submission(
        self,
        case: str,
        model_id: str,
        body: Mapping[str, Any],
        started: Mapping[str, Any],
        revision: int,
    ) -> None:
        previous = self.cases.get(case)
        history = (
            [*previous.get("history", []), {k: v for k, v in previous.items() if k != "history"}]
            if previous
            else []
        )
        self.cases[case] = {
            "assumption_group_id": started["assumption_group_id"],
            "case_count": started["case_count"],
            "model_id": model_id,
            "user_specified_name": body["user_specified_name"],
            "request_digest": request_digest(body),
            "request": dict(body),
            "revision": revision,
            "submitted_at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
            "tasks": {},
            "history": history,
        }

    def record_tasks(self, case: str, tasks: Iterable[Mapping[str, Any]]) -> None:
        entry = self.cases[case]
        for task in tasks:
            n = task.get("assumption_case")
            key = str(n if n is not None else task["task_id"])
            entry["tasks"][key] = {"task_id": task["task_id"], "status": task["status"]}

    def record_import(
        self,
        case: str,
        tasks: Iterable[Mapping[str, Any]],
        *,
        source: str,
    ) -> None:
        """Attach runs made elsewhere to a case: ``source`` is the group or task id they
        were found by. Their own request is in Autogration (GET /tasks/{id}/assumption-set)."""
        tasks = list(tasks)
        if not tasks:
            raise ProjectError(f"no runs found for {source}")
        first = tasks[0]
        groups = {t.get("assumption_group_id") for t in tasks}
        self.cases[case] = {
            "imported": True,
            "source": source,
            "assumption_group_id": next(iter(groups)) if len(groups) == 1 else None,
            "case_count": len(tasks),
            "model_id": first.get("parent_task_id"),
            "user_specified_name": first.get("user_specified_name"),
            "created_by": (first.get("created_by") or {}).get("email"),
            "imported_at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
            "revision": 1,
            "tasks": {},
            "history": [],
        }
        for t in tasks:
            self.cases[case]["tasks"][t["task_id"]] = {
                "task_id": t["task_id"],
                "status": t["status"],
                "assumption_case": t.get("assumption_case"),
            }

    def rows(self, project: Project | None = None) -> list[dict[str, Any]]:
        """One row per run of the current revision of each case, baseline first. Without
        a project (the ad hoc log) every logged run is its own case."""
        cases = project.cases if project else []
        order = {c.name: i for i, c in enumerate(sorted(cases, key=lambda c: not c.baseline))}
        rows = []
        for case_name in sorted(self.cases, key=lambda n: (order.get(n, len(order)), n)):
            entry = self.cases[case_name]
            case = next((c for c in cases if c.name == case_name), None)
            labels = case.case_labels if case else {}
            single = len(entry["tasks"]) <= 1
            for key, task in sorted(entry["tasks"].items(), key=lambda kv: (len(kv[0]), kv[0])):
                n = int(key) if key.isdigit() else task.get("assumption_case")
                label = labels.get(n) if n is not None else None
                rows.append(
                    {
                        "case": case_name,
                        "run": n,
                        "case_name": label
                        or (case_name if single else f"{case_name}#{n if n is not None else key}"),
                        "is_baseline": bool(case and case.baseline),
                        "switch": project.switch_state(case) if project and case else None,
                        "based_on": case.based_on if case else None,
                        "revision": entry.get("revision", 1),
                        "imported": bool(entry.get("imported")),
                        "task_id": task["task_id"],
                        "status": task["status"],
                    }
                )
        return rows


# ------------------------------------------------------------------- workspace
class ProjectPaths:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.definition = root / "project.yaml"
        self.runs = root / "runs.json"
        self.results = root / "results"
        self.steps = root / "steps"
        self.bundles = root / "bundles"
        self.bookings = root / "bookings"
        self.workbench = root / "workbench"
        self.reference = root / "reference"


class Workspace:
    """``data/projects``: the projects, and which one commands use by default."""

    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir
        self.root = data_dir / "projects"
        self.current_file = self.root / ".current"

    def slugs(self) -> list[str]:
        if not self.root.exists():
            return []
        return sorted(p.name for p in self.root.iterdir() if (p / "project.yaml").exists())

    def paths(self, slug: str) -> ProjectPaths:
        if not re.match(_SLUG, slug):
            raise ProjectError(f"project slug {slug!r}: lowercase letters, digits and dashes")
        return ProjectPaths(self.root / slug)

    def current(self) -> str | None:
        if self.current_file.exists():
            slug = self.current_file.read_text(encoding="utf-8").strip()
            return slug or None
        return None

    def use(self, slug: str) -> None:
        if slug not in self.slugs():
            raise ProjectError(
                f"no project {slug!r}; projects: {', '.join(self.slugs()) or 'none'}"
            )
        self.root.mkdir(parents=True, exist_ok=True)
        self.current_file.write_text(slug, encoding="utf-8")

    def resolve(self, slug: str | None) -> str:
        """The project to work on: the one named, else the current one."""
        chosen = self.resolve_optional(slug)
        if not chosen:
            raise ProjectError(
                "no project selected: name one with --project, `tiein project use <slug>`, "
                "or create one with `tiein project new` (runs outside projects: `tiein run`)"
            )
        return chosen

    def resolve_optional(self, slug: str | None) -> str | None:
        """The named project, else the current one, else None (work outside projects)."""
        chosen = slug or self.current()
        if chosen and chosen not in self.slugs():
            raise ProjectError(
                f"no project {chosen!r}; projects: {', '.join(self.slugs()) or 'none'}"
            )
        return chosen or None

    def clear_current(self) -> None:
        self.current_file.unlink(missing_ok=True)

    @property
    def adhoc(self) -> ProjectPaths:
        """``data/adhoc``: the log, results and steps of runs outside any project."""
        return ProjectPaths(self.data_dir / "adhoc")

    def load(self, slug: str | None = None) -> tuple[Project, ProjectPaths, RunLog]:
        paths = self.paths(self.resolve(slug))
        return Project.load(paths.definition), paths, RunLog(paths.runs)

    def reference_dir(self, paths: ProjectPaths) -> Path:
        """The project's own reference data if it has any, else the shared folder."""
        return (
            paths.reference
            if (paths.reference / "entities.csv").exists()
            else self.data_dir / "reference"
        )
