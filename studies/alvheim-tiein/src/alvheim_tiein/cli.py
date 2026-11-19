"""``tiein`` command line: Autogration runs, optional projects, results and bookings.

``tiein run`` submits a one-off request (logged in ``data/adhoc``). A project
(``tiein project new``) is optional structure for runs that are compared: a type, one
baseline case and the cases against it, on a named environment. Project commands work
on the current project (``tiein project use``) or ``--project``; ``status``, ``fetch``
and ``steps`` work on one-off runs when no project is selected (or with ``--adhoc``).
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import string
import sys
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import pandas as pd
import yaml

from alvheim_tiein.client import FINAL, AutogrationClient, AutogrationError, step_results_frame
from alvheim_tiein.config import STUDY_ROOT, ConfigError, Settings
from alvheim_tiein.prepare import PrepareError
from alvheim_tiein.project import (
    HARD_MAX_ACTIVE_RUNS,
    Limits,
    Project,
    ProjectError,
    ProjectPaths,
    ProjectType,
    RunLog,
    Workspace,
    check_run_budget,
    estimate_runs,
    expand_cells,
    resolve_tracked_variable,
)

UNFINISHED = ("Preparing", "Enqueued", "Running")


class Paths:
    """Shared data (not per project): reference data, model caches, public data."""

    def __init__(self, settings: Settings) -> None:
        d = settings.data_dir
        self.data = d
        self.reference = d / "reference"
        self.models = d / "models"
        self.public = d / "public"
        self.workspace = Workspace(d)


def _print_table(rows: list[dict[str, Any]], columns: list[str]) -> None:
    if not rows:
        print("(none)")
        return
    print(pd.DataFrame(rows)[columns].to_string(index=False))


def _dump(obj: Any) -> None:
    print(json.dumps(obj, indent=2, default=str))


def cmd_init(args: argparse.Namespace, settings: Settings, paths: Paths) -> int:
    templates = STUDY_ROOT / "templates"
    paths.reference.mkdir(parents=True, exist_ok=True)
    paths.workspace.root.mkdir(parents=True, exist_ok=True)
    for src in sorted((templates / "reference").iterdir()):
        dst = paths.reference / src.name
        if not dst.exists():
            shutil.copyfile(src, dst)
            print(f"created {dst}")
    print(f"data folder: {paths.data} (git-ignored); next: `tiein project new`")
    return 0


def cmd_access(args: argparse.Namespace, settings: Settings, paths: Paths) -> int:
    print(f"API:  {settings.api_url}")
    print(f"auth: {settings.resolved_auth()}")
    with AutogrationClient.from_env(settings) as api:
        me = api.me()
        print(f"user: {me.get('name') or ''} <{me.get('email') or ''}>")
        role = me.get("role")
        if role is None:
            print("role: (this environment has no roles yet: every signed-in user may run)")
        else:
            print(f"role: {role}")
            if role == "reader":
                print(
                    "  readers can only look. Run `tiein request-access`, or ask a "
                    "contributor on the web app's Access page to make you one."
                )
        if not settings.is_local:
            access = api.api_access()
            print(f"token scope: {access.get('token_scope')}")
        assets = api.assets()
        print(f"assets ({len(assets)}): {', '.join(assets)}")
    return 0


def cmd_request_access(args: argparse.Namespace, settings: Settings, paths: Paths) -> int:
    with AutogrationClient.from_env(settings) as api:
        api.request_access()
    print("asked the admins to make you a contributor; they get a Teams message")
    return 0


def cmd_register(args: argparse.Namespace, settings: Settings, paths: Paths) -> int:
    with AutogrationClient.from_env(settings) as api:
        task = api.register_model(name=args.name, asset=args.asset, s_drive_path=args.s_drive)
        task_id = task["task_id"]
        print(f"registration task {task_id}: {task['status']}")
        if not args.wait:
            print(f"follow it with `tiein task {task_id}`; when Completed it is the model_id")
            return 0
        done = api.wait_for_task(
            task_id,
            poll_seconds=args.wait,
            on_progress=lambda t: print(f"{time.strftime('%H:%M:%S')} {t['status']}"),
        )
    _report_task(done)
    return 0 if done["status"] == "Completed" else 1


def _report_task(task: dict[str, Any]) -> None:
    print(f"task {task['task_id']} ({task.get('task_type')}): {task['status']}")
    if task.get("failure"):
        print(f"  failure [{task['failure'].get('category')}]: {task['failure'].get('message')}")
    for missing in task.get("missing_files") or []:
        print(f"  missing file: {missing.get('file_path') or missing.get('file_name')}")


def cmd_task(args: argparse.Namespace, settings: Settings, paths: Paths) -> int:
    with AutogrationClient.from_env(settings) as api:
        task = api.task(
            args.task_id, include=("logs",) if args.logs else (), log_tail=args.logs or 100
        )
    _report_task(task)
    for entry in task.get("logs") or []:
        level = entry.get("log_level") or entry.get("level") or ""
        print(f"  {entry.get('timestamp', '')} {level} {entry.get('message', '')}")
    return 0


def cmd_models(args: argparse.Namespace, settings: Settings, paths: Paths) -> int:
    with AutogrationClient.from_env(settings) as api:
        models = api.registered_models(asset=args.asset, search=args.search)
    _print_table(models, ["task_id", "user_specified_name", "asset", "created_at"])
    return 0


def cmd_browse(args: argparse.Namespace, settings: Settings, paths: Paths) -> int:
    with AutogrationClient.from_env(settings) as api:
        _dump(api.browse(args.model_id, args.path, search=args.search, limit=args.limit))
    return 0


def cmd_settings(args: argparse.Namespace, settings: Settings, paths: Paths) -> int:
    with AutogrationClient.from_env(settings) as api:
        data = {
            "resolve-settings": api.resolve_settings(args.model_id),
            "module-settings": api.module_settings(args.model_id),
            "dataobject-tables": api.dataobject_tables(args.model_id),
        }
    out = paths.models / args.model_id
    out.mkdir(parents=True, exist_ok=True)
    for kind, payload in data.items():
        target = out / f"{kind}.json"
        target.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"wrote {target}")
    return 0


LEVER_PROPERTIES = (
    "AlqControl",
    "MINGINJ",
    "MAXGINJ",
    "DPControl",
    "DPControlValue",
    "weighting",
    "IsMasked",
)


def _forecast_start(api: AutogrationClient, model_id: str) -> str:
    for s in api.resolve_settings(model_id):
        if s.get("key") == "START_DATE" and s.get("value"):
            return str(s["value"])[:10]
    raise ProjectError("the model has no START_DATE setting; pass --off-from")


def _yaml_text(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


# ------------------------------------------------------------------ scopes
@dataclass
class Scope:
    """What a command works on: one project, or the runs outside projects."""

    slug: str | None
    project: Project | None
    paths: ProjectPaths
    settings: Settings

    @property
    def label(self) -> str:
        return self.slug or "runs outside projects"

    def log(self) -> RunLog:
        return RunLog(self.paths.runs)

    def rows(self) -> list[dict[str, Any]]:
        return self.log().rows(self.project)


def _scope(
    args: argparse.Namespace, settings: Settings, paths: Paths, *, required: bool = False
) -> Scope:
    ws = paths.workspace
    if getattr(args, "adhoc", False):
        if required:
            raise ProjectError("this command needs a project")
        return Scope(None, None, ws.adhoc, settings)
    slug = ws.resolve(args.project) if required else ws.resolve_optional(args.project)
    if slug is None:
        return Scope(None, None, ws.adhoc, settings)
    project, ppaths, _ = ws.load(slug)
    return Scope(slug, project, ppaths, settings.for_environment(project.environment))


def _results_link(settings: Settings, rows: list[dict[str, Any]]) -> str | None:
    """A Results page link comparing the completed runs, baseline first."""
    done = [r for r in rows if r["status"] == "Completed"]
    done.sort(key=lambda r: not r["is_baseline"])
    if not done:
        return None
    if len(done) == 1:
        return f"{settings.web_url}/results/run.{done[0]['task_id']}"
    return f"{settings.web_url}/results/compare~" + "~".join(f"t.{r['task_id']}" for r in done)


# ---------------------------------------------------------------- projects
def _cases_block(project_type: ProjectType, switch_text: str, imported_baseline: bool) -> str:
    imported = "\n    imported: true" if imported_baseline else ""
    if project_type is ProjectType.SCENARIO_COMPARISON:
        what = "Imported run" if imported_baseline else "The model as registered"
        return f'  - name: baseline\n    baseline: true{imported}\n    description: "{what}."\n'
    baseline = (
        f'  - name: baseline\n    baseline: true{imported}\n    switch: "off"\n'
        f'    description: "{switch_text} shut from the start."\n'
    )
    tie_in = (
        f'\n  - name: tie_in\n    based_on: baseline\n    switch: "on"\n'
        f'    description: "{switch_text} on, as the model schedules it."\n'
    )
    return baseline + ("" if imported_baseline else tie_in)


def _switch_block(found: list[Any], label: str, off_from: str) -> str:
    wells = "\n".join(f"    - {{name: {e.name}, path: {_yaml_text(e.path)}}}" for e in found)
    return (
        "\n# The new reservoir. Switched-off cases shut these wells with WELL_OFF events from\n"
        "# `off_from` (the forecast start); switched-on cases leave the model's own schedule.\n"
        "# If the model opens the wells itself (a RESOLVE workflow), that undoes WELL_OFF:\n"
        "# add `off_changes` the model can't undo, and check the first baseline's well rates.\n"
        f"switch:\n  label: {_yaml_text(label)}\n  off_from: {off_from}\n  wells:\n{wells}\n"
        "  off_changes: {}\n"
    )


def _insert_case(text: str, item: list[str]) -> str:
    """``text`` (a project.yaml) with a new list item at the end of ``cases:``, indented
    like the items there, keeping every comment."""
    lines = text.splitlines()
    start = next((i for i, line in enumerate(lines) if re.match(r"^cases:\s*(#.*)?$", line)), None)
    if start is None:
        raise ProjectError("project.yaml has no `cases:` section")
    end = next(
        (i for i in range(start + 1, len(lines)) if re.match(r"^[^\s#-]", lines[i])), len(lines)
    )
    while end - 1 > start and not lines[end - 1].strip():
        end -= 1
    indent = next(
        (m.group(1) for line in lines[start + 1 : end] if (m := re.match(r"^(\s*)- ", line))), "  "
    )
    block = ["", *(indent + line for line in item)]
    return "\n".join([*lines[:end], *block, *lines[end:]]) + "\n"


def _import_tasks(api: AutogrationClient, ref: str) -> list[dict[str, Any]]:
    """The runs of a simulation (assumption group id) or a single run (task id)."""
    progress = api.group_progress(ref)
    if progress.tasks:
        return progress.tasks
    task = api.task(ref)
    if task.get("task_type") != "petex_compute":
        raise ProjectError(f"{ref} is a {task.get('task_type')} task, not a simulation run")
    return [task]


def cmd_project_new(args: argparse.Namespace, settings: Settings, paths: Paths) -> int:
    from alvheim_tiein import bookings, prepare

    ws = paths.workspace
    ppaths = ws.paths(args.slug)
    if ppaths.definition.exists():
        raise ProjectError(f"project {args.slug} exists: {ppaths.definition}")
    project_type = ProjectType(args.type)
    if project_type is ProjectType.CASE_COMPARISON and not (
        args.switch_label and args.switch_wells
    ):
        raise ProjectError("a case comparison needs --switch-label and --switch-wells")
    env_settings = settings.for_environment(args.env)
    environment = args.env or env_settings.environment
    wells = [w.strip() for w in (args.switch_wells or "").split(",") if w.strip()]
    with AutogrationClient.from_env(env_settings) as api:
        found = [prepare.find_equipment(api, args.model, w) for w in wells]
        tables = api.dataobject_tables(args.model)
        off_from = args.off_from or (_forecast_start(api, args.model) if wells else "")
        baseline_tasks = _import_tasks(api, args.import_baseline) if args.import_baseline else []
    model_dir = paths.models / args.model
    model_dir.mkdir(parents=True, exist_ok=True)
    (model_dir / "dataobject-tables.json").write_text(
        json.dumps(tables, indent=2), encoding="utf-8"
    )
    licences = [x.strip() for x in (args.user_licenses or "").split(",") if x.strip()]
    label = args.switch_label or ""
    template = string.Template(
        (STUDY_ROOT / "templates" / "project.yaml").read_text(encoding="utf-8")
    )
    text = template.substitute(
        NAME=_yaml_text(args.name),
        TYPE=project_type.value,
        ENVIRONMENT=environment or "null",
        ASSET=_yaml_text(args.asset),
        MODEL_ID=args.model,
        SWITCH_BLOCK=_switch_block(found, label, off_from) if found else "",
        BOOKING_GROUPS=json.dumps(bookings.booking_groups(tables), ensure_ascii=False),
        USER_LICENSES=json.dumps(licences),
        CASES_BLOCK=_cases_block(project_type, label.replace('"', "'"), bool(baseline_tasks)),
    )
    ppaths.root.mkdir(parents=True, exist_ok=True)
    ppaths.definition.write_text(text, encoding="utf-8")
    try:
        project = Project.load(ppaths.definition)
    except ProjectError:
        shutil.rmtree(ppaths.root)
        raise
    if baseline_tasks:
        log = RunLog(ppaths.runs)
        log.record_import("baseline", baseline_tasks, source=args.import_baseline)
        log.cases["baseline"]["environment"] = environment
        log.save()
    print(f"created {ppaths.definition}")
    switch = f" ({project.switch.label} off)" if project.switch else ""
    print(
        f"  {project.type.value} on {environment or 'the default environment'}: "
        f"baseline {project.baseline_case.name}{switch}"
    )
    print(f"  booking groups: {', '.join(project.bookings.groups) or '(none found)'}")
    if args.use or ws.current() is None:
        ws.use(args.slug)
        print(f"  current project: {args.slug}")
    return 0


def cmd_project_add_run(args: argparse.Namespace, settings: Settings, paths: Paths) -> int:
    """Attach runs made elsewhere (by anyone, same environment) to a project as an
    imported case, so they are compared with the rest."""
    scope = _scope(args, settings, paths, required=True)
    project, ppaths = scope.project, scope.paths
    assert project is not None
    if any(c.name == args.case for c in project.cases):
        raise ProjectError(
            f"case {args.case} exists in {ppaths.definition}; pick a new name for imported runs"
        )
    refs = args.ref
    with AutogrationClient.from_env(scope.settings) as api:
        tasks = [t for ref in refs for t in _import_tasks(api, ref)]
    models = {t.get("parent_task_id") for t in tasks}
    if models != {project.model_id} and not args.other_model:
        raise ProjectError(
            f"the runs belong to model(s) {sorted(m for m in models if m)}, not the project's "
            f"{project.model_id}; comparing across registrations needs --other-model"
        )
    lines = [f"- name: {args.case}", "  imported: true"]
    if project.switch is not None:
        lines.append(f'  switch: "{args.switch or "on"}"')
    names = sorted({t.get("user_specified_name") or "" for t in tasks})
    who = sorted({(t.get("created_by") or {}).get("email", "") for t in tasks})
    description = args.description or f"Imported: {', '.join(names)} ({', '.join(who)})"
    lines.append(f"  description: {_yaml_text(description)}")
    if args.label and len(tasks) == 1 and tasks[0].get("assumption_case") is not None:
        lines.append(f"  case_labels: {{{tasks[0]['assumption_case']}: {_yaml_text(args.label)}}}")
    original = ppaths.definition.read_text(encoding="utf-8")
    ppaths.definition.write_text(_insert_case(original, lines), encoding="utf-8")
    try:
        Project.load(ppaths.definition)
    except ProjectError as e:
        ppaths.definition.write_text(original, encoding="utf-8")
        raise ProjectError(f"could not add the case to {ppaths.definition}: {e}") from e
    log = scope.log()
    log.record_import(args.case, tasks, source=",".join(refs))
    log.cases[args.case]["environment"] = project.environment
    log.save()
    print(f"{scope.label}: added {args.case} with {len(tasks)} run(s) from {', '.join(refs)}")
    return 0


def cmd_project_list(args: argparse.Namespace, settings: Settings, paths: Paths) -> int:
    ws = paths.workspace
    current = ws.current()
    rows = []
    for slug in ws.slugs():
        row: dict[str, Any] = {"": "*" if slug == current else "", "project": slug}
        try:
            project, _, log = ws.load(slug)
        except ProjectError as e:
            rows.append({**row, "name": f"(invalid) {e}"})
            continue
        statuses = [r["status"] for r in log.rows(project)]
        rows.append(
            {
                **row,
                "name": project.name,
                "type": project.type.value,
                "environment": project.environment or "(default)",
                "asset": project.asset,
                "baseline": project.baseline_case.name,
                "cases": len(project.cases),
                "runs": len(statuses),
                "completed": statuses.count("Completed"),
            }
        )
    if not rows:
        print("no projects yet: `tiein project new <slug> ...` (projects are optional)")
        return 0
    print(pd.DataFrame(rows).fillna("").to_string(index=False))
    return 0


def _case_table(project: Project, log: RunLog) -> pd.DataFrame:
    rows = []
    for case in project.cases:
        entry = log.cases.get(case.name)
        statuses = pd.Series([t["status"] for t in (entry or {}).get("tasks", {}).values()])
        runs = len(statuses) if case.imported else estimate_runs(project.simulate_request(case))
        rows.append(
            {
                "case": case.name,
                "role": "baseline" if case.baseline else "",
                "source": "imported" if case.imported else "",
                "switch": project.switch_state(case) or "",
                "based_on": case.based_on or "",
                "runs": runs,
                "revision": entry.get("revision", 1) if entry and not case.imported else "",
                "status": ", ".join(f"{s} {n}" for s, n in statuses.value_counts().items())
                or "not submitted",
            }
        )
    return pd.DataFrame(rows)


def cmd_project_show(args: argparse.Namespace, settings: Settings, paths: Paths) -> int:
    scope = _scope(args, settings, paths, required=True)
    project, log = scope.project, scope.log()
    assert project is not None
    print(f"{project.name}  [{scope.slug}, {project.type.value}]")
    print(f"  environment {project.environment or '(default)'}: {scope.settings.api_url}")
    print(f"  asset {project.asset}, model {project.model_id}")
    if project.switch:
        wells = ", ".join(w.name for w in project.switch.wells)
        print(f"  switch: {project.switch.label} ({wells}), off from {project.switch.off_from}")
    print(f"  booking groups: {', '.join(project.bookings.groups) or '(none)'}")
    limits = project.limits
    print(
        f"  limits: {limits.max_runs_per_submit} runs per submit, {limits.max_active_runs} at once"
    )
    print(f"  folder: {scope.paths.root}\n")
    print(_case_table(project, log).to_string(index=False))
    link = _results_link(scope.settings, log.rows(project))
    if link:
        print(f"\ncompare in the web app (baseline first):\n  {link}")
    return 0


def cmd_project_use(args: argparse.Namespace, settings: Settings, paths: Paths) -> int:
    if args.none:
        paths.workspace.clear_current()
        print("no current project: commands without --project work on runs outside projects")
        return 0
    if not args.slug:
        raise ProjectError("name a project, or pass --none")
    paths.workspace.use(args.slug)
    print(f"current project: {args.slug}")
    return 0


def cmd_project_check(args: argparse.Namespace, settings: Settings, paths: Paths) -> int:
    from alvheim_tiein import bookings, prepare

    scope = _scope(args, settings, paths, required=True)
    project, log = scope.project, scope.log()
    assert project is not None
    problems: list[str] = []
    with AutogrationClient.from_env(scope.settings) as api:
        tables = api.dataobject_tables(project.model_id)
        for well in project.switch.wells if project.switch else []:
            name = api.browse(project.model_id, path=well.path, limit=1)["node"].get("name")
            if name != well.name:
                problems.append(f"switch well {well.name}: {well.path} is {name!r} in the model")
    (paths.models / project.model_id).mkdir(parents=True, exist_ok=True)
    (paths.models / project.model_id / "dataobject-tables.json").write_text(
        json.dumps(tables, indent=2), encoding="utf-8"
    )
    missing = sorted(set(project.bookings.groups) - set(bookings.booking_groups(tables)))
    if missing:
        problems.append(f"booking groups not in the model's booking tables: {missing}")
    values, cell_problems = prepare.check_cells(tables, prepare.dataobject_cells(project))
    problems += cell_problems
    shown = 0
    for (alias, table, index), value in values.items():
        if shown < 40:
            print(f"{alias}.{table}[{index}] is {value} in the model")
        shown += 1
    if shown > 40:
        print(f"... and {shown - 40} more cells")
    print(_case_table(project, log).to_string(index=False))
    for problem in problems:
        print(f"problem: {problem}", file=sys.stderr)
    if not problems:
        print("ok")
    return 1 if problems else 0


def cmd_project_levers(args: argparse.Namespace, settings: Settings, paths: Paths) -> int:
    from alvheim_tiein import prepare, report

    scope = _scope(args, settings, paths, required=True)
    project = scope.project
    assert project is not None
    ws = paths.workspace
    with AutogrationClient.from_env(scope.settings) as api:
        if args.wells:
            wells = [w.strip() for w in args.wells.split(",") if w.strip()]
            groups = {w: "" for w in wells}
        else:
            members = report.group_members(ws, project.model_id, project.bookings.groups, api)
            groups = {w: g for g, ws_ in members.items() for w in ws_}
            if project.switch:
                groups.update({w.name: project.switch.label for w in project.switch.wells})
        tables = report.dataobject_tables(ws, project.model_id, api)
        per_well = _well_table_rows(tables)
        rows = []
        for well, group in groups.items():
            eq = prepare.find_equipment(api, project.model_id, well)
            props = api.browse(project.model_id, path=eq.path, limit=1)["node"].get(
                "properties", {}
            )
            rows.append(
                {
                    "well": well,
                    "group": group,
                    **{k: (props.get(k) or {}).get("value") for k in LEVER_PROPERTIES},
                    **per_well.get(well, {}),
                }
            )
    print(
        "GAP well properties: AlqControl, MINGINJ/MAXGINJ (1000Sm3/d), DPControl, DPControlValue "
        "(bar). DataObject tables with a Well column follow as <table>.<column> with their row: "
        "a RESOLVE workflow that writes these to the wells every step (as Alvheim's does) "
        "overrides the GAP properties, so change the table cells (dataobject_tables) instead."
    )
    print(pd.DataFrame(rows).to_string(index=False))
    return 0


def _well_table_rows(tables: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Per well, the cells of every DataObject table keyed by a `Well` column."""
    by_alias: dict[str, dict[str, list[Any]]] = {}
    for t in tables.get("tables") or []:
        by_alias.setdefault(t["object_alias"], {})[t["table_name"]] = t.get("values") or []
    out: dict[str, dict[str, Any]] = {}
    for alias, cols in by_alias.items():
        wells = cols.get("Well")
        if not wells:
            continue
        for row, well in enumerate(wells):
            cells = out.setdefault(str(well), {})
            cells[f"{alias}.row"] = row
            for name, values in cols.items():
                if name != "Well" and row < len(values) and isinstance(values[row], int | float):
                    cells[f"{alias}.{name}"] = values[row]
    return out


# --------------------------------------------------------------- submitting
def _active_runs(api: AutogrationClient) -> int:
    """Your unfinished simulation runs in this Autogration environment, any project."""
    email = api.me().get("email")
    return sum(
        1 for _ in api.tasks(task_type="petex_compute", status=list(UNFINISHED), created_by=email)
    )


def _submit_planned(
    scope: Scope,
    model_id: str,
    plan: list[tuple[str, int, dict[str, Any], int]],
    limits: Limits,
    *,
    dry_run: bool,
) -> int:
    total = sum(p[3] for p in plan)
    listed = ", ".join(f"{n} ({r})" for n, _, _, r in plan)
    env = scope.settings.environment or scope.settings.api_url
    print(f"{scope.label} on {env}: {total} run(s): {listed}")
    if dry_run:
        for name, _, body, runs in plan:
            print(f"\nPOST /models/{model_id}/simulate   # {name}: {runs} run(s)")
            _dump(body)
        return 0
    with AutogrationClient.from_env(scope.settings) as api:
        problem = check_run_budget(total, _active_runs(api), limits)
        if problem:
            print(f"not submitted: {problem} (hard limit {HARD_MAX_ACTIVE_RUNS})", file=sys.stderr)
            return 2
        for name, revision, body, _ in plan:
            started = api.simulate(model_id, body)
            log = scope.log()
            log.record_submission(name, model_id, body, started, revision)
            log.cases[name]["environment"] = scope.settings.environment
            log.save()
            group = started["assumption_group_id"]
            print(f"submitted {name}: {started['case_count']} run(s), group {group}")
    return 0


def cmd_submit(args: argparse.Namespace, settings: Settings, paths: Paths) -> int:
    scope = _scope(args, settings, paths, required=True)
    project, log = scope.project, scope.log()
    assert project is not None
    submittable = [c for c in project.cases if not c.imported]
    if args.case == "all":
        names = [c.name for c in submittable if args.force or c.name not in log.cases]
        if not names:
            print("every case was already submitted; use --force to submit new revisions")
            return 0
    else:
        case = project.case(args.case)
        if case.imported:
            raise ProjectError(f"case {case.name} is imported: its runs were made elsewhere")
        if case.name in log.cases and not (args.force or args.dry_run):
            revision = log.cases[case.name].get("revision", 1)
            print(
                f"case {case.name} was already submitted (revision {revision}); "
                "use --force to submit a new revision",
                file=sys.stderr,
            )
            return 2
        names = [case.name]
    plan = []
    for name in names:
        case = project.case(name)
        revision = log.next_revision(name)
        body = project.simulate_request(case, revision)
        runs = estimate_runs(body)
        if case.baseline and runs != 1:
            raise ProjectError(f"the baseline must be one run; {name} would start {runs}")
        plan.append((name, revision, body, runs))
    return _submit_planned(scope, project.model_id, plan, project.limits, dry_run=args.dry_run)


def cmd_run(args: argparse.Namespace, settings: Settings, paths: Paths) -> int:
    """Submit a one-off request outside any project (logged in data/adhoc)."""
    request = yaml.safe_load(Path(args.request).read_text(encoding="utf-8")) or {}
    if not isinstance(request, dict):
        raise ProjectError(f"{args.request}: expected a mapping of simulate request keys")
    model_id = args.model or request.pop("model_id", None)
    if not model_id:
        raise ProjectError("give the model: --model or `model_id:` in the request file")
    env_settings = settings.for_environment(args.env or request.pop("environment", None))
    request.pop("environment", None)
    body: dict[str, Any] = {
        "user_specified_name": args.name,
        "asset": request.pop("asset", None) or args.asset,
        **request,
    }
    if not any(k in body for k in ("assumptions", "preset", "compute_set")):
        body["assumptions"] = []
    if body.get("dataobject_tables"):
        body["dataobject_tables"] = expand_cells(body["dataobject_tables"])
    if body.get("tracked_variables"):
        body["tracked_variables"] = [resolve_tracked_variable(v) for v in body["tracked_variables"]]
    scope = Scope(None, None, paths.workspace.adhoc, env_settings)
    log = scope.log()
    if args.name in log.cases and not args.dry_run:
        raise ProjectError(f"a run named {args.name!r} is already logged in {scope.paths.runs}")
    plan = [(args.name, 1, body, estimate_runs(body))]
    return _submit_planned(scope, model_id, plan, Limits(), dry_run=args.dry_run)


# --------------------------------------------------------------- following
def _summary(statuses: list[str]) -> str:
    counts = Counter(statuses)
    parts = [f"{s} {counts[s]}" for s in (*UNFINISHED, *FINAL) if s in counts]
    return f"{len(statuses)} task(s): " + (", ".join(parts) if parts else "none yet")


def _refresh(scope: Scope) -> bool:
    """Update the run log with task statuses and print them. The log is re-read just
    before saving, so a submission made meanwhile is kept. Runs outside projects can
    be on different environments: each is followed on its own."""
    log = scope.log()
    if not log.cases:
        return True
    by_env: dict[str | None, list[str]] = {}
    for name, entry in log.cases.items():
        env = scope.project.environment if scope.project else entry.get("environment")
        by_env.setdefault(env, []).append(name)
    updates: dict[str, tuple[str, list[dict[str, Any]]]] = {}
    for env, names in by_env.items():
        env_settings = scope.settings if scope.project else scope.settings.for_environment(env)
        with AutogrationClient.from_env(env_settings) as api:
            for name in names:
                entry = log.cases[name]
                if entry.get("imported"):
                    tasks = []
                    for t in entry["tasks"].values():
                        if t["status"] in FINAL:
                            tasks.append(t)
                        else:
                            d = api.task(t["task_id"])
                            tasks.append({"task_id": d["task_id"], "status": d["status"]})
                    updates[name] = ("imported", tasks)
                else:
                    updates[name] = (
                        "group",
                        api.group_progress(entry["assumption_group_id"]).tasks,
                    )
    fresh = scope.log()
    for name, (kind, tasks) in updates.items():
        entry = fresh.cases.get(name)
        if entry is None:
            continue
        if kind == "group":
            if entry.get("assumption_group_id") == log.cases[name]["assumption_group_id"]:
                fresh.record_tasks(name, tasks)
        else:
            for t in tasks:
                entry["tasks"][t["task_id"]]["status"] = t["status"]
    fresh.save()
    baseline = scope.project.baseline_case.name if scope.project else None
    finished = True
    for name, entry in fresh.cases.items():
        statuses = [t["status"] for t in entry["tasks"].values()]
        finished &= bool(statuses) and all(s in FINAL for s in statuses)
        tag = (
            " (baseline)" if name == baseline else (" (imported)" if entry.get("imported") else "")
        )
        print(f"  {name + tag:<34} {_summary(statuses)}")
    return finished


def cmd_status(args: argparse.Namespace, settings: Settings, paths: Paths) -> int:
    scope = _scope(args, settings, paths)
    if not scope.log().cases:
        print(f"{scope.label}: nothing submitted yet")
        return 0
    while True:
        print(f"{time.strftime('%H:%M:%S')} {scope.label}")
        done = _refresh(scope)
        if done or not args.watch:
            link = _results_link(scope.settings, scope.rows()) if scope.project else None
            if link and done:
                print(f"compare in the web app: {link}")
            return 0
        time.sleep(args.watch)


def cmd_fetch(args: argparse.Namespace, settings: Settings, paths: Paths) -> int:
    scope = _scope(args, settings, paths)
    _refresh(scope)
    log = scope.log()
    for row in scope.rows():
        if row["status"] != "Completed":
            continue
        env = (
            scope.project.environment
            if scope.project
            else log.cases[row["case"]].get("environment")
        )
        env_settings = scope.settings if scope.project else scope.settings.for_environment(env)
        task_id, ppaths = row["task_id"], scope.paths
        with AutogrationClient.from_env(env_settings) as api:
            if args.force or not (ppaths.results / f"{task_id}.parquet").exists():
                saved = api.download_results_parquet(task_id, ppaths.results)
                print(f"results  {row['case_name']}: {saved}")
            steps_csv = ppaths.steps / f"{task_id}.csv"
            if args.force or not steps_csv.exists():
                ppaths.steps.mkdir(parents=True, exist_ok=True)
                step_results_frame(api.step_results(task_id)).to_csv(steps_csv, index=False)
            if args.bundle and (args.force or not (ppaths.bundles / f"{task_id}.json").exists()):
                print(
                    f"bundle   {row['case_name']}: {api.download_bundle(task_id, ppaths.bundles)}"
                )
    return 0


def cmd_steps(args: argparse.Namespace, settings: Settings, paths: Paths) -> int:
    scope = _scope(args, settings, paths)
    log = scope.log()
    name = scope.project.case(args.case).name if scope.project else args.case
    if name not in log.cases:
        raise ProjectError(f"{name} has not been submitted in {scope.label}")
    entry = log.cases[name]
    runs = {
        str(t.get("assumption_case") if entry.get("imported") else key): t
        for key, t in entry["tasks"].items()
    }
    if str(args.run) not in runs:
        raise ProjectError(f"{name} has no run {args.run} (yet); runs: {sorted(runs)}")
    task_id = runs[str(args.run)]["task_id"]
    env_settings = (
        scope.settings
        if scope.project
        else scope.settings.for_environment(entry.get("environment"))
    )
    with AutogrationClient.from_env(env_settings) as api:
        frame = step_results_frame(api.step_results(task_id))
    scope.paths.steps.mkdir(parents=True, exist_ok=True)
    target = scope.paths.steps / f"{task_id}.csv"
    frame.to_csv(target, index=False)
    if frame.empty:
        print("no tracked variables recorded (yet)")
    else:
        latest = frame.sort_values("time").groupby("variable").tail(1)
        print(latest[["time", "variable", "value"]].to_string(index=False))
    print(f"wrote {target}")
    return 0


def cmd_bookings(args: argparse.Namespace, settings: Settings, paths: Paths) -> int:
    from alvheim_tiein import report

    scope = _scope(args, settings, paths, required=True)
    ws = paths.workspace
    data = report.load_project(ws, scope.slug)
    done = data.completed()
    if done.empty:
        print(f"{data.slug}: no completed runs yet (`tiein status`, then `tiein fetch`)")
        return 1
    missing = [t for t in done["task_id"] if not (data.paths.results / f"{t}.parquet").exists()]
    if missing:
        print(
            f"results not downloaded for {len(missing)} run(s): `tiein fetch` first",
            file=sys.stderr,
        )
        return 1
    if args.offline:
        rep = report.booking_report(ws, data)
    else:
        with AutogrationClient.from_env(scope.settings) as api:
            rep = report.booking_report(ws, data, api)
    written = report.write_booking_report(rep, data.paths.bookings)
    summary = rep.summary()
    for col in ("below_booking", "at_booking", "above_booking"):
        summary[col] = (100 * summary[col]).round(0).astype(int).astype(str) + " %"
    for col in ("booked_sm3d", "produced_sm3d", "delta_sm3d"):
        summary[col] = summary[col].round(0)
    print(
        f"{data.slug}: booked vs produced (Sm3/d, mean over periods); baseline {data.baseline_name}"
    )
    print(summary.to_string(index=False))
    if rep.sources is not None:
        print(
            "\nbooked rates from: "
            + ", ".join(f"{r.case_name} {r.source}" for r in rep.sources.itertuples())
        )
    violations = rep.violations()
    if not violations.empty:
        print(
            f"\nwarning: {len(violations)} step(s) where a group produced more than its applied "
            "limit (GAP did not honour it); those steps are suspect. First ones:"
        )
        cols = ["case_name", "group", "phase", "period", "booked_sm3d", "produced_sm3d"]
        shown = violations[cols].head(10).round({"booked_sm3d": 0, "produced_sm3d": 0})
        print(shown.to_string(index=False))
    if (summary["basis"] == "formation only").any():
        print(
            "\nnote: gas bookings limit total gas (lift gas included); gas rows compare "
            "formation gas only. Set bookings.lift_gas_property to compare them fully."
        )
    print(f"\nwrote {', '.join(str(p.name) for p in written.values())} to {data.paths.bookings}")
    return 0


def cmd_export_workbench(args: argparse.Namespace, settings: Settings, paths: Paths) -> int:
    from alvheim_tiein import report
    from alvheim_tiein.results import export_workbench_folder

    scope = _scope(args, settings, paths, required=True)
    ws = paths.workspace
    data = report.load_project(ws, scope.slug)
    out = export_workbench_folder(
        data.runs.to_dict("records"),
        data.paths.results,
        data.paths.workbench,
        baseline=data.baseline_name,
        entities_csv=ws.reference_dir(data.paths) / "entities.csv",
    )
    print(
        f"workbench folder: {out}\nopen it with the 'Study: results viewer' task and paste the path"
    )
    return 0


def cmd_sodir(args: argparse.Namespace, settings: Settings, paths: Paths) -> int:
    from alvheim_tiein import sodir

    paths.public.mkdir(parents=True, exist_ok=True)
    tables = {}
    for name in sodir.TABLES:
        text = sodir.fetch_text(name)
        (paths.public / f"{name}.csv").write_text(text, encoding="utf-8")
        tables[name] = sodir.parse_table(text)
        print(f"wrote {paths.public / name}.csv ({len(tables[name])} rows)")
    current = sodir.current_field_licensees(tables["field_licensee_hst"])
    current.to_csv(paths.public / "alvheim_area_current_licensees.csv", index=False)
    area = tables["field_licensee_hst"]
    area = area[area["fldName"].isin(sodir.ALVHEIM_AREA_FIELDS)]
    sodir.to_licence_shares(area).to_csv(
        paths.public / "alvheim_area_licence_shares.csv", index=False
    )
    print(current.to_string(index=False))
    return 0


def cmd_demo(args: argparse.Namespace, settings: Settings, paths: Paths) -> int:
    from alvheim_tiein.demo import build_demo_data

    target = build_demo_data(paths.data / "demo")
    print(f"demo study folder (synthetic results, fictional economics): {target}")
    return 0


# ------------------------------------------------------------------ optimise
def _study_scope(
    args: argparse.Namespace, settings: Settings, paths: Paths, name: str | None = None
) -> tuple[Scope, Any]:
    from alvheim_tiein.optimise import runner as rn

    name = name or args.name
    scope = _scope(args, settings, paths, required=True)
    sp = rn.StudyPaths(scope.paths, name)
    if not sp.spec.exists():
        names = rn.study_names(scope.paths)
        raise ProjectError(
            f"no study {name!r} in {scope.label}; studies: {', '.join(names) or 'none'} "
            "(`tiein optimise new`)"
        )
    return scope, sp


def _open_study(scope: Scope, paths: Paths, name: str, api: AutogrationClient | None) -> Any:
    from alvheim_tiein.optimise import runner as rn

    assert scope.slug is not None
    ctx = rn.StudyContext.load(paths.workspace, scope.slug, name, api)
    return rn.Study.open(ctx)


def _confirm_runs(spec: Any) -> int:
    if "confirm" not in spec.stage_list:
        return 0
    cases = 1 + len(spec.reference_cases) if spec.budget.confirm_base else 0
    return spec.budget.confirm + cases


def cmd_optimise_new(args: argparse.Namespace, settings: Settings, paths: Paths) -> int:
    from alvheim_tiein.optimise import runner as rn
    from alvheim_tiein.optimise import templates

    scope = _scope(args, settings, paths, required=True)
    assert scope.project is not None
    refs = None
    if args.reference is not None:
        refs = [r.strip() for r in args.reference.split(",") if r.strip()]
    data = templates.template(
        args.scheme, args.name, scope.project, base_case=args.base, reference_cases=refs
    )
    if args.description:
        data["description"] = args.description
    sp = rn.StudyPaths(scope.paths, args.name)
    state = rn.load_state(sp.state)
    if state is not None and state.started_at is not None:
        raise ProjectError(f"study {args.name} has started; pick another name")
    if sp.spec.exists() and not args.force:
        raise ProjectError(f"study {args.name} exists ({sp.spec}); --force replaces it")
    sp.root.mkdir(parents=True, exist_ok=True)
    text = templates.study_yaml(data, comments=templates.header(args.scheme, args.name))
    sp.spec.write_text(text, encoding="utf-8")
    spec = rn.load_spec(sp.spec)
    print(f"wrote {sp.spec}")
    against = ", ".join(spec.reference_cases) or "nothing"
    print(
        f"{spec.scheme}: runs start from {data['base_case']}, compared with {against}; "
        f"stages {' -> '.join(spec.stage_list)}"
    )
    print(
        f"at least {spec.required_runs()} run(s) on the {spec.fidelity.search} grid "
        f"(budget {spec.budget.max_evaluations}), then up to {_confirm_runs(spec)} "
        f"{spec.fidelity.confirm} run(s) (fewer when completed runs of the cases are reused)"
    )
    if spec.scheme == "restructure_bookings":
        print(f"next: `tiein optimise plans {args.name} --s2 <case with the bookings lifted>`")
    else:
        print(f"next: edit it, then `tiein optimise check {args.name}`")
    return 0


def cmd_optimise_list(args: argparse.Namespace, settings: Settings, paths: Paths) -> int:
    from alvheim_tiein.optimise import runner as rn

    scope = _scope(args, settings, paths, required=True)
    rows = []
    for name in rn.study_names(scope.paths):
        sp = rn.StudyPaths(scope.paths, name)
        try:
            scheme = rn.load_spec(sp.spec).scheme
        except ProjectError:
            scheme = "(invalid study.yaml)"
        state = rn.load_state(sp.state)
        if state is None or state.started_at is None:
            stage, runs = "not started", 0
        else:
            stage = f"done: {state.stop_reason}" if state.finished else str(state.stage)
            runs = state.committed()
        rows.append({"study": name, "scheme": scheme, "stage": stage, "runs": runs})
    print(f"{scope.label}: optimisation studies")
    _print_table(rows, ["study", "scheme", "stage", "runs"])
    return 0


def _lever_scope(lever: Any) -> str:
    groups = ", ".join(lever.groups) if lever.groups else "all groups"
    if lever.kind == "weights":
        return ", ".join(lever.wells) if lever.wells else "all wells"
    if lever.kind == "release":
        phases = "/".join(lever.phases) if lever.phases else "booked phases"
        return f"{groups}; {phases}; window {lever.window}"
    if lever.kind == "liquid_scale":
        return f"{groups}; future liquid"
    return f"{lever.alias}.{lever.column}: {', '.join(lever.wells or [])}"


def _check_requests(study: Any) -> list[dict[str, Any]]:
    """Build the request of the base and reference cases, each lever at its bounds and
    each candidate: every cell lookup and booking plan is checked before a run."""
    from alvheim_tiein.optimise import study as st

    spec, state = study.spec, study.state
    stamp = st.now_utc().isoformat(timespec="seconds")
    search = spec.fidelity.search

    def ev(stage: str, case: str, fidelity: str = search, **kw: Any) -> Any:
        return st.Evaluation(
            id="check", stage=stage, fidelity=fidelity, case=case, proposed_at=stamp, **kw
        )

    base = state.base_case
    points = [("base", ev("base", base, base=True, theta=spec.baseline_theta()))]
    points += [(f"ref:{r}", ev("base", r, reference=r)) for r in spec.reference_cases]
    defaults = spec.lever_defaults()
    for lever in spec.levers:
        for value in dict.fromkeys((lever.lower, lever.upper)):
            theta = {**defaults, lever.name: value}
            points.append((f"{lever.name}={value:g}", ev("screening", base, theta=theta)))
    for c in spec.candidates:
        theta = {**defaults, **c.theta}
        points.append((c.name, ev("candidates", base, theta=theta, candidate=c.name)))
    if "confirm" in spec.stage_list and spec.fidelity.confirm != search:
        confirm = spec.fidelity.confirm
        points.append(
            ("base", ev("confirm", base, confirm, base=True, theta=spec.baseline_theta()))
        )
    rows = []
    for what, e in points:
        row = {"what": what, "grid": e.fidelity, "cells": 0, "settings": 0, "problem": ""}
        try:
            body = study.request(e)
            row["cells"] = len(body.get("dataobject_tables") or [])
            row["settings"] = len(body.get("resolve_settings") or [])
        except (KeyError, ValueError, ProjectError) as err:
            row["problem"] = str(err)
        rows.append(row)
    return rows


def cmd_optimise_check(args: argparse.Namespace, settings: Settings, paths: Paths) -> int:
    scope, sp = _study_scope(args, settings, paths)
    assert scope.project is not None
    if args.offline:
        study = _open_study(scope, paths, args.name, None)
    else:
        with AutogrationClient.from_env(scope.settings) as api:
            study = _open_study(scope, paths, args.name, api)
    spec, state, p = study.spec, study.state, scope.project
    print(f"study {spec.name} ({spec.scheme}) in {scope.slug}: {p.environment or 'default'}")
    print(f"  model {p.model_id}, VM {p.vm_size or 'default'}")
    print(
        f"  base case {state.base_case}; references {', '.join(spec.reference_cases) or 'none'}"
        f"; objective {spec.objective} in {study.ctx.ref.economics.value_unit}"
    )
    grids = {g: len(spec.fidelity.steps(g)) for g in (spec.fidelity.search, spec.fidelity.confirm)}
    print(f"  stages {' -> '.join(spec.stage_list)}")
    print("  grids " + ", ".join(f"{g} ({n} steps)" for g, n in grids.items()))
    print(
        f"  runs: at least {spec.required_runs()} on {spec.fidelity.search} (budget "
        f"{spec.budget.max_evaluations}, {spec.budget.wave_size} at once), up to "
        f"{_confirm_runs(spec)} on {spec.fidelity.confirm}"
    )
    if state.case_tasks:
        reused = ", ".join(f"{c} ({t})" for c, t in state.case_tasks.items())
        print(f"  completed monthly runs reused: {reused}")
    if spec.levers:
        print("\nlevers")
        _print_table(
            [
                {
                    "name": lever.name,
                    "kind": lever.kind,
                    "bounds": f"{lever.lower:g}..{lever.upper:g}",
                    "baseline": "" if lever.baseline is None else f"{lever.baseline:g}",
                    "levels": ", ".join(f"{v:g}" for v in lever.levels or []),
                    "applies to": _lever_scope(lever),
                }
                for lever in spec.levers
            ],
            ["name", "kind", "bounds", "baseline", "levels", "applies to"],
        )
    if spec.candidates:
        print("\ncandidates")
        rows = [
            {
                "name": c.name,
                "theta": ", ".join(f"{k}={v:g}" for k, v in c.theta.items()),
                "cells": len(c.cells),
                "booking_plan": c.booking_plan or "",
            }
            for c in spec.candidates
        ]
        _print_table(rows, ["name", "theta", "cells", "booking_plan"])
    checks = _check_requests(study)
    print("\nrequests (cells written, schedule settings)")
    _print_table(checks, ["what", "grid", "cells", "settings", "problem"])
    if state.started_at is None:
        print("\nnot started: `tiein optimise step NAME --dry-run` shows the first wave")
    else:
        print(f"\nstarted {state.started_at}; stage {state.stage}; runs used {state.committed()}")
    return 1 if any(r["problem"] for r in checks) else 0


def _print_status(state: Any) -> None:
    table = state.table()
    if table.empty:
        print("(no evaluations yet)")
        return
    cols = ["id", "stage", "fidelity", "what", "status", "task_status", "objective", "feasible"]
    shown = table[cols + ["reasons"]].copy()
    shown["objective"] = shown["objective"].map(lambda v: "" if pd.isna(v) else f"{v:,.0f}")
    shown["reasons"] = shown["reasons"].str.slice(0, 60)
    print(shown.fillna("").to_string(index=False))


def _print_outcome(state: Any) -> None:
    out = state.outcome()
    if not out:
        print("no feasible result yet")
        return
    gain = "" if out["gain"] is None else f", {out['gain']:+,.0f} against the base case"
    unit = f" {state.value_unit}" if state.value_unit else ""
    flag = " (check: most of the gain is outside the search grid's trusted window)"
    print(
        f"best on {out['fidelity']}: {out['id']} {out['label']}: {out['objective']:,.0f}"
        f"{unit}{gain}" + (flag if out["window_flag"] else "")
    )


def cmd_optimise_step(args: argparse.Namespace, settings: Settings, paths: Paths) -> int:
    from alvheim_tiein.optimise import runner as rn

    names = list(dict.fromkeys(args.name))
    scoped = {name: _study_scope(args, settings, paths, name) for name in names}
    scope = scoped[names[0]][0]
    with AutogrationClient.from_env(scope.settings) as api:
        studies = {name: _open_study(scope, paths, name, api) for name in names}
        backend = rn.ApiBackend(api)
        finished: set[str] = set()
        while True:
            for name, study in studies.items():
                if name in finished:
                    continue
                try:
                    if _step_study(name, study, backend, scoped[name][1], args.dry_run):
                        finished.add(name)
                except (httpx.TransportError, AutogrationError) as e:
                    if not (args.watch and _transient(e)):
                        raise
                    print(f"  {name}: {e}; trying again next round", file=sys.stderr)
            if args.dry_run or len(finished) == len(studies):
                return 0
            if not args.watch:
                print("step again later or --watch SECONDS")
                return 0
            time.sleep(args.watch)


def _transient(e: Exception) -> bool:
    """Errors a watch rides out: the network, the gateway, throttling, an expired token."""
    if isinstance(e, AutogrationError):
        return e.status >= 500 or e.status in (401, 408, 429)
    return True


def _step_study(name: str, study: Any, backend: Any, sp: Any, dry_run: bool) -> bool:
    """One tick of a study, printed; True when it has finished."""
    r = study.tick(backend, dry_run=dry_run)
    s = study.state
    print(
        f"{time.strftime('%H:%M:%S')} {name}: stage {s.stage or '-'}, "
        f"runs used {s.committed()} of {study.spec.budget.max_evaluations}"
    )
    for label, ids in (
        ("followed", r.followed),
        ("scored", r.scored),
        ("submitted", r.submitted),
        ("shared (another study's identical run, no new run)", r.shared),
    ):
        if ids:
            print(f"  {label}: {', '.join(ids)}")
    if r.blocked:
        print(f"  waiting: {r.blocked}")
    if dry_run:
        folder = sp.root / "dry-run"
        folder.mkdir(parents=True, exist_ok=True)
        rows = []
        for eid, body in r.requests:
            (folder / f"{eid}.json").write_text(
                json.dumps(body, indent=2, default=str), encoding="utf-8"
            )
            rows.append(
                {
                    "id": eid,
                    "what": s.get(eid).label,
                    "name": body.get("user_specified_name"),
                    "cells": len(body.get("dataobject_tables") or []),
                    "shares": r.shares.get(eid, ""),
                }
            )
        new = len(rows) - len(r.shares)
        print(
            f"dry run: {new} new run(s) would start, {len(r.shares)} shared with "
            f"another study; requests in {folder}"
        )
        _print_table(rows, ["id", "what", "name", "cells", "shares"])
        return True
    if r.finished:
        print(f"finished: {r.stop_reason}")
        _print_outcome(s)
        print(f"next: `tiein optimise report {name}`")
        return True
    print(f"  {len(s.in_flight())} run(s) of this study unfinished")
    return False


def cmd_optimise_status(args: argparse.Namespace, settings: Settings, paths: Paths) -> int:
    from alvheim_tiein.optimise import runner as rn

    scope, sp = _study_scope(args, settings, paths)
    state = rn.load_state(sp.state)
    if state is None:
        print(f"{args.name}: not started (`tiein optimise step {args.name}`)")
        return 0
    head = f"done: {state.stop_reason}" if state.finished else f"stage {state.stage}"
    print(
        f"{args.name} ({state.spec.scheme}) in {scope.slug}: {head}; runs used "
        f"{state.committed()} of {state.spec.budget.max_evaluations}"
    )
    _print_status(state)
    _print_outcome(state)
    return 0


def cmd_optimise_report(args: argparse.Namespace, settings: Settings, paths: Paths) -> int:
    from alvheim_tiein.optimise import runner as rn

    scope, sp = _study_scope(args, settings, paths)
    state = rn.load_state(sp.state)
    if state is None:
        raise ProjectError(f"{args.name} has not started")
    written = rn.write_report(state, sp.report)
    _print_outcome(state)
    if "settlement.csv" in written:
        settle = pd.read_csv(written["settlement.csv"])
        settle = settle[settle["rule"] == args.rule]
        notes = sorted(set(settle["note"].dropna()) - {""}) if "note" in settle else []
        values = [c for c in ("delta", "transfer") if c in settle and settle[c].notna().any()]
        if not settle.empty:
            print(f"\nsettlement ({args.rule}): change per licence and transfer (+ received)")
            pivot = settle.pivot_table(
                index="license", columns="against", values=values, aggfunc="first"
            )
            print(pivot.round(0).to_string())
            for note in notes:
                print(f"  note: {note}")
    print(f"\nwrote {', '.join(written)} to {sp.report}")
    return 0


def cmd_optimise_cancel(args: argparse.Namespace, settings: Settings, paths: Paths) -> int:
    from alvheim_tiein.optimise import runner as rn

    scope, _ = _study_scope(args, settings, paths)
    with AutogrationClient.from_env(scope.settings) as api:
        study = _open_study(scope, paths, args.name, api)
        cancelled = study.cancel(rn.ApiBackend(api))
    print(f"{args.name}: stopped; cancelled {len(cancelled)} run(s) {', '.join(cancelled)}")
    return 0


def _monthly_calendar(periods: list[pd.Timestamp]) -> pd.DataFrame:
    p = pd.DatetimeIndex(sorted(set(periods)))
    return pd.DataFrame({"period": p, "days": p.days_in_month})


def cmd_optimise_plans(args: argparse.Namespace, settings: Settings, paths: Paths) -> int:
    from alvheim_tiein import bookings as bk
    from alvheim_tiein import levers as lv
    from alvheim_tiein import report
    from alvheim_tiein import restructure as rs
    from alvheim_tiein.economics import Reference
    from alvheim_tiein.optimise import runner as rn
    from alvheim_tiein.optimise import templates

    scope, sp = _study_scope(args, settings, paths)
    project = scope.project
    assert project is not None and scope.slug is not None
    state = rn.load_state(sp.state)
    if state is not None and state.started_at is not None:
        raise ProjectError(f"{args.name} has started; write plans into a new study")
    raw = yaml.safe_load(sp.spec.read_text(encoding="utf-8")) or {}
    s1 = args.s1 or raw.get("base_case") or project.baseline_case.name
    ws = paths.workspace
    data = report.load_project(ws, scope.slug)
    done = set(data.completed()["case_name"])
    for case in (s1, args.s2):
        if project.case(case).name not in done:
            raise ProjectError(f"{case} has no completed run in {scope.slug} (`tiein status`)")
    if args.offline:
        rep = report.booking_report(ws, data)
        payload = report.dataobject_tables(ws, project.model_id)
    else:
        with AutogrationClient.from_env(scope.settings) as api:
            rep = report.booking_report(ws, data, api)
            payload = report.dataobject_tables(ws, project.model_id, api)
    tables = lv.ModelTables(payload)
    booking = rs.from_satisfaction(rep.satisfaction(), s1, args.s2)
    # Results end with a timestamp after the last step; plans cover the steps the
    # study's runs simulate (the calendar evaluation_cells maps them onto).
    steps = pd.DatetimeIndex(rn.load_spec(sp.spec).fidelity.steps("monthly"))
    booking = booking[pd.DatetimeIndex(booking["period"]).isin(steps)].reset_index(drop=True)
    if booking.empty:
        raise ProjectError(f"{s1} and {args.s2} share no period with the monthly grid")
    periods = sorted(booking["period"].unique())
    cells = bk.booking_cells(payload, periods, sorted(booking["group"].unique()))
    has_cell = cells.loc[cells["object_alias"].notna(), ["group", "period", "phase"]]
    booking = booking.merge(has_cell, on=["group", "period", "phase"]).reset_index(drop=True)
    windows = rs.booking_windows(payload, periods)
    plans = {
        "r1_lend": rs.r1_lend(booking, args.lam),
        "r4_pro_rata": rs.r4_resplit(booking, windows=windows),
    }
    reference = rs.plan_of(booking)
    sp.plans.mkdir(parents=True, exist_ok=True)
    booking.to_csv(sp.plans / "booking_state.csv", index=False)
    for name, plan in plans.items():
        problems = rs.check_plan(reference, plan)
        if problems:
            raise ProjectError(f"{name}: {'; '.join(problems)}")
        plan.to_csv(sp.plans / templates.PLAN_FILES[name], index=False)
    print(
        f"S1 {s1}, S2 {args.s2}: {booking['group'].nunique()} groups, {len(periods)} periods; "
        f"wrote booking_state.csv and {', '.join(templates.PLAN_FILES.values())} to {sp.plans}"
    )

    demand = rep.satisfaction()
    demand = demand[demand["case_name"] == args.s2]
    try:
        ref = Reference.load(ws.reference_dir(data.paths))
        worth = rs.unit_values(ref, _monthly_calendar(periods))
        ranking = rs.rank_candidates(
            plans,
            reference,
            demand,
            worth,
            limits=lv.fpso_limits(tables),
            priority=rs.group_priority(payload),
        )
        print("\nsurrogate ranking (only picks what to run; never a value estimate)")
        print(ranking.round(0).to_string(index=False))
    except (KeyError, ValueError) as e:
        print(f"\nno surrogate ranking: {e}")

    new: list[dict[str, Any]] = [
        {
            "name": name,
            "description": f"{name} from S1 {s1} and S2 {args.s2}"
            + (f" (lambda {args.lam:g})" if name == "r1_lend" else ""),
            "booking_plan": templates.PLAN_FILES[name],
        }
        for name in plans
    ]
    if project.switch is not None and not args.no_r3:
        fl = [w.name for w in project.switch.wells]
        wells = rep.wells[rep.wells["case_name"] == args.s2]
        for phi in args.phi:
            caps = rs.r3_fl_caps(wells, phi, wells=fl)
            new.append(
                {
                    "name": f"r3_phi{round(100 * phi)}",
                    "description": f"{project.switch.label} liquid cap at {phi:.0%} of its "
                    f"S2 ({args.s2}) peak: "
                    + ", ".join(f"{w} {v:,.0f} Sm3/d" for w, v in caps.items()),
                    "cells": [
                        lv.well_cell(tables, w, "MaxLiquidRate", round(v, 1))
                        for w, v in caps.items()
                    ],
                }
            )
    names = {c["name"] for c in new}
    raw["candidates"] = [c for c in raw.get("candidates") or [] if c.get("name") not in names] + new
    budget = raw.setdefault("budget", {})
    roomy = {**raw, "budget": {**budget, "max_evaluations": 500}}
    try:
        need = rn.st.StudySpec.model_validate(roomy).required_runs()
    except ValueError as e:
        raise ProjectError(f"study {args.name} with the new candidates: {e}") from e
    if budget.get("max_evaluations", 40) < need:
        budget["max_evaluations"] = need + 2
    lines = sp.spec.read_text(encoding="utf-8").splitlines(keepends=True)
    comments = "".join(line for line in lines if line.startswith("#"))
    sp.spec.write_text(templates.study_yaml(raw, comments=comments), encoding="utf-8")
    spec = rn.load_spec(sp.spec)
    print(f"\n{len(new)} candidate(s) in {sp.spec}: {', '.join(c['name'] for c in new)}")
    print(f"at least {spec.required_runs()} run(s); next: `tiein optimise check {args.name}`")
    return 0


# --------------------------------------------------------------- grids, export
def cmd_mhgrid(args: argparse.Namespace, settings: Settings, paths: Paths) -> int:
    from alvheim_tiein import levers as lv
    from alvheim_tiein import mhgrid, report
    from alvheim_tiein.optimise import study as st

    scope = _scope(args, settings, paths, required=True)
    project = scope.project
    assert project is not None
    ws = paths.workspace
    if args.offline:
        payload = report.dataobject_tables(ws, project.model_id)
    else:
        with AutogrationClient.from_env(scope.settings) as api:
            payload = report.dataobject_tables(ws, project.model_id, api)
    tables = lv.ModelTables(payload)
    steps = mhgrid.predict_steps(args.grid)
    overrides: list[dict[str, Any]] = []
    if args.case:
        case = project.case(args.case).model_copy(update={"imported": False})
        body = project.simulate_request(case)
        overrides = expand_cells(body.get("dataobject_tables") or [])
    cells = mhgrid.remap_cells(tables, steps, overrides=overrides)
    print(
        f"grid {args.grid}: {len(steps)} steps from {steps[0].date()} to "
        f"{mhgrid.FORECAST_END.date()} (monthly: {len(mhgrid.predict_steps('monthly'))})"
    )
    print("steps: " + ", ".join(str(s.date()) for s in steps))
    counts = Counter((str(c["object_alias"]), str(c["table_name"])) for c in cells)
    rows = [{"table": a, "column": c, "cells": n} for (a, c), n in sorted(counts.items())]
    print(f"\n{len(cells)} cell(s) put {args.case or 'the model'} on the grid")
    _print_table(rows, ["table", "column", "cells"])
    settings_ = st.request_resolve_settings(args.grid)
    if args.table:
        frame = mhgrid.remap_table(tables, steps, overrides=overrides)
        Path(args.table).parent.mkdir(parents=True, exist_ok=True)
        frame.to_csv(args.table, index=False)
        print(f"wrote {args.table}")
    if args.write:
        changes: dict[str, Any] = {"dataobject_tables": cells}
        if settings_:
            changes["resolve_settings"] = settings_
        if any("ScheduleList[1]" in s["tag"] for s in settings_):
            changes["schedule_ops"] = [{"op": "add", "index": -1}]
        Path(args.write).parent.mkdir(parents=True, exist_ok=True)
        Path(args.write).write_text(
            yaml.safe_dump({"changes": changes}, sort_keys=False), encoding="utf-8"
        )
        print(f"wrote {args.write}: paste `changes` into a case (cells replace the case's own)")
    return 0


def _step_rows(frame: pd.DataFrame, keys: list[str], value: str) -> pd.DataFrame:
    """Rows where the value changes per key (a row holds until the next one); a blank
    value ends the previous one."""
    out = []
    for _, g in frame.sort_values([*keys, "period"]).groupby(keys, sort=False):
        prev: float | None = None
        for row in g.itertuples(index=False):
            v = getattr(row, value)
            v = None if pd.isna(v) else round(float(v), 3)
            if v == prev:
                continue
            if v is None and prev is None:
                continue
            out.append({**row._asdict(), value: v})
            prev = v
    return pd.DataFrame(out, columns=frame.columns)


def cmd_export_reference(args: argparse.Namespace, settings: Settings, paths: Paths) -> int:
    from alvheim_tiein import bookings as bk
    from alvheim_tiein import levers as lv
    from alvheim_tiein import mhgrid, report
    from alvheim_tiein.economics import EconomicsConfig, load_shares
    from alvheim_tiein.optimise import runner as rn

    scope = _scope(args, settings, paths, required=True)
    project = scope.project
    assert project is not None
    ws = paths.workspace
    ref_dir = ws.reference_dir(scope.paths)
    out = Path(args.out) if args.out else scope.paths.root / "reference-upload"
    out.mkdir(parents=True, exist_ok=True)

    shares = load_shares(ref_dir / "licence_shares.csv")
    for col in ("valid_from", "valid_to"):
        shares[col] = shares[col].dt.strftime("%Y-%m-%d")
    shares[["license", "company", "share", "valid_from", "valid_to"]].to_csv(
        out / "licence_shares.csv", index=False
    )
    econ = EconomicsConfig.from_yaml(ref_dir / "economics.yaml")
    written = ["licence_shares"]
    (out / "prices.csv").unlink(missing_ok=True)
    if econ.value_basis == "price":
        prices = pd.read_csv(ref_dir / "prices.csv", parse_dates=["date"])
        prices["date"] = prices["date"].dt.strftime("%Y-%m-%d")
        prices[["date", "oil_price_per_bbl", "gas_price_per_sm3"]].to_csv(
            out / "prices.csv", index=False
        )
        written.append("prices")

    api = None if args.offline else AutogrationClient.from_env(scope.settings)
    try:
        payload = report.dataobject_tables(ws, project.model_id, api)
        groups = project.bookings.groups or bk.booking_groups(payload)
        members = report.group_members(ws, project.model_id, groups, api)
    finally:
        if api is not None:
            api.close()
    pd.DataFrame([(g, w) for g in groups for w in members[g]], columns=["group", "well"]).to_csv(
        out / "booking_members.csv", index=False
    )

    monthly = mhgrid.predict_steps("monthly")
    keys = ["group", "phase"]
    frames = [bk.booked_from_tables(payload, monthly, groups).assign(case="")]
    if args.study:
        sp = rn.StudyPaths(scope.paths, args.study)
        state = rn.load_state(sp.state)
        plans = rn.load_plans(rn.load_spec(sp.spec), sp.plans)
        for ev in state.evaluations if state else []:
            if not (ev.candidate and ev.task_id):
                continue
            name = state.spec.candidate(ev.candidate).booking_plan  # type: ignore[union-attr]
            if name:
                plan = plans[name].assign(period=lambda f: pd.to_datetime(f["period"]))
                frames.append(plan.assign(case=ev.task_id))
    booked = pd.concat(frames, ignore_index=True)
    booked = booked[["group", "period", "phase", "booked_sm3d", "case"]]
    booked = _step_rows(booked, [*keys, "case"], "booked_sm3d")
    booked["period"] = pd.to_datetime(booked["period"]).dt.strftime("%Y-%m-%d")
    booked.to_csv(out / "bookings.csv", index=False)

    limits = lv.fpso_limits(lv.ModelTables(payload))
    start = mhgrid.FORECAST_START.strftime("%Y-%m-%d")
    pd.DataFrame(
        [{"period": start, "phase": ph, "limit_sm3d": limits[ph]} for ph in ("oil", "gas", "water")]
    ).to_csv(out / "facility_limits.csv", index=False)

    econ_note = (
        "no prices.csv: the Results page values in Sm3 oe (relative earnings)"
        if econ.value_basis == "oe"
        else f"values in {econ.currency}"
    )
    print(
        f"wrote {', '.join(written)}, bookings, booking_members, facility_limits to {out}; "
        f"{econ_note}"
    )
    print(
        "economics to enter on the Results page: "
        f"tax rate {econ.tax_rate:g}, discount rate {econ.discount_rate:g}, valuation date "
        f"{econ.valuation_date}, gas {econ.gas_sm3_per_sm3oe:g} Sm3 per Sm3 oe"
    )
    print(
        "the files hold commercial data: upload them in the browser only (they stay local), "
        "never commit them"
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="tiein", description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)
    sub.add_parser(
        "init", help="create data/ with reference templates and the projects folder"
    ).set_defaults(fn=cmd_init)
    sub.add_parser("access", help="check API access, user and assets").set_defaults(fn=cmd_access)
    sub.add_parser(
        "request-access", help="ask the admins (in Teams) to make you a contributor"
    ).set_defaults(fn=cmd_request_access)
    s = sub.add_parser("register", help="register an .rsl model from the S-drive")
    s.add_argument("--s-drive", required=True, metavar="PATH", help=r"e.g. S:\ASSET\...\model.rsl")
    s.add_argument("--name", required=True, help="display name of the registration")
    s.add_argument("--asset", default="Alvheim")
    s.add_argument(
        "--wait", type=int, nargs="?", const=60, metavar="SECONDS", help="poll until it finishes"
    )
    s.set_defaults(fn=cmd_register)
    s = sub.add_parser("task", help="status, failure and missing files of one task")
    s.add_argument("task_id")
    s.add_argument("--logs", type=int, nargs="?", const=50, metavar="N", help="last N log lines")
    s.set_defaults(fn=cmd_task)
    s = sub.add_parser("models", help="list registered models")
    s.add_argument("--asset")
    s.add_argument("--search")
    s.set_defaults(fn=cmd_models)
    s = sub.add_parser("browse", help="browse a registered model's nodes")
    s.add_argument("model_id")
    s.add_argument("--path")
    s.add_argument("--search")
    s.add_argument("--limit", type=int, default=50)
    s.set_defaults(fn=cmd_browse)
    s = sub.add_parser(
        "settings", help="save a model's RESOLVE, module (optimiser) settings and DataObject tables"
    )
    s.add_argument("model_id")
    s.set_defaults(fn=cmd_settings)

    s = sub.add_parser("run", help="submit a one-off request outside any project")
    s.add_argument("request", help="YAML file with simulate request keys (model_id optional)")
    s.add_argument("--name", required=True, help="run name: unique per asset")
    s.add_argument("--model", metavar="MODEL_ID")
    s.add_argument("--asset", default="Alvheim")
    s.add_argument("--env", help="named environment from .env; default the default one")
    s.add_argument("--dry-run", action="store_true")
    s.set_defaults(fn=cmd_run)

    project = sub.add_parser("project", help="optional: group runs with a baseline and cases")
    psub = project.add_subparsers(dest="project_command", required=True)
    s = psub.add_parser("new", help="create a project from a registered model")
    s.add_argument("slug", help="folder name: lowercase letters, digits, dashes")
    s.add_argument("--name", required=True, help="display name; prefixes every run name")
    s.add_argument("--model", required=True, metavar="MODEL_ID", help="registered model task id")
    s.add_argument(
        "--type", choices=[t.value for t in ProjectType], default=ProjectType.CASE_COMPARISON.value
    )
    s.add_argument("--env", help="named environment from .env; default the default one")
    s.add_argument("--asset", default="Alvheim")
    s.add_argument("--switch-label", help="case comparison: the new reservoir, e.g. Froskelaar")
    s.add_argument("--switch-wells", help="case comparison: its wells, comma-separated: FL1,FL2")
    s.add_argument("--off-from", help="YYYY-MM-DD; default the model's forecast start")
    s.add_argument("--user-licenses", help="licence(s) of the new reservoir, comma-separated")
    s.add_argument(
        "--import-baseline", metavar="ID", help="use existing runs (group or task id) as baseline"
    )
    s.add_argument("--use", action="store_true", help="make it the current project")
    s.set_defaults(fn=cmd_project_new)
    psub.add_parser("list", help="all projects (* = current)").set_defaults(fn=cmd_project_list)
    for name, fn, text in (
        ("show", cmd_project_show, "a project's cases, runs and web-app comparison link"),
        ("check", cmd_project_check, "check a project against its model"),
        ("levers", cmd_project_levers, "gas-lift and choke dP settings of the booked wells"),
    ):
        s = psub.add_parser(name, help=text)
        s.add_argument("project", nargs="?", help="default: the current project")
        if name == "levers":
            s.add_argument("--wells", help="comma-separated; default the booking groups' wells")
        s.set_defaults(fn=fn)
    s = psub.add_parser("use", help="make a project the current one")
    s.add_argument("slug", nargs="?")
    s.add_argument("--none", action="store_true", help="no current project")
    s.set_defaults(fn=cmd_project_use)
    s = psub.add_parser("add-run", help="attach existing runs (anyone's) as an imported case")
    s.add_argument("ref", nargs="+", help="simulation (assumption group) or run (task) ids")
    s.add_argument("--case", required=True, help="new case name")
    s.add_argument("--project", metavar="SLUG", help="default: the current project")
    s.add_argument("--switch", choices=["on", "off"], help="case comparison: default on")
    s.add_argument("--label", help="name of a single imported run")
    s.add_argument("--description")
    s.add_argument("--other-model", action="store_true", help="allow runs of another model")
    s.set_defaults(fn=cmd_project_add_run)

    def scoped(parser: argparse.ArgumentParser, *, adhoc: bool = True) -> argparse.ArgumentParser:
        parser.add_argument("--project", metavar="SLUG", help="default: the current project")
        if adhoc:
            parser.add_argument(
                "--adhoc", action="store_true", help="runs outside projects (`tiein run`)"
            )
        return parser

    s = scoped(
        sub.add_parser("submit", help="start a case of a project, or `all` not yet submitted"),
        adhoc=False,
    )
    s.add_argument("case", help="case name from project.yaml, or `all`")
    s.add_argument("--dry-run", action="store_true", help="print the requests and run counts")
    s.add_argument("--force", action="store_true", help="submit a new revision")
    s.set_defaults(fn=cmd_submit)
    s = scoped(sub.add_parser("status", help="progress of a project's runs, or of one-off runs"))
    s.add_argument("--watch", type=int, metavar="SECONDS", help="poll until all runs finish")
    s.set_defaults(fn=cmd_status)
    s = scoped(sub.add_parser("fetch", help="download results and tracked steps of completed runs"))
    s.add_argument("--bundle", action="store_true", help="also the full DataExchange JSON")
    s.add_argument("--force", action="store_true")
    s.set_defaults(fn=cmd_fetch)
    s = scoped(sub.add_parser("steps", help="tracked variables of one run so far"))
    s.add_argument("case", help="case name (or one-off run name)")
    s.add_argument("--run", type=int, default=1, help="run number within a sweep")
    s.set_defaults(fn=cmd_steps)
    s = scoped(
        sub.add_parser("bookings", help="booked vs produced per group and company"), adhoc=False
    )
    s.add_argument("--offline", action="store_true", help="use cached model data only")
    s.set_defaults(fn=cmd_bookings)
    scoped(
        sub.add_parser("export-workbench", help="write a results-workbench folder"), adhoc=False
    ).set_defaults(fn=cmd_export_workbench)
    sub.add_parser("sodir", help="download public Sodir tables for the area").set_defaults(
        fn=cmd_sodir
    )
    sub.add_parser("demo", help="build data/demo from synthetic results").set_defaults(fn=cmd_demo)

    from alvheim_tiein.optimise import study as st
    from alvheim_tiein.optimise.runner import SETTLEMENT_RULES

    opt = sub.add_parser(
        "optimise", help="optimisation studies on a project (schemes of research/22)"
    )
    osub = opt.add_subparsers(dest="optimise_command", required=True)
    s = scoped(
        osub.add_parser("new", help="write a study.yaml from a scheme's template"), adhoc=False
    )
    s.add_argument("name", help="study name: lower case, digits and -")
    s.add_argument("--scheme", required=True, choices=st.SCHEMES)
    s.add_argument("--base", help="case every run starts from (default: first switched-on case)")
    s.add_argument(
        "--reference", help="comma-separated cases to compare against (default: baseline)"
    )
    s.add_argument("--description")
    s.add_argument("--force", action="store_true", help="replace a study that has not started")
    s.set_defaults(fn=cmd_optimise_new)
    s = scoped(osub.add_parser("list", help="the project's studies"), adhoc=False)
    s.set_defaults(fn=cmd_optimise_list)
    s = scoped(
        osub.add_parser("check", help="validate a study and build every kind of request"),
        adhoc=False,
    )
    s.add_argument("name")
    s.add_argument("--offline", action="store_true", help="use cached model data only")
    s.set_defaults(fn=cmd_optimise_check)
    s = scoped(
        osub.add_parser("step", help="follow, score and submit the next wave of a study"),
        adhoc=False,
    )
    s.add_argument("name", nargs="+", help="one or more studies, stepped in this order")
    s.add_argument("--dry-run", action="store_true", help="write the next wave's requests only")
    s.add_argument("--watch", type=int, metavar="SECONDS", help="repeat until the studies end")
    s.set_defaults(fn=cmd_optimise_step)
    for name, text, fn in (
        ("status", "evaluations of a study so far (offline)", cmd_optimise_status),
        ("report", "write the study's report tables and settlement", cmd_optimise_report),
        ("cancel", "stop a study and cancel its unfinished runs", cmd_optimise_cancel),
    ):
        s = scoped(osub.add_parser(name, help=text), adhoc=False)
        s.add_argument("name")
        s.set_defaults(fn=fn)
        if name == "report":
            s.add_argument("--rule", choices=SETTLEMENT_RULES, default="minimal")
    s = scoped(
        osub.add_parser("plans", help="write booking plans of a restructure study (S1, S2)"),
        adhoc=False,
    )
    s.add_argument("name")
    s.add_argument("--s2", required=True, help="case with the bookings lifted (demand)")
    s.add_argument("--s1", help="case with today's bookings (default: the study's base case)")
    s.add_argument("--lam", type=float, default=1.0, help="R1: share of unused capacity lent")
    s.add_argument(
        "--phi",
        type=lambda v: [float(x) for x in v.split(",")],
        default=[0.5, 0.8],
        help="R3: Froskelaar liquid caps as fractions of the S2 peak (comma-separated)",
    )
    s.add_argument("--no-r3", action="store_true", help="no Froskelaar cap candidates")
    s.add_argument("--offline", action="store_true", help="use cached model data only")
    s.set_defaults(fn=cmd_optimise_plans)

    s = scoped(
        sub.add_parser("mhgrid", help="a coarse time grid: steps, settings and remapped cells"),
        adhoc=False,
    )
    s.add_argument("--grid", default="mh")
    s.add_argument("--case", help="remap this case's cells too (default: the model alone)")
    s.add_argument("--offline", action="store_true", help="use cached model data only")
    s.add_argument("--table", metavar="CSV", help="write monthly vs remapped values per step")
    s.add_argument("--write", metavar="YAML", help="write a case `changes` block for the grid")
    s.set_defaults(fn=cmd_mhgrid)
    s = scoped(
        sub.add_parser(
            "export-reference", help="reference files for the Results page's project mode"
        ),
        adhoc=False,
    )
    s.add_argument("--out", metavar="DIR", help="default: <project>/reference-upload")
    s.add_argument("--study", help="add the booking plans of this study's runs (case = task id)")
    s.add_argument("--offline", action="store_true", help="use cached model data only")
    s.set_defaults(fn=cmd_export_reference)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        settings = Settings.from_env()
        return args.fn(args, settings, Paths(settings))
    except (
        AutogrationError,
        ConfigError,
        FileNotFoundError,
        KeyError,
        PrepareError,
        ProjectError,
    ) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    except httpx.TransportError as e:
        print(f"error: cannot reach {e.request.url}: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
