"""Advancing a study against Autogration: follow, score, plan, submit, report.

:meth:`Study.tick` is one step. It follows the submitted runs, scores the finished
ones, lets the study plan its next runs and submits as many as the wave size and your
run limits allow. The state (``study.json``) is saved after every submission, so a crash
never loses a started run. Study runs are not added to the project's ``runs.json``; to
compare one in the web app's Results, attach it with ``tiein project add-run``.

Layout: ``data/projects/<project>/studies/<study>/`` holds ``study.yaml`` (the spec),
``study.json`` (the state), ``plans/`` (booking plans) and ``report/``. Results and
tracked steps go to the project's shared ``results/`` and ``steps/`` folders.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

import pandas as pd
import yaml

from alvheim_tiein import bookings as bk
from alvheim_tiein import levers as lv
from alvheim_tiein import report as rp
from alvheim_tiein import settlement
from alvheim_tiein.client import FINAL, UNFINISHED, AutogrationClient, step_results_frame
from alvheim_tiein.economics import Reference
from alvheim_tiein.optimise import study as st
from alvheim_tiein.project import (
    HARD_MAX_ACTIVE_RUNS,
    Project,
    ProjectError,
    ProjectPaths,
    RunLog,
    Workspace,
    request_digest,
)

PLAN_COLUMNS = ["group", "period", "phase", "booked_sm3d"]
REFERENCE_FILES = ("entities.csv", "licence_shares.csv", "prices.csv", "economics.yaml")
SETTLEMENT_RULES = ("proportional", "minimal", "equal")
TIE_IN = (
    "the new reservoir is off in this comparator: the tie-in, settled by the tie-in "
    "agreement (tariffs and compensation; notebooks/01_with_without_settlement), not by "
    "the surplus rules"
)


# ---------------------------------------------------------------------- files
class StudyPaths:
    def __init__(self, project_paths: ProjectPaths, name: str) -> None:
        self.name = name
        self.root = project_paths.root / "studies" / name
        self.spec = self.root / "study.yaml"
        self.state = self.root / "study.json"
        self.plans = self.root / "plans"
        self.report = self.root / "report"


def study_names(project_paths: ProjectPaths) -> list[str]:
    root = project_paths.root / "studies"
    if not root.exists():
        return []
    return sorted(p.name for p in root.iterdir() if (p / "study.yaml").exists())


def load_spec(path: Path) -> st.StudySpec:
    if not path.exists():
        raise ProjectError(f"no study file {path}")
    try:
        return st.StudySpec.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")) or {})
    except ValueError as e:
        raise ProjectError(f"{path}: {e}") from e


def load_plans(spec: st.StudySpec, folder: Path) -> dict[str, pd.DataFrame]:
    out: dict[str, pd.DataFrame] = {}
    for c in spec.candidates:
        if not c.booking_plan or c.booking_plan in out:
            continue
        path = folder / c.booking_plan
        if not path.exists():
            raise ProjectError(
                f"candidate {c.name}: no booking plan {path} (`tiein optimise plans`)"
            )
        df = pd.read_csv(path)
        missing = [col for col in PLAN_COLUMNS if col not in df]
        if missing:
            raise ProjectError(f"{path}: missing columns {missing}")
        out[c.booking_plan] = df[PLAN_COLUMNS]
    return out


def load_state(path: Path) -> st.StudyState | None:
    if not path.exists():
        return None
    return st.StudyState.model_validate_json(path.read_text(encoding="utf-8"))


def save_state(state: st.StudyState, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(state.model_dump_json(indent=2), encoding="utf-8")
    tmp.replace(path)


def run_digest(body: Mapping[str, Any]) -> str:
    """Digest of what a request simulates: the run name is left out, so the same run from
    two studies matches."""
    return request_digest({k: v for k, v in body.items() if k != "user_specified_name"})


def shared_run(
    project_paths: ProjectPaths, study: str, digest: str, *, model_id: str, environment: str | None
) -> tuple[str, st.Evaluation] | None:
    """Another study's run of the same request on the same model and environment that is
    running or completed, as (``study eid``, evaluation)."""
    for name in study_names(project_paths):
        if name == study:
            continue
        other = load_state(StudyPaths(project_paths, name).state)
        if other is None or (other.model_id, other.environment) != (model_id, environment):
            continue
        for ev in other.evaluations:
            if ev.digest != digest or ev.group_id is None:
                continue
            running = ev.status == "submitted"
            completed = ev.status in ("completed", "scored") and ev.task_status == st.COMPLETED
            if running or completed:
                return f"{name} {ev.id}", ev
    return None


def reference_digest(folder: Path) -> str:
    h = hashlib.sha256()
    for name in REFERENCE_FILES:
        p = folder / name
        h.update(name.encode())
        h.update(p.read_bytes() if p.exists() else b"")
    return h.hexdigest()[:16]


def case_runs(project: Project, log: RunLog) -> dict[str, tuple[str, str]]:
    """Cases whose current revision is one run: (task id, status as last followed)."""
    by_case: dict[str, list[dict[str, Any]]] = {}
    for row in log.rows(project):
        by_case.setdefault(row["case"], []).append(row)
    return {
        case: (str(rows[0]["task_id"]), str(rows[0]["status"]))
        for case, rows in by_case.items()
        if len(rows) == 1 and rows[0].get("task_id")
    }


# -------------------------------------------------------------------- backend
class Backend(Protocol):
    def active_runs(self) -> int: ...
    def simulate(self, model_id: str, body: Mapping[str, Any]) -> dict[str, Any]: ...
    def group_tasks(self, group_id: str) -> list[dict[str, Any]]: ...
    def task(self, task_id: str) -> dict[str, Any]: ...
    def download_results(self, task_id: str, dest_dir: Path) -> Path: ...
    def steps(self, task_id: str) -> pd.DataFrame: ...
    def log_lines(self, task_id: str) -> list[str]: ...
    def cancel(self, task_id: str) -> None: ...


class ApiBackend:
    """:class:`Backend` over the Autogration API."""

    def __init__(self, api: AutogrationClient) -> None:
        self.api = api
        self._email: str | None = None

    def active_runs(self) -> int:
        if self._email is None:
            self._email = self.api.me().get("email")
        return sum(
            1
            for _ in self.api.tasks(
                task_type="petex_compute", status=list(UNFINISHED), created_by=self._email
            )
        )

    def simulate(self, model_id: str, body: Mapping[str, Any]) -> dict[str, Any]:
        return self.api.simulate(model_id, body)

    def group_tasks(self, group_id: str) -> list[dict[str, Any]]:
        return self.api.group_progress(group_id).tasks

    def task(self, task_id: str) -> dict[str, Any]:
        return self.api.task(task_id)

    def download_results(self, task_id: str, dest_dir: Path) -> Path:
        return self.api.download_results_parquet(task_id, dest_dir)

    def steps(self, task_id: str) -> pd.DataFrame:
        return step_results_frame(self.api.step_results(task_id))

    def log_lines(self, task_id: str) -> list[str]:
        entries: Any = self.api.task_logs(task_id)
        if isinstance(entries, Mapping):
            entries = entries.get("items") or entries.get("logs") or []
        return [str(e.get("message", "")) for e in entries]

    def cancel(self, task_id: str) -> None:
        self.api.cancel(task_id)


# -------------------------------------------------------------------- context
@dataclass
class StudyContext:
    """What scoring and building requests need, loaded once per command."""

    slug: str
    project: Project
    project_paths: ProjectPaths
    paths: StudyPaths
    tables: lv.ModelTables
    members: dict[str, list[str]]
    ref: Reference
    ref_digest: str

    @classmethod
    def load(
        cls, ws: Workspace, slug: str, name: str, api: AutogrationClient | None = None
    ) -> StudyContext:
        project, ppaths, _ = ws.load(slug)
        payload = rp.dataobject_tables(ws, project.model_id, api)
        groups = project.bookings.groups or bk.booking_groups(payload)
        members = rp.group_members(ws, project.model_id, groups, api)
        ref_dir = ws.reference_dir(ppaths)
        return cls(
            slug=slug,
            project=project,
            project_paths=ppaths,
            paths=StudyPaths(ppaths, name),
            tables=lv.ModelTables(payload),
            members=members,
            ref=Reference.load(ref_dir),
            ref_digest=reference_digest(ref_dir),
        )

    def log(self) -> RunLog:
        return RunLog(self.project_paths.runs)


@dataclass
class TickResult:
    followed: list[str] = field(default_factory=list)
    scored: list[str] = field(default_factory=list)
    submitted: list[str] = field(default_factory=list)
    shared: list[str] = field(default_factory=list)
    waiting: list[str] = field(default_factory=list)
    requests: list[tuple[str, dict[str, Any]]] = field(default_factory=list)
    shares: dict[str, str] = field(default_factory=dict)
    blocked: str | None = None
    finished: bool = False
    stop_reason: str | None = None


# ---------------------------------------------------------------------- study
class Study:
    def __init__(self, ctx: StudyContext, state: st.StudyState) -> None:
        self.ctx = ctx
        self.state = state
        self.plans = load_plans(state.spec, ctx.paths.plans)

    @property
    def spec(self) -> st.StudySpec:
        return self.state.spec

    @classmethod
    def open(cls, ctx: StudyContext, *, now: dt.datetime | None = None) -> Study:
        """The study's state, or a new one. A study that has not submitted anything yet
        follows edits to ``study.yaml``; once it has, the spec, the model, environment,
        VM size and the reference data are fixed."""
        spec = load_spec(ctx.paths.spec)
        state = load_state(ctx.paths.state)
        if state is None or (state.started_at is None and state.spec_digest != spec.digest()):
            runs = case_runs(ctx.project, ctx.log())
            state = st.StudyState.start(
                spec,
                slug=ctx.slug,
                project=ctx.project,
                case_tasks={c: t for c, (t, s) in runs.items() if s == st.COMPLETED},
                reference_digest=ctx.ref_digest,
                value_unit=ctx.ref.economics.value_unit,
                now=now,
            )
        else:
            _guard(state, spec, ctx)
        return cls(ctx, state)

    def save(self) -> None:
        save_state(self.state, self.ctx.paths.state)

    # ------------------------------------------------------------------ tick
    def tick(
        self, backend: Backend, *, now: dt.datetime | None = None, dry_run: bool = False
    ) -> TickResult:
        out = TickResult()
        s = self.state
        if s.finished:
            out.finished, out.stop_reason = True, s.stop_reason
            return out
        out.followed = self._follow(backend)
        self._update_case_tasks(backend)
        out.scored = self._score(backend)
        proposed = s.plan(now)
        out.finished, out.stop_reason = s.finished, s.stop_reason
        if dry_run:
            out.requests = [(ev.id, self.request(ev)) for ev in proposed]
            out.waiting = [ev.id for ev in proposed]
            for eid, body in out.requests:
                found = self.shared_run(body)
                if found is not None:
                    out.shares[eid] = found[0]
            return out
        if proposed:
            self._submit(backend, proposed, out)
        self.save()
        return out

    def shared_run(self, body: Mapping[str, Any]) -> tuple[str, st.Evaluation] | None:
        s = self.state
        return shared_run(
            self.ctx.project_paths,
            self.ctx.paths.name,
            run_digest(body),
            model_id=s.model_id,
            environment=s.environment,
        )

    def request(self, ev: st.Evaluation) -> dict[str, Any]:
        return st.build_request(
            self.spec,
            ev,
            self.ctx.project,
            self.ctx.tables,
            run_name=st.run_name(self.ctx.project, self.ctx.paths.name, ev),
            plans=self.plans,
        )

    def _follow(self, backend: Backend) -> list[str]:
        followed = []
        for ev in self.state.in_flight():
            if ev.task_id is None:
                tasks = backend.group_tasks(str(ev.group_id))
                if not tasks:
                    continue
                task = tasks[0]
            else:
                task = backend.task(ev.task_id)
            failure = task.get("failure")
            if task.get("status") in (st.FAILED, st.CANCELLED) and failure is None:
                failure = backend.task(task["task_id"]).get("failure")
            self.state.record_status(ev.id, task, failure=failure)
            followed.append(ev.id)
        return followed

    def _update_case_tasks(self, backend: Backend) -> None:
        s = self.state
        if not self.spec.reuse_case_runs:
            return
        wanted = {s.base_case, *self.spec.reference_cases} - set(s.case_tasks)
        if not wanted:
            return
        for case, (task_id, status) in case_runs(self.ctx.project, self.ctx.log()).items():
            if case not in wanted:
                continue
            if status not in FINAL:
                status = str(backend.task(task_id).get("status"))
            if status == st.COMPLETED:
                s.case_tasks[case] = task_id

    def _score(self, backend: Backend) -> list[str]:
        s = self.state
        ready = [ev for ev in s.evaluations if ev.status == "completed"]
        ready.sort(key=lambda ev: not (ev.base or ev.reference))
        scored = []
        limits = self._fpso_limits() if ready else None
        for ev in ready:
            comparator = None
            if not (ev.base or ev.reference):
                base = s.baseline_of(ev.fidelity)
                if base is not None and not base.done:
                    continue
                comparator = base.score if base is not None else None
            assert ev.task_id is not None
            results = self._results(ev.task_id, backend)
            steps = self._steps(ev.task_id, backend)
            lines = backend.log_lines(ev.task_id) if self.spec.constraints.check_logs else None
            try:
                score = st.score_results(
                    self.spec,
                    ev,
                    status=st.COMPLETED,
                    results=results,
                    ref=self.ctx.ref,
                    steps=steps,
                    members=self.ctx.members,
                    log_lines=lines,
                    comparator=comparator,
                    limits=limits,
                )
            except (KeyError, ValueError) as e:
                raise ProjectError(f"scoring {ev.id} (task {ev.task_id}): {e}") from e
            s.record_score(ev.id, score)
            scored.append(ev.id)
        return scored

    def _fpso_limits(self) -> dict[str, float] | None:
        """FPSO limits for the host's booked capacity; None where the model's tables
        don't have them (the basis then leaves the host out)."""
        try:
            return lv.fpso_limits(self.ctx.tables)
        except (KeyError, IndexError, ValueError):
            return None

    def _results(self, task_id: str, backend: Backend) -> pd.DataFrame:
        folder = self.ctx.project_paths.results
        path = folder / f"{task_id}.parquet"
        if not path.exists():
            backend.download_results(task_id, folder)
        df = pd.read_parquet(path)
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        return df

    def _steps(self, task_id: str, backend: Backend) -> pd.DataFrame:
        path = self.ctx.project_paths.steps / f"{task_id}.csv"
        if path.exists():
            return pd.read_csv(path, parse_dates=["time"])
        frame = backend.steps(task_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        frame.to_csv(path, index=False)
        return frame

    def _submit(self, backend: Backend, proposed: list[st.Evaluation], out: TickResult) -> None:
        s, limits = self.state, self.ctx.project.limits
        fresh = []
        for ev in proposed:
            body = self.request(ev)
            found = self.shared_run(body)
            if found is None:
                fresh.append((ev, body))
                continue
            origin, other = found
            s.record_shared(ev.id, origin, other, digest=run_digest(body))
            self.save()
            out.shared.append(ev.id)
        if not fresh:
            return
        per_submit = min(limits.max_runs_per_submit, HARD_MAX_ACTIVE_RUNS)
        cap = min(limits.max_active_runs, HARD_MAX_ACTIVE_RUNS)
        active = backend.active_runs()
        room = min(self.spec.budget.wave_size - len(s.in_flight()), cap - active, per_submit)
        if room <= 0:
            out.waiting = [ev.id for ev, _ in fresh]
            out.blocked = (
                f"{active} of your runs are unfinished (limit {cap}); "
                f"{len(s.in_flight())} of this study's (wave size {self.spec.budget.wave_size})"
            )
            return
        for ev, body in fresh[:room]:
            started = backend.simulate(self.ctx.project.model_id, body)
            s.record_submission(ev.id, started, digest=run_digest(body))
            self.save()
            out.submitted.append(ev.id)
        out.waiting = [ev.id for ev, _ in fresh[room:]]

    # ---------------------------------------------------------------- cancel
    def cancel(self, backend: Backend) -> list[str]:
        """Stop the study and cancel its unfinished runs; returns the cancelled task ids."""
        self._follow(backend)
        cancelled = []
        for run in self.state.cancel():
            if self.state.get(str(run["id"])).shared_from:
                continue
            ids = [run["task_id"]] if run["task_id"] else []
            if not ids and run["group_id"]:
                ids = [
                    t["task_id"]
                    for t in backend.group_tasks(run["group_id"])
                    if t.get("status") not in FINAL
                ]
            for task_id in ids:
                backend.cancel(str(task_id))
                cancelled.append(str(task_id))
        self.save()
        return cancelled


def _guard(state: st.StudyState, spec: st.StudySpec, ctx: StudyContext) -> None:
    problems = []
    if state.spec_digest != spec.digest():
        problems.append(
            "study.yaml changed after the study started; copy it to a new study instead"
        )
    p = ctx.project
    for what, was, now in (
        ("model", state.model_id, p.model_id),
        ("environment", state.environment, p.environment),
        ("VM size", state.vm_size, p.vm_size),
    ):
        if was != now:
            problems.append(f"the project's {what} changed from {was} to {now}")
    if state.reference_digest and state.reference_digest != ctx.ref_digest:
        problems.append("the reference data (economics, shares, entities) changed")
    if problems:
        raise ProjectError(
            f"study {ctx.paths.name}: " + "; ".join(problems) + " (scores would not compare)"
        )


# --------------------------------------------------------------------- report
def settlement_basis(
    state: st.StudyState, ev: st.Evaluation, against: st.Evaluation
) -> tuple[pd.Series | None, str]:
    """The proportional rule's basis ``r_l`` and whose bookings it is: the bookings in
    force under ``against`` for policy schemes, the plan's own for a restructure (a
    restructure changes the basis)."""
    src = ev if state.spec.scheme == "restructure_bookings" else against
    assert src.score is not None
    cap = src.score.booked_capacity
    return (pd.Series(cap, dtype=float) if cap else None), src.id


def settlement_table(
    state: st.StudyState,
    ev: st.Evaluation,
    against: st.Evaluation,
    label: str,
    *,
    tie_in: bool = False,
) -> pd.DataFrame:
    """Who pays whom if the plan of ``ev`` is adopted over ``against``: per licence the
    change Δ, and under each rule the award and transfer (positive received). The
    proportional rule splits the surplus by booked capacity (``basis``).

    ``tie_in``: the comparator has the new reservoir off. That change is the tie-in,
    settled by the tie-in agreement rather than by these rules (research/22), so only
    Δ is given (rule ``tie-in``)."""
    assert ev.score is not None and against.score is not None
    licences = sorted(set(ev.score.licence_values) | set(against.score.licence_values))
    delta = pd.Series(
        {
            lic: ev.score.licence_values.get(lic, 0.0) - against.score.licence_values.get(lic, 0.0)
            for lic in licences
        },
        name="delta",
    )
    if tie_in:
        return pd.DataFrame(
            [
                {"against": label, "rule": "tie-in", "license": lic, "delta": d, "note": TIE_IN}
                for lic, d in delta.items()
            ]
        )
    basis, basis_of = settlement_basis(state, ev, against)
    rows = []
    for rule in SETTLEMENT_RULES:
        r = basis if rule == "proportional" else None
        try:
            if rule == "proportional" and basis is None:
                raise ValueError(
                    f"no booked capacity for {basis_of}: scored without tracked group "
                    "limits (or before the basis was recorded)"
                )
            award = settlement.awards(delta, rule, basis=r)
        except ValueError as e:
            rows += [
                {"against": label, "rule": rule, "license": lic, "delta": d, "note": str(e)}
                for lic, d in delta.items()
            ]
            continue
        transfer = settlement.transfers(delta, award)
        note = f"basis: booked capacity of {basis_of}" if r is not None else ""
        rows += [
            {
                "against": label,
                "rule": rule,
                "license": lic,
                "delta": float(delta[lic]),
                "basis": float(r.get(lic, 0.0)) if r is not None else None,
                "award": float(award[lic]),
                "transfer": float(transfer[lic]),
                "note": note,
            }
            for lic in licences
        ]
    return pd.DataFrame(rows)


def write_report(
    state: st.StudyState, folder: Path, switches: Mapping[str, str | None] | None = None
) -> dict[str, Path]:
    """CSV tables and ``summary.json`` of a study. ``switches``: the new reservoir on
    or off per project case; comparators where it differs from the best plan's case are
    the tie-in and get no surplus split."""
    folder.mkdir(parents=True, exist_ok=True)
    out: dict[str, Path] = {}

    def save(name: str, frame: pd.DataFrame) -> None:
        path = folder / name
        frame.to_csv(path, index=False)
        out[name] = path

    save("evaluations.csv", state.table())
    scored = [ev for ev in state.evaluations if ev.score is not None and ev.score.objective]
    for attr, name in (
        ("licence_values", "licence_values.csv"),
        ("company_values", "company_values.csv"),
    ):
        rows = [
            {"id": ev.id, "fidelity": ev.fidelity, "what": ev.label, "name": k, "pv": v}
            for ev in scored
            for k, v in getattr(ev.score, attr).items()
        ]
        save(name, pd.DataFrame(rows, columns=["id", "fidelity", "what", "name", "pv"]))
    rows = [
        {"id": ev.id, "fidelity": ev.fidelity, "what": ev.label, "period": p, "value": v}
        for ev in scored
        for p, v in ev.score.by_period.items()  # type: ignore[union-attr]
    ]
    save(
        "objective_by_period.csv",
        pd.DataFrame(rows, columns=["id", "fidelity", "what", "period", "value"]),
    )

    outcome = state.outcome()
    settlements = []
    if outcome:
        best = state.get(outcome["id"])
        fid = outcome["fidelity"]
        comparators = [("base", state.baseline_of(fid))] + [
            (f"ref:{r}", state.find(fid, reference=r)) for r in state.spec.reference_cases
        ]
        for label, comp in comparators:
            if comp is not None and comp.score is not None and comp.score.feasible:
                on, off = (switches or {}).get(best.case), (switches or {}).get(comp.case)
                tie_in = on is not None and off is not None and on != off
                settlements.append(settlement_table(state, best, comp, label, tie_in=tie_in))
    if settlements:
        save("settlement.csv", pd.concat(settlements, ignore_index=True))

    summary = {
        "study": state.spec.name,
        "scheme": state.spec.scheme,
        "project": state.project,
        "base_case": state.base_case,
        "reference_cases": state.spec.reference_cases,
        "objective": state.spec.objective,
        "value_unit": state.value_unit,
        "stage": state.stage,
        "finished": state.finished,
        "stop_reason": state.stop_reason,
        "search_stop": state.search_stop,
        "runs_used": state.committed(),
        "max_evaluations": state.spec.budget.max_evaluations,
        "outcome": outcome,
        "screening": state.screening.get("result"),
        "active_levers": state.active,
        "fixed_levers": state.fixed,
        "pattern_incumbent": state.pattern.get("incumbent"),
    }
    path = folder / "summary.json"
    path.write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    out["summary.json"] = path
    return out


__all__ = [
    "ApiBackend",
    "Backend",
    "Study",
    "StudyContext",
    "StudyPaths",
    "TickResult",
    "case_runs",
    "load_plans",
    "load_spec",
    "load_state",
    "reference_digest",
    "save_state",
    "settlement_basis",
    "settlement_table",
    "study_names",
    "write_report",
]
