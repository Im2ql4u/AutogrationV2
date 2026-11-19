"""Optimisation studies: the outer loop around Autogration runs (research/22).

A **study** belongs to a project. Every run it makes starts from one of the project's
cases (``base_case``, by default the project's baseline) and adds lever cells, a
candidate's cells or a booking plan. A study is defined by ``study.yaml``
(:class:`StudySpec`) and its progress lives in ``study.json`` (:class:`StudyState`),
so it can be advanced one step at a time from the CLI, a notebook or a scheduled task.

Schemes (selectable; each has default stages, see :data:`DEFAULT_STAGES`):

- ``outer``: screening, then a pattern search on the levers that matter, then
  confirmation of the best points on the monthly grid;
- ``soften_bookings``: a grid over how hard the bookings steer GAP (weights alpha,
  released caps beta);
- ``total_then_settle``: candidates that maximise the hub (neutral weights, released
  bookings), valued then settled between the licences (``tiein optimise report``);
- ``restructure_bookings``: booking plans (R1 lend, R4 re-split, ...) and per-well caps.

Stages: ``base`` (the base case and the reference cases on the search grid), then
``screening``, ``pattern``, ``grid`` or ``candidates`` on the search grid, and
``confirm`` on the confirmation grid. Searching runs on a coarse grid (MH, about 2 h on
D4) with the step-indexed tables remapped (:mod:`alvheim_tiein.mhgrid`); confirmation runs
monthly, reusing the project's completed monthly runs of the base and reference cases.

Everything here is pure: :mod:`alvheim_tiein.optimise.runner` talks to Autogration.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
from collections.abc import Iterable, Mapping, Sequence
from typing import Any, Literal

import pandas as pd
from pydantic import BaseModel, Field, field_validator, model_validator

from alvheim_tiein import bookings as bk
from alvheim_tiein import feasibility, ledgers, mhgrid
from alvheim_tiein import levers as lv
from alvheim_tiein.economics import Reference, value_volumes
from alvheim_tiein.optimise import algorithms as alg
from alvheim_tiein.project import (
    Project,
    ProjectError,
    _merge,
    estimate_runs,
    expand_cells,
)
from alvheim_tiein.results import period_volumes

Scheme = Literal["outer", "soften_bookings", "total_then_settle", "restructure_bookings"]
Stage = Literal["base", "screening", "pattern", "grid", "candidates", "confirm"]
Objective = Literal["pv", "cash_flow", "revenue", "oe_sm3", "oil_sm3"]
Status = Literal["proposed", "submitted", "completed", "scored", "skipped"]

SCHEMES: tuple[str, ...] = (
    "outer",
    "soften_bookings",
    "total_then_settle",
    "restructure_bookings",
)
DEFAULT_STAGES: dict[str, tuple[Stage, ...]] = {
    "outer": ("base", "screening", "pattern", "confirm"),
    "soften_bookings": ("base", "grid", "confirm"),
    "total_then_settle": ("base", "candidates", "confirm"),
    "restructure_bookings": ("base", "candidates", "confirm"),
}
SEARCH_STAGES = frozenset({"screening", "pattern", "grid", "candidates"})
RETRYABLE_FAILURES = frozenset({"job_failed", "unknown", "blob_parsing_error"})
"""Failure categories worth a second attempt (infrastructure, not the model)."""
COMPLETED, FAILED, CANCELLED = "Completed", "Failed", "Cancelled"
STATE_VERSION = 1
_NAME = r"^[a-z0-9][a-z0-9-]*$"
_KEY_DIGITS = 9


def now_utc() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def _iso(when: dt.datetime) -> str:
    return when.astimezone(dt.UTC).isoformat(timespec="seconds")


def _parse(when: str) -> dt.datetime:
    return dt.datetime.fromisoformat(when)


def theta_key(theta: Mapping[str, float] | None) -> tuple[tuple[str, float], ...]:
    """Hashable, rounded form of a point: equal points give equal keys."""
    return tuple(sorted((k, round(float(v), _KEY_DIGITS) + 0.0) for k, v in (theta or {}).items()))


# ------------------------------------------------------------------------- spec
class Fidelity(BaseModel):
    """Time grids: ``search`` for the base, screening and search stages; ``confirm``
    for the confirmation runs. ``forced_steps`` are the dates RESOLVE forces a step at
    (default :data:`alvheim_tiein.mhgrid.FORCED_STEPS`)."""

    search: str = "mh"
    confirm: str = "monthly"
    weights: mhgrid.Weights = "months"
    forced_steps: list[dt.date] | None = None

    @field_validator("search", "confirm")
    @classmethod
    def _known_grid(cls, value: str) -> str:
        if value not in mhgrid.GRIDS:
            raise ValueError(f"no grid {value!r}; grids: {', '.join(mhgrid.GRIDS)}")
        return value

    def forced(self) -> tuple[pd.Timestamp, ...]:
        if self.forced_steps is None:
            return mhgrid.FORCED_STEPS
        return tuple(pd.Timestamp(d) for d in self.forced_steps)

    def steps(self, grid: str) -> list[pd.Timestamp]:
        return mhgrid.predict_steps(grid, forced=self.forced())


class StudyBudget(BaseModel):
    max_evaluations: int = Field(
        default=40,
        ge=1,
        le=500,
        description="Runs on the search grid, retries included (confirmation not counted).",
    )
    wave_size: int = Field(default=6, ge=1, le=50, description="This study's runs at once.")
    confirm: int = Field(default=3, ge=0, description="Best points re-run on the confirm grid.")
    confirm_base: bool = Field(
        default=True, description="Also run the base and reference cases on the confirm grid."
    )
    max_hours: float | None = Field(
        default=None,
        gt=0,
        description="Wall-clock limit from the first submission; then only confirm runs.",
    )
    max_attempts: int = Field(default=2, ge=1, le=5)


class AlgorithmSettings(BaseModel):
    seed: int = 0
    active_levers: int = Field(default=alg.DEFAULT_ACTIVE_LEVERS, ge=1)
    mesh: float = Field(default=alg.DEFAULT_MESH, gt=0)
    min_mesh: float = Field(default=alg.MIN_MESH, gt=0)
    max_mesh: float = Field(default=alg.MAX_MESH, gt=0)
    min_improvement: float = Field(default=0.0, ge=0)
    max_unsuccessful_polls: int | None = Field(default=alg.NO_IMPROVEMENT_POLLS, ge=1)


class Constraints(BaseModel):
    """Feasibility beyond a clean run.

    ``no_loss`` licences (``"*"``: all) may not end up worse than in ``no_loss_against``
    (``base``, or a reference case such as the Froskelår-off baseline) by more than
    ``no_loss_tol`` (PV, absolute), measured on the participant ledger (production and
    tariffs, no settlement transfers) at the same fidelity."""

    no_loss: list[str] | Literal["*"] = Field(default_factory=list)
    no_loss_against: str = "base"
    no_loss_tol: float = Field(default=0.0, ge=0)
    violation_tol: float = Field(default=0.02, ge=0)
    check_logs: bool = Field(
        default=False,
        description="Treat solver/OpenServer error lines in the task logs as infeasible.",
    )


class Candidate(BaseModel):
    """A named point: lever values (``theta``), extra cells and/or a booking plan
    (CSV in the study's ``plans/`` folder: group, period, phase, booked_sm3d)."""

    name: str = Field(pattern=r"^[A-Za-z0-9_.+-]+$")
    description: str = ""
    theta: dict[str, float] = Field(default_factory=dict)
    cells: list[dict[str, Any]] = Field(default_factory=list)
    booking_plan: str | None = None

    @field_validator("cells")
    @classmethod
    def _expand(cls, cells: list[dict[str, Any]]) -> list[dict[str, Any]]:
        try:
            return expand_cells(cells)
        except ProjectError as e:
            raise ValueError(str(e)) from e


class StudySpec(BaseModel):
    name: str = Field(pattern=_NAME)
    scheme: Scheme
    description: str = ""
    base_case: str | None = Field(
        default=None, description="Case every run starts from; None: the project baseline."
    )
    reference_cases: list[str] = Field(
        default_factory=list,
        description="Cases run as they are at each fidelity, to compare against (S0, ...).",
    )
    objective: Objective = "pv"
    reuse_case_runs: bool = Field(
        default=True,
        description=(
            "Confirm against the project's completed monthly runs of the base and reference "
            "cases instead of re-running them (off when, e.g., an imported run may differ "
            "from the case as this toolkit builds it)."
        ),
    )
    levers: list[lv.LeverDef] = Field(default_factory=list)
    stages: list[Stage] = Field(default_factory=list)
    candidates: list[Candidate] = Field(default_factory=list)
    fidelity: Fidelity = Field(default_factory=Fidelity)
    budget: StudyBudget = Field(default_factory=StudyBudget)
    algorithm: AlgorithmSettings = Field(default_factory=AlgorithmSettings)
    constraints: Constraints = Field(default_factory=Constraints)

    @model_validator(mode="after")
    def _check(self) -> StudySpec:
        stages = self.stage_list
        if not stages or stages[0] != "base":
            raise ValueError("stages start with `base`")
        if len(set(stages)) != len(stages):
            raise ValueError(f"stages repeat: {stages}")
        if "confirm" in stages and stages[-1] != "confirm":
            raise ValueError("`confirm` is the last stage")
        if "screening" in stages and (
            "pattern" not in stages or stages.index("screening") > stages.index("pattern")
        ):
            raise ValueError("`screening` picks the levers for a later `pattern` stage")
        names = [lever.name for lever in self.levers]
        if len(set(names)) != len(names):
            raise ValueError(f"lever names repeat: {names}")
        if {"screening", "pattern", "grid"} & set(stages):
            if not self.levers:
                raise ValueError("screening, pattern and grid stages need levers")
            self.search_levers()
        cand_names = [c.name for c in self.candidates]
        if len(set(cand_names)) != len(cand_names):
            raise ValueError(f"candidate names repeat: {cand_names}")
        if "candidates" in stages and not self.candidates:
            raise ValueError("the candidates stage needs candidates")
        for c in self.candidates:
            unknown = sorted(set(c.theta) - set(names))
            if unknown:
                raise ValueError(f"candidate {c.name}: {unknown} are not levers")
            for lever in self.levers:
                if lever.baseline is None and lever.name not in c.theta:
                    raise ValueError(
                        f"candidate {c.name}: give {lever.name} (the lever has no baseline)"
                    )
                v = c.theta.get(lever.name)
                if v is not None and not lever.lower <= v <= lever.upper:
                    raise ValueError(f"candidate {c.name}: {lever.name}={v} outside its bounds")
        if len(set(self.reference_cases)) != len(self.reference_cases):
            raise ValueError("reference cases repeat")
        if self.base_case is not None and self.base_case in self.reference_cases:
            raise ValueError("the base case is not also a reference case")
        against = self.constraints.no_loss_against
        if against != "base" and against not in self.reference_cases:
            raise ValueError(f"no_loss_against {against!r}: use `base` or a reference case")
        a = self.algorithm
        if not a.min_mesh <= a.mesh <= a.max_mesh:
            raise ValueError("need min_mesh <= mesh <= max_mesh")
        need = self.required_runs()
        if need > self.budget.max_evaluations:
            raise ValueError(
                f"the stages need at least {need} runs; budget.max_evaluations is "
                f"{self.budget.max_evaluations}"
            )
        return self

    @property
    def stage_list(self) -> list[Stage]:
        return list(self.stages or DEFAULT_STAGES[self.scheme])

    def search_levers(self) -> list[alg.Lever]:
        try:
            return [
                alg.Lever(
                    lever.name,
                    lever.lower,
                    lever.upper,
                    baseline=lever.baseline,
                    levels=tuple(lever.levels) if lever.levels else None,
                )
                for lever in self.levers
            ]
        except ValueError as e:
            raise ValueError(f"{e} (a searched lever needs lower < upper)") from e

    def lever_defaults(self) -> dict[str, float]:
        """Each lever's baseline, else the centre of its bounds."""
        return {
            lever.name: lever.baseline
            if lever.baseline is not None
            else 0.5 * (lever.lower + lever.upper)
            for lever in self.levers
        }

    def baseline_theta(self) -> dict[str, float] | None:
        """The point that is the base case: {} without levers, the baselines when every
        lever has one, else None (then no point is the base case)."""
        if not self.levers:
            return {}
        if all(lever.baseline is not None for lever in self.levers):
            return {lever.name: float(lever.baseline) for lever in self.levers}  # type: ignore[arg-type]
        return None

    def candidate(self, name: str) -> Candidate:
        for c in self.candidates:
            if c.name == name:
                return c
        raise KeyError(f"no candidate {name!r}")

    def required_runs(self) -> int:
        """Search-grid runs the stages need at least (no retries, no reuse)."""
        stages = self.stage_list
        d = len(self.levers)
        n = 1 + len(self.reference_cases)
        if "screening" in stages:
            n += alg.screening_runs(d)
        if "pattern" in stages:
            k = min(self.algorithm.active_levers, d) if "screening" in stages else d
            n += 2 * k
        if "grid" in stages:
            n += len(alg.grid(self.search_levers()))
        if "candidates" in stages:
            n += len(self.candidates)
        return n

    def digest(self) -> str:
        text = json.dumps(self.model_dump(mode="json"), sort_keys=True, default=str)
        return hashlib.sha256(text.encode()).hexdigest()[:16]


# ----------------------------------------------------------------- evaluations
class Score(BaseModel):
    feasible: bool
    objective: float | None = None
    reasons: list[str] = Field(default_factory=list)
    licence_values: dict[str, float] = Field(default_factory=dict)
    company_values: dict[str, float] = Field(default_factory=dict)
    by_period: dict[str, float] = Field(default_factory=dict)
    """The objective per period (ISO date): for window flags and plots."""
    window_share: float | None = None
    window_flag: bool = False
    steps_missing: int = 0
    steps_unexpected: int = 0
    checks: dict[str, Any] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)


class Evaluation(BaseModel):
    """One run of the study: a point (``theta``), a candidate, the base case or a
    reference case, on one grid."""

    id: str
    stage: Stage
    fidelity: str
    case: str
    theta: dict[str, float] | None = None
    base: bool = False
    reference: str | None = None
    candidate: str | None = None
    source: str | None = None
    """For confirmation runs: the search-grid evaluation confirmed."""
    status: Status = "proposed"
    attempt: int = 1
    task_id: str | None = None
    group_id: str | None = None
    task_status: str | None = None
    failure: str | None = None
    digest: str | None = None
    reuse_task: str | None = None
    """A completed run of the case used as this evaluation (no new run)."""
    shared_from: str | None = None
    """``study eid`` of another study's evaluation with the same request whose run this
    one follows (no new run)."""
    history: list[dict[str, Any]] = Field(default_factory=list)
    proposed_at: str
    submitted_at: str | None = None
    finished_at: str | None = None
    score: Score | None = None

    @property
    def done(self) -> bool:
        return self.status in ("scored", "skipped")

    @property
    def spent(self) -> int:
        """Runs this evaluation has started or is about to start."""
        if self.reuse_task or self.shared_from:
            return 0
        if self.status == "skipped" and self.group_id is None and self.task_id is None:
            return self.attempt - 1
        return self.attempt

    @property
    def label(self) -> str:
        if self.base:
            return "base"
        if self.reference:
            return f"ref:{self.reference}"
        if self.candidate:
            return self.candidate
        if self.theta:
            return ", ".join(f"{k}={v:.4g}" for k, v in sorted(self.theta.items()))
        return "-"


class StudyState(BaseModel):
    version: int = STATE_VERSION
    spec: StudySpec
    spec_digest: str
    project: str
    model_id: str
    environment: str | None = None
    vm_size: str | None = None
    base_case: str
    reference_digest: str | None = None
    value_unit: str = ""
    """Unit of the objective and PV values (``Sm3 oe`` or a currency), from economics.yaml."""
    case_tasks: dict[str, str] = Field(default_factory=dict)
    """Completed monthly runs of the base and reference cases, reused when confirming."""
    created_at: str
    started_at: str | None = None
    stage_index: int = 0
    evaluations: list[Evaluation] = Field(default_factory=list)
    stage_ids: dict[str, list[str]] = Field(default_factory=dict)
    screening: dict[str, Any] = Field(default_factory=dict)
    active: list[str] = Field(default_factory=list)
    fixed: dict[str, float] = Field(default_factory=dict)
    pattern: dict[str, Any] = Field(default_factory=dict)
    search_stop: str | None = None
    stop_reason: str | None = None
    finished: bool = False
    cancelled: bool = False
    log: list[dict[str, Any]] = Field(default_factory=list)

    # ---------------------------------------------------------------- creating
    @classmethod
    def start(
        cls,
        spec: StudySpec,
        *,
        slug: str,
        project: Project,
        case_tasks: Mapping[str, str] | None = None,
        reference_digest: str | None = None,
        value_unit: str = "",
        now: dt.datetime | None = None,
    ) -> StudyState:
        """A new study of ``project``. ``case_tasks``: completed monthly runs per case."""
        base = spec.base_case or project.baseline_case.name
        for name in [base, *spec.reference_cases]:
            project.case(name)
        if base in spec.reference_cases:
            raise ProjectError(f"{base} is the base case; drop it from reference_cases")
        wanted = {base, *spec.reference_cases} if spec.reuse_case_runs else set()
        return cls(
            spec=spec,
            spec_digest=spec.digest(),
            project=slug,
            model_id=project.model_id,
            environment=project.environment,
            vm_size=project.vm_size,
            base_case=base,
            reference_digest=reference_digest,
            value_unit=value_unit,
            case_tasks={k: v for k, v in (case_tasks or {}).items() if k in wanted},
            created_at=_iso(now or now_utc()),
        )

    # ------------------------------------------------------------------ access
    @property
    def stages(self) -> list[Stage]:
        return self.spec.stage_list

    @property
    def stage(self) -> Stage | None:
        s = self.stages
        return s[self.stage_index] if self.stage_index < len(s) else None

    def get(self, eid: str) -> Evaluation:
        for ev in self.evaluations:
            if ev.id == eid:
                return ev
        raise KeyError(f"no evaluation {eid!r}")

    def committed(self) -> int:
        """Search-grid runs started or about to start (confirmation not counted)."""
        return sum(ev.spent for ev in self.evaluations if ev.stage != "confirm")

    def remaining(self) -> int:
        return self.spec.budget.max_evaluations - self.committed()

    def in_flight(self) -> list[Evaluation]:
        return [ev for ev in self.evaluations if ev.status == "submitted"]

    def proposed(self) -> list[Evaluation]:
        return [ev for ev in self.evaluations if ev.status == "proposed"]

    def find(
        self,
        fidelity: str,
        *,
        theta: Mapping[str, float] | None = None,
        base: bool = False,
        reference: str | None = None,
        candidate: str | None = None,
    ) -> Evaluation | None:
        """An evaluation of the same thing on the same grid. Plain points match any
        point evaluation (the base case included) with the same lever values."""
        for ev in self.evaluations:
            if ev.fidelity != fidelity:
                continue
            if reference is not None:
                if ev.reference == reference:
                    return ev
            elif candidate is not None:
                if ev.candidate == candidate:
                    return ev
            elif base:
                if ev.base:
                    return ev
            elif (
                theta is not None
                and ev.reference is None
                and ev.candidate is None
                and ev.theta is not None
                and theta_key(ev.theta) == theta_key(theta)
            ):
                return ev
        return None

    def _note(self, event: str, now: dt.datetime | None = None, **fields: Any) -> None:
        self.log.append({"at": _iso(now or now_utc()), "event": event, **fields})

    def _propose(
        self,
        stage: Stage,
        fidelity: str,
        *,
        case: str,
        theta: Mapping[str, float] | None = None,
        base: bool = False,
        reference: str | None = None,
        candidate: str | None = None,
        source: str | None = None,
        now: dt.datetime | None = None,
    ) -> Evaluation:
        reuse = None
        if (base or reference) and fidelity == "monthly":
            reuse = self.case_tasks.get(case)
        ev = Evaluation(
            id=f"e{len(self.evaluations) + 1:03d}",
            stage=stage,
            fidelity=fidelity,
            case=case,
            theta=None if theta is None else {k: float(v) for k, v in theta.items()},
            base=base,
            reference=reference,
            candidate=candidate,
            source=source,
            proposed_at=_iso(now or now_utc()),
        )
        if reuse:
            ev.reuse_task, ev.task_id = reuse, reuse
            ev.status, ev.task_status = "completed", COMPLETED
        self.evaluations.append(ev)
        return ev

    def _ensure(
        self,
        stage: Stage,
        fidelity: str,
        *,
        case: str,
        theta: Mapping[str, float] | None = None,
        base: bool = False,
        reference: str | None = None,
        candidate: str | None = None,
        source: str | None = None,
    ) -> Evaluation | None:
        """The matching evaluation, else a new one; None when the budget is spent."""
        found = self.find(
            fidelity, theta=theta, base=base, reference=reference, candidate=candidate
        )
        if found is not None:
            return found
        reusable = (base or reference) and fidelity == "monthly" and case in self.case_tasks
        if stage != "confirm" and not reusable and self.remaining() < 1:
            return None
        return self._propose(
            stage,
            fidelity,
            case=case,
            theta=theta,
            base=base,
            reference=reference,
            candidate=candidate,
            source=source,
        )

    # --------------------------------------------------------------- recording
    def record_submission(
        self,
        eid: str,
        started: Mapping[str, Any],
        *,
        digest: str | None = None,
        now: dt.datetime | None = None,
    ) -> None:
        ev = self.get(eid)
        when = _iso(now or now_utc())
        ev.status, ev.group_id, ev.digest = "submitted", started["assumption_group_id"], digest
        ev.submitted_at = when
        if self.started_at is None:
            self.started_at = when

    def record_shared(
        self,
        eid: str,
        origin: str,
        other: Evaluation,
        *,
        digest: str,
        now: dt.datetime | None = None,
    ) -> None:
        """Follow another study's run of the same request instead of starting one."""
        ev = self.get(eid)
        when = _iso(now or now_utc())
        ev.shared_from, ev.digest = origin, digest
        ev.task_id, ev.group_id, ev.task_status = other.task_id, other.group_id, other.task_status
        ev.submitted_at = when
        if other.task_status == COMPLETED:
            ev.status, ev.finished_at = "completed", when
        else:
            ev.status = "submitted"
        if self.started_at is None:
            self.started_at = when
        self._note("shared", now, id=eid, run=origin)

    def record_status(
        self,
        eid: str,
        task: Mapping[str, Any],
        *,
        failure: Mapping[str, Any] | None = None,
        now: dt.datetime | None = None,
    ) -> None:
        """A task's status. A failed run is retried when the failure is an
        infrastructure one (or unknown), attempts and budget allow; a model failure or
        a cancelled run is infeasible."""
        ev = self.get(eid)
        status = str(task.get("status"))
        ev.task_id = task.get("task_id") or ev.task_id
        ev.task_status = status
        when = _iso(now or now_utc())
        if status == COMPLETED:
            ev.status, ev.finished_at = "completed", when
            return
        if status not in (FAILED, CANCELLED):
            return
        category = (failure or {}).get("category")
        message = str((failure or {}).get("message") or "")[:500]
        ev.failure = f"{category or 'unknown'}: {message}".strip().rstrip(":")
        retryable = status == FAILED and (category is None or category in RETRYABLE_FAILURES)
        budget_left = ev.stage == "confirm" or self.remaining() >= 1
        if retryable and ev.attempt < self.spec.budget.max_attempts and budget_left:
            ev.history.append(
                {
                    "attempt": ev.attempt,
                    "task_id": ev.task_id,
                    "group_id": ev.group_id,
                    "status": status,
                    "failure": ev.failure,
                    "at": when,
                }
            )
            ev.attempt += 1
            ev.status, ev.task_id, ev.group_id, ev.task_status = "proposed", None, None, None
            ev.shared_from = None
            self._note("retry", now, id=eid, attempt=ev.attempt, failure=ev.failure)
            return
        what = "cancelled" if status == CANCELLED else f"failed ({ev.failure})"
        ev.status, ev.finished_at = "scored", when
        ev.score = Score(feasible=False, reasons=[f"run {what}"])

    def record_score(self, eid: str, score: Score) -> None:
        ev = self.get(eid)
        ev.status, ev.score = "scored", score

    def cancel(self, now: dt.datetime | None = None) -> list[dict[str, str | None]]:
        """Stop the study: runs not yet submitted are skipped. Returns the submitted runs
        (``id``, ``task_id``, ``group_id``) to cancel in Autogration."""
        running = [
            {"id": ev.id, "task_id": ev.task_id, "group_id": ev.group_id} for ev in self.in_flight()
        ]
        for ev in self.evaluations:
            if not ev.done and ev.status != "completed":
                ev.status, ev.failure = "skipped", "cancelled"
        self.cancelled, self.finished, self.stop_reason = True, True, "cancelled"
        self._note("cancelled", now, running=[r["id"] for r in running])
        return running

    # ------------------------------------------------------------------ values
    def comparator(self, fidelity: str) -> Evaluation | None:
        against = self.spec.constraints.no_loss_against
        if against == "base":
            return self.find(fidelity, base=True)
        return self.find(fidelity, reference=against)

    def baseline_of(self, fidelity: str) -> Evaluation | None:
        return self.find(fidelity, base=True)

    def no_loss_shortfalls(self, ev: Evaluation) -> dict[str, float]:
        """Licences worse off than in the comparator by more than the tolerance."""
        c = self.spec.constraints
        if not c.no_loss or ev.base or ev.reference is not None or ev.score is None:
            return {}
        comp = self.comparator(ev.fidelity)
        if comp is None or comp.score is None or not comp.score.feasible:
            return {}
        values, ref = ev.score.licence_values, comp.score.licence_values
        licences = sorted(set(ref) | set(values)) if c.no_loss == "*" else list(c.no_loss)
        out = {}
        for lic in licences:
            short = ref.get(lic, 0.0) - values.get(lic, 0.0)
            if short > c.no_loss_tol:
                out[lic] = short
        return out

    def effective(self, ev: Evaluation) -> tuple[float | None, bool]:
        """(objective, feasible) as the search sees it: feasibility includes the
        no-loss constraint."""
        s = ev.score
        if s is None:
            return None, False
        if not s.feasible or s.objective is None or not math.isfinite(s.objective):
            return s.objective, False
        return s.objective, not self.no_loss_shortfalls(ev)

    def best(self, fidelity: str, n: int = 1) -> list[Evaluation]:
        """The ``n`` best distinct feasible points or candidates on a grid (the base and
        reference cases left out)."""
        rows = []
        for ev in self.evaluations:
            if ev.fidelity != fidelity or ev.base or ev.reference is not None:
                continue
            value, ok = self.effective(ev)
            if ok and value is not None:
                rows.append((value, ev))
        rows.sort(key=lambda r: -r[0])
        seen, out = set(), []
        for _, ev in rows:
            key = (ev.candidate, theta_key(ev.theta))
            if key in seen:
                continue
            seen.add(key)
            out.append(ev)
            if len(out) == n:
                break
        return out

    def outcome(self) -> dict[str, Any]:
        """The best result on the most trusted grid that has one, against the base."""
        fids = [self.spec.fidelity.confirm, self.spec.fidelity.search]
        for fid in dict.fromkeys(fids):
            top = self.best(fid, 1)
            if top:
                ev = top[0]
                base = self.baseline_of(fid)
                base_value = base.score.objective if base and base.score else None
                value = ev.score.objective if ev.score else None
                gain = None if value is None or base_value is None else value - base_value
                return {
                    "fidelity": fid,
                    "id": ev.id,
                    "label": ev.label,
                    "theta": ev.theta,
                    "candidate": ev.candidate,
                    "objective": value,
                    "base_objective": base_value,
                    "gain": gain,
                    "window_flag": bool(ev.score and ev.score.window_flag),
                }
        return {}

    def table(self) -> pd.DataFrame:
        rows = []
        for ev in self.evaluations:
            value, ok = self.effective(ev)
            s = ev.score
            rows.append(
                {
                    "id": ev.id,
                    "stage": ev.stage,
                    "fidelity": ev.fidelity,
                    "what": ev.label,
                    "case": ev.case,
                    "status": ev.status,
                    "attempt": ev.attempt,
                    "task_id": ev.task_id,
                    "task_status": ev.task_status,
                    "objective": value,
                    "feasible": ok if s else None,
                    "window_flag": s.window_flag if s else None,
                    "reasons": "; ".join(
                        [
                            *(s.reasons if s else []),
                            *(
                                f"{lic} loses {v:,.0f}"
                                for lic, v in self.no_loss_shortfalls(ev).items()
                            ),
                        ]
                    ),
                    "source": ev.source,
                    "shared_from": ev.shared_from,
                    **{f"theta.{k}": v for k, v in (ev.theta or {}).items()},
                }
            )
        return pd.DataFrame(rows)

    # ---------------------------------------------------------------- planning
    def over_time(self, now: dt.datetime) -> bool:
        limit = self.spec.budget.max_hours
        if limit is None or self.started_at is None:
            return False
        return (now - _parse(self.started_at)).total_seconds() > limit * 3600.0

    def plan(self, now: dt.datetime | None = None) -> list[Evaluation]:
        """Advance the stages as far as the finished runs allow; returns the evaluations
        waiting to be submitted."""
        now = now or now_utc()
        if self.finished:
            return []
        stages = self.stages
        if self.over_time(now) and self.stage not in (None, "confirm"):
            self._wall_clock(now)
            if any(not ev.done for ev in self.evaluations if ev.stage != "confirm"):
                return self.proposed()
            self.stage_index = stages.index("confirm") if "confirm" in stages else len(stages)
        while self.stage_index < len(stages):
            stage = stages[self.stage_index]
            complete = getattr(self, f"_stage_{stage}")()
            if self.stop_reason is not None:
                self.finished = True
                self._note("stopped", now, reason=self.stop_reason, stage=stage)
                return []
            if not complete:
                return self.proposed()
            self._note("stage_done", now, stage=stage)
            self.stage_index += 1
        self.finished, self.stop_reason = True, "completed"
        self._note("finished", now, outcome=self.outcome())
        return []

    def _wall_clock(self, now: dt.datetime) -> None:
        for ev in self.evaluations:
            if ev.status == "proposed" and ev.stage != "confirm":
                ev.status, ev.failure = "skipped", "wall_clock"
        if self.pattern.get("search"):
            ps = alg.PatternSearch.from_dict(self.pattern["search"])
            if ps.stop_reason() is None:
                ps.stop("wall_clock")
                self.pattern["search"] = ps.to_dict()
        if self.search_stop != "wall_clock":
            self.search_stop = "wall_clock"
            self._note("wall_clock", now, max_hours=self.spec.budget.max_hours)

    def _ids_done(self, ids: Iterable[str]) -> bool:
        return all(self.get(i).done for i in ids)

    def _stage_base(self) -> bool:
        fid = self.spec.fidelity.search
        ids = self.stage_ids.get("base")
        if ids is None:
            evs = [
                self._ensure(
                    "base", fid, case=self.base_case, theta=self.spec.baseline_theta(), base=True
                ),
                *(
                    self._ensure("base", fid, case=r, reference=r)
                    for r in self.spec.reference_cases
                ),
            ]
            ids = self.stage_ids["base"] = [ev.id for ev in evs if ev is not None]
        if not self._ids_done(ids):
            return False
        evs = [self.get(i) for i in ids]
        if any(ev.score and (ev.score.steps_unexpected or ev.score.steps_missing) for ev in evs):
            self.stop_reason = "grid_mismatch"
            return False
        if any(ev.score is None or not ev.score.feasible for ev in evs):
            self.stop_reason = "base_infeasible"
            return False
        return True

    def _stage_screening(self) -> bool:
        fid = self.spec.fidelity.search
        levers = self.spec.search_levers()
        if "design" not in self.screening:
            design = alg.definitive_screening(levers)
            self.screening["design"] = design.to_dict()
            ids = []
            for point in design.points:
                ev = self._ensure("screening", fid, case=self.base_case, theta=point)
                ids.append(ev.id if ev is not None else None)
            self.screening["ids"] = ids
            if None in ids:
                self.search_stop = "budget_exhausted"
        ids = self.screening["ids"]
        evs = [self.get(i) if i else None for i in ids]
        if any(ev is not None and not ev.done for ev in evs):
            return False
        design = self.screening["design"]
        responses, feasible = [], []
        for ev in evs:
            value, ok = self.effective(ev) if ev is not None else (None, False)
            responses.append(value)
            feasible.append(ok)
        k = self.spec.algorithm.active_levers
        try:
            result = alg.screen(design["coded"], responses, feasible, names=design["names"])
        except ValueError as e:
            self.screening["error"] = str(e)
            self.active, self.fixed = [lever.name for lever in levers], {}
            self._note("screening_failed", error=str(e), fallback="search every lever")
            return True
        self.screening["result"] = result.to_dict()
        self.active = alg.active_levers(result, k)
        self.fixed = alg.inactive_settings(result, levers, k)
        return True

    def _compatible(self, theta: Mapping[str, float] | None, fixed: Mapping[str, float]) -> bool:
        if theta is None:
            return False
        return all(
            name in theta and math.isclose(theta[name], v, rel_tol=0, abs_tol=1e-9)
            for name, v in fixed.items()
        )

    def _stage_pattern(self) -> bool:
        fid = self.spec.fidelity.search
        a = self.spec.algorithm
        if not self.pattern:
            everything = self.spec.search_levers()
            names = self.active or [lever.name for lever in everything]
            fixed = dict(self.fixed) if self.active else {}
            levers = [next(lv_ for lv_ in everything if lv_.name == n) for n in names]
            ps = alg.PatternSearch(
                levers,
                seed=a.seed,
                mesh=a.mesh,
                min_mesh=a.min_mesh,
                max_mesh=a.max_mesh,
                min_improvement=a.min_improvement,
                max_unsuccessful_polls=a.max_unsuccessful_polls,
            )
            prior = [
                ev
                for ev in self.evaluations
                if ev.fidelity == fid
                and ev.done
                and ev.reference is None
                and ev.candidate is None
                and self._compatible(ev.theta, fixed)
            ]
            told: list[str] = []
            if prior:
                ps.tell([(ev.theta or {}, *self.effective(ev)) for ev in prior])
                told = [ev.id for ev in prior]
            self.pattern = {
                "active": names,
                "fixed": fixed,
                "search": ps.to_dict(),
                "points": {},
                "told": told,
            }
        ps = alg.PatternSearch.from_dict(self.pattern["search"])
        points: dict[str, dict[str, float]] = self.pattern["points"]
        told = self.pattern["told"]
        fixed = self.pattern["fixed"]
        for _ in range(100):
            fresh = [eid for eid in points if eid not in told and self.get(eid).done]
            if fresh:
                ps.tell([(points[eid], *self.effective(self.get(eid))) for eid in fresh])
                told.extend(fresh)
            if any(not self.get(eid).done for eid in points):
                self.pattern["search"] = ps.to_dict()
                return False
            ps.budget = ps.n_evaluations + max(0, self.remaining())
            wanted = ps.poll()
            if not wanted:
                self.search_stop = self.search_stop or ps.stop_reason() or "converged"
                self.pattern["search"] = ps.to_dict()
                self.pattern["incumbent"] = ps.incumbent
                self.pattern["incumbent_value"] = ps.incumbent_value
                return True
            for point in wanted:
                theta = {**fixed, **point}
                ev = self.find(fid, theta=theta)
                if ev is None:
                    ev = self._propose("pattern", fid, case=self.base_case, theta=theta)
                if ev.id in told:
                    # Already told under another rounding: tell this key directly.
                    ps.tell([(point, *self.effective(ev))])
                else:
                    points.setdefault(ev.id, point)
        raise RuntimeError("pattern search did not settle in 100 polls")

    def _stage_grid(self) -> bool:
        fid = self.spec.fidelity.search
        ids = self.stage_ids.get("grid")
        if ids is None:
            ids = []
            for point in alg.grid(self.spec.search_levers()):
                ev = self._ensure("grid", fid, case=self.base_case, theta=point)
                if ev is None:
                    self.search_stop = "budget_exhausted"
                    break
                ids.append(ev.id)
            self.stage_ids["grid"] = ids
        return self._ids_done(ids)

    def _stage_candidates(self) -> bool:
        fid = self.spec.fidelity.search
        ids = self.stage_ids.get("candidates")
        if ids is None:
            ids = []
            defaults = self.spec.lever_defaults()
            for c in self.spec.candidates:
                theta = {**defaults, **c.theta}
                ev = self._ensure(
                    "candidates", fid, case=self.base_case, theta=theta, candidate=c.name
                )
                if ev is None:
                    self.search_stop = "budget_exhausted"
                    break
                ids.append(ev.id)
            self.stage_ids["candidates"] = ids
        return self._ids_done(ids)

    def _stage_confirm(self) -> bool:
        search, confirm = self.spec.fidelity.search, self.spec.fidelity.confirm
        if confirm == search:
            return True
        ids = self.stage_ids.get("confirm")
        if ids is None:
            evs: list[Evaluation | None] = []
            if self.spec.budget.confirm_base:
                evs.append(
                    self._ensure(
                        "confirm",
                        confirm,
                        case=self.base_case,
                        theta=self.spec.baseline_theta(),
                        base=True,
                    )
                )
                evs += [
                    self._ensure("confirm", confirm, case=r, reference=r)
                    for r in self.spec.reference_cases
                ]
            for top in self.best(search, self.spec.budget.confirm):
                evs.append(
                    self._ensure(
                        "confirm",
                        confirm,
                        case=top.case,
                        theta=top.theta,
                        candidate=top.candidate,
                        source=top.id,
                    )
                )
            ids = self.stage_ids["confirm"] = [ev.id for ev in evs if ev is not None]
        return self._ids_done(ids)


# ------------------------------------------------------------------- requests
def request_resolve_settings(grid: str) -> list[dict[str, Any]]:
    """The grid's RESOLVE schedule settings as simulate-request sweeps (the backend
    takes the key from the tag)."""
    return [{"tag": s["tag"], "values": [s["value"]]} for s in mhgrid.resolve_settings(grid)]


def moved_levers(theta: Mapping[str, float], levers: Sequence[lv.LeverDef]) -> list[lv.LeverDef]:
    """Levers away from their baseline: the others leave the model as it is."""
    return [
        lever
        for lever in levers
        if lever.baseline is None
        or not math.isclose(float(theta[lever.name]), lever.baseline, rel_tol=0, abs_tol=1e-12)
    ]


def evaluation_cells(
    spec: StudySpec,
    ev: Evaluation,
    tables: lv.ModelTables,
    *,
    plans: Mapping[str, pd.DataFrame] | None = None,
    limits: Mapping[str, float] | None = None,
) -> list[dict[str, Any]]:
    """The monthly cells an evaluation adds to its case: none for the base and
    reference cases."""
    if ev.base or ev.reference is not None:
        return []
    monthly = spec.fidelity.steps("monthly")
    out: list[list[dict[str, Any]]] = []
    if ev.theta:
        moved = moved_levers(ev.theta, spec.levers)
        if moved:
            out.append(lv.cells_for(ev.theta, moved, tables, monthly, limits=limits))
    if ev.candidate:
        cand = spec.candidate(ev.candidate)
        out.append(cand.cells)
        if cand.booking_plan:
            if not plans or cand.booking_plan not in plans:
                raise ProjectError(
                    f"candidate {cand.name}: booking plan {cand.booking_plan!r} not loaded"
                )
            out.append(lv.booking_plan_cells(tables, monthly, plans[cand.booking_plan]))
    return lv.merge_cells(*out)


def build_request(
    spec: StudySpec,
    ev: Evaluation,
    project: Project,
    tables: lv.ModelTables,
    *,
    run_name: str,
    plans: Mapping[str, pd.DataFrame] | None = None,
    limits: Mapping[str, float] | None = None,
) -> dict[str, Any]:
    """The simulate request of one evaluation: its case's request, the evaluation's
    cells, and on a coarse grid the schedule settings and the remapped step tables."""
    case = project.case(ev.case)
    if case.imported:
        case = case.model_copy(update={"imported": False})
    body = project.simulate_request(case)
    body["user_specified_name"] = run_name
    cells = lv.merge_cells(
        expand_cells(body.pop("dataobject_tables", None) or []),
        evaluation_cells(spec, ev, tables, plans=plans, limits=limits),
    )
    if ev.fidelity != "monthly":
        steps = spec.fidelity.steps(ev.fidelity)
        cells = mhgrid.remap_cells(tables, steps, overrides=cells, weights=spec.fidelity.weights)
        settings = request_resolve_settings(ev.fidelity)
        body["resolve_settings"] = _merge(
            "resolve_settings", body.get("resolve_settings") or [], settings
        )
        if any("ScheduleList[1]" in s["tag"] for s in settings):
            ops = list(body.get("schedule_ops") or [])
            if not any(op.get("op") == "add" for op in ops):
                ops.append({"op": "add", "index": -1})
            body["schedule_ops"] = ops
    if cells:
        body["dataobject_tables"] = cells
    runs = estimate_runs(body)
    if runs != 1:
        raise ProjectError(f"{ev.id}: the request would start {runs} runs, not 1")
    return body


def run_name(project: Project, study: str, ev: Evaluation) -> str:
    suffix = f" a{ev.attempt}" if ev.attempt > 1 else ""
    return f"{project.name} | opt {study} {ev.id}{suffix}"


# -------------------------------------------------------------------- scoring
def score_results(
    spec: StudySpec,
    ev: Evaluation,
    *,
    status: str,
    results: pd.DataFrame | None,
    ref: Reference,
    steps: pd.DataFrame | None = None,
    members: Mapping[str, Sequence[str]] | None = None,
    log_lines: Iterable[str] | None = None,
    comparator: Score | None = None,
) -> Score:
    """Objective, licence and company values and feasibility of one finished run.

    Periods from the forecast end on (results also report the end date) are dropped
    after the volumes are computed, so the last step keeps its full length.
    Booking violations are checked against the group limits the run applied (tracked
    variables); without them they are not checked."""
    if status != COMPLETED or results is None or results.empty:
        f = feasibility.check(ev.id, status=status)
        return Score(feasible=False, reasons=f.reasons() or ["no results"], checks=f.as_dict())
    res = results.assign(
        case_name=ev.id, timestamp=pd.to_datetime(results["timestamp"]).dt.normalize()
    )
    within = res[res["timestamp"] < mhgrid.FORECAST_END]
    expected = spec.fidelity.steps(ev.fidelity)
    predicted = {pd.Timestamp(t) for t in expected}
    unexpected = sorted(t for t in set(within["timestamp"]) if pd.Timestamp(t) not in predicted)

    # Volumes from every row: the end-date row gives the last step its length.
    volumes = period_volumes(res)
    valued = value_volumes(volumes[volumes["period"] < mhgrid.FORECAST_END], ref)
    by_period = valued.groupby("period")[spec.objective].sum()
    ledger = ledgers.participant_ledger(valued, ref)
    licence = ledgers.licence_values(ledger)
    company = ledgers.company_values(ledger, ref.shares)

    notes: list[str] = []
    violations = None
    booked = bk.booked_from_steps(steps) if steps is not None and not steps.empty else None
    if booked is not None and members:
        booked = booked[booked["group"].isin(list(members))]
    if booked is None or booked.empty or not members:
        notes.append("booking violations not checked: no tracked group limits")
    else:
        report = bk.BookingReport(
            within,
            booked.assign(case_name=ev.id),
            members,
            ref.entities,
            ref.shares,
            baseline=ev.id,
        )
        violations = report.violations()
    if log_lines is None:
        notes.append("solver logs not checked")
    gain = None
    if comparator is not None and comparator.by_period:
        base = pd.Series(comparator.by_period)
        base.index = pd.to_datetime(base.index)
        gain = by_period.sub(base, fill_value=0.0)
    f = feasibility.check(
        ev.id,
        status=status,
        results=within,
        expected_steps=expected,
        violations=violations,
        log_lines=log_lines,
        gain_by_period=gain,
        tol=spec.constraints.violation_tol,
    )
    reasons = f.reasons()
    if unexpected:
        reasons.append(
            f"{len(unexpected)} step(s) the grid doesn't predict (first "
            f"{pd.Timestamp(unexpected[0]).date()}): remapped tables may be misaligned"
        )

    def row(frame: pd.DataFrame) -> dict[str, float]:
        if ev.id not in frame.index:
            return {}
        return {str(k): float(v) for k, v in frame.loc[ev.id].items()}

    return Score(
        feasible=f.feasible and not unexpected,
        objective=float(by_period.sum()),
        reasons=reasons,
        licence_values=row(licence),
        company_values=row(company),
        by_period={pd.Timestamp(k).date().isoformat(): float(v) for k, v in by_period.items()},
        window_share=f.window_share,
        window_flag=f.window_flag,
        steps_missing=f.missing,
        steps_unexpected=len(unexpected),
        checks=f.as_dict(),
        notes=notes,
    )


__all__ = [
    "CANCELLED",
    "COMPLETED",
    "DEFAULT_STAGES",
    "FAILED",
    "RETRYABLE_FAILURES",
    "SCHEMES",
    "AlgorithmSettings",
    "Candidate",
    "Constraints",
    "Evaluation",
    "Fidelity",
    "Score",
    "StudyBudget",
    "StudySpec",
    "StudyState",
    "build_request",
    "evaluation_cells",
    "moved_levers",
    "request_resolve_settings",
    "run_name",
    "score_results",
    "theta_key",
]
