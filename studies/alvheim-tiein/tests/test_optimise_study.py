from __future__ import annotations

import datetime as dt
import hashlib
import json
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

import pandas as pd
import pytest
import yaml
from pydantic import ValidationError

from alvheim_tiein import mhgrid
from alvheim_tiein.economics import Reference
from alvheim_tiein.levers import ModelTables
from alvheim_tiein.optimise import algorithms as alg
from alvheim_tiein.optimise import runner as rn
from alvheim_tiein.optimise import study as st
from alvheim_tiein.project import Project, ProjectError, RunLog, Workspace, estimate_runs

from .test_project import FL1, FL2, PROJECT, write_project

T0 = dt.datetime(2026, 5, 4, 8, 0, tzinfo=dt.UTC)
MONTHS = list(pd.date_range("2026-07-01", periods=174, freq="MS"))
SWITCH = pd.Timestamp("2027-10-01")
LEVERS: list[dict[str, Any]] = [
    {"name": "alpha", "kind": "weights", "lower": 0, "upper": 1, "baseline": 1},
    {"name": "beta", "kind": "release", "lower": 0, "upper": 1, "baseline": 0, "groups": ["G"]},
    {
        "name": "gamma",
        "kind": "liquid_scale",
        "lower": 0.8,
        "upper": 1.5,
        "baseline": 1,
        "groups": ["G"],
    },
]


def month(label: str | pd.Timestamp) -> str:
    return pd.Timestamp(label).strftime("%d %B %Y 00:00:00.0000000")


def model() -> ModelTables:
    """Step tables like Alvheim's (see test_mhgrid) plus weights and capacities."""
    tables: list[dict[str, Any]] = [
        {"object_alias": "Uptime_base", "table_name": "Date", "values": [month(m) for m in MONTHS]},
        {
            "object_alias": "Uptime_base",
            "table_name": "Uptime",
            "values": [0.9 + 0.0005 * m for m in range(len(MONTHS))],
        },
        {
            "object_alias": "Bookings_oil",
            "table_name": "Month",
            "values": [month(m) for m in MONTHS[:24]],
        },
        {"object_alias": "Bookings_oil", "table_name": "G", "values": [100.0] * 24},
        {
            "object_alias": "Future_Bookings_Liquid",
            "table_name": "Month",
            "values": [month(SWITCH), month("2028-10-01")],
        },
        {
            "object_alias": "Future_Bookings_Liquid",
            "table_name": "G",
            "values": [1000.0 + m for m in range(60)],
        },
        {"object_alias": "Weightings", "table_name": "Well", "values": ["H1", "S1"]},
        {"object_alias": "Weightings", "table_name": "Weight", "values": [3.0, 1.0]},
        {"object_alias": "Capacities", "table_name": "TotalOil_Capacity", "values": [1000.0]},
        {"object_alias": "Capacities", "table_name": "Maximumwaterrate", "values": [500.0]},
        {"object_alias": "Capacities", "table_name": "TotalGas_Capacity", "values": [4300.0]},
    ]
    return ModelTables({"tables": tables})


def spec(**overrides: Any) -> st.StudySpec:
    data: dict[str, Any] = {
        "name": "outer-1",
        "scheme": "outer",
        "base_case": "tie_in",
        "reference_cases": ["baseline"],
        "levers": LEVERS,
        "algorithm": {"active_levers": 2},
        "budget": {"max_evaluations": 30},
    }
    data.update(overrides)
    return st.StudySpec.model_validate(data)


def start(s: st.StudySpec, case_tasks: Mapping[str, str] | None = None) -> st.StudyState:
    project = Project.model_validate(PROJECT)
    return st.StudyState.start(s, slug="fl", project=project, case_tasks=case_tasks, now=T0)


# ---------------------------------------------------------- simulated Autogration
Scorer = Callable[[st.Evaluation], st.Score]


def outer_value(theta: Mapping[str, float]) -> float:
    """Strong in alpha (lower is better) and beta (higher), weak in gamma."""
    return 1000.0 + 60.0 * theta["beta"] - 40.0 * theta["alpha"] + 2.0 * theta["gamma"]


def outer_score(ev: st.Evaluation) -> st.Score:
    if ev.reference is not None:
        return st.Score(feasible=True, objective=900.0)
    return st.Score(feasible=True, objective=outer_value(ev.theta or {}))


def submit(state: st.StudyState, *, now: dt.datetime = T0, limit: int | None = None) -> None:
    for ev in state.plan(now)[:limit]:
        state.record_submission(ev.id, {"assumption_group_id": f"g-{ev.id}-{ev.attempt}"}, now=now)


def complete(state: st.StudyState, *, now: dt.datetime = T0) -> None:
    for ev in state.in_flight():
        task = {"task_id": f"t-{ev.id}-{ev.attempt}", "status": st.COMPLETED}
        state.record_status(ev.id, task, now=now)


def score_all(state: st.StudyState, score: Scorer) -> None:
    for ev in state.evaluations:
        if ev.status == "completed":
            state.record_score(ev.id, score(ev))


def wave(
    state: st.StudyState, score: Scorer, *, now: dt.datetime = T0, limit: int | None = None
) -> None:
    """Submit what the study proposes, finish and score every run."""
    submit(state, now=now, limit=limit)
    complete(state, now=now)
    score_all(state, score)


def drive(state: st.StudyState, score: Scorer, *, now: dt.datetime = T0) -> None:
    for _ in range(100):
        if state.finished:
            return
        wave(state, score, now=now)
    raise AssertionError("the study did not finish")


def reload(state: st.StudyState) -> st.StudyState:
    return st.StudyState.model_validate_json(state.model_dump_json())


# ------------------------------------------------------------------- the stages
def test_outer_study_screens_searches_the_active_levers_and_confirms() -> None:
    s = start(spec())
    drive(s, outer_score)
    assert s.stop_reason == "completed"
    done = [e["stage"] for e in s.log if e["event"] == "stage_done"]
    assert done == ["base", "screening", "pattern", "confirm"]
    assert set(s.active) == {"alpha", "beta"}
    assert s.fixed == {"gamma": 1.5}

    search = [ev for ev in s.evaluations if ev.fidelity == "mh" and ev.reference is None]
    keys = [st.theta_key(ev.theta) for ev in search]
    assert len(keys) == len(set(keys)), "a point was run twice"
    assert s.committed() <= 30

    confirm = [ev for ev in s.evaluations if ev.stage == "confirm"]
    assert {ev.fidelity for ev in confirm} == {"monthly"}
    assert [ev.label for ev in confirm[:2]] == ["base", "ref:baseline"]
    assert [ev.source for ev in confirm[2:]] == [ev.id for ev in s.best("mh", 3)]

    out = s.outcome()
    assert out["fidelity"] == "monthly"
    assert out["theta"] == {"alpha": 0.0, "beta": 1.0, "gamma": 1.5}
    assert out["gain"] == pytest.approx(outer_value(out["theta"]) - 962.0)


def test_a_study_resumes_from_json_exactly() -> None:
    whole = start(spec())
    drive(whole, outer_score)

    s = start(spec())
    for _ in range(100):
        if s.finished:
            break
        submit(s, limit=4)
        s = reload(s)
        complete(s)
        s = reload(s)
        score_all(s, outer_score)
        s = reload(s)
    assert s.finished
    pd.testing.assert_frame_equal(s.table(), whole.table())
    assert s.outcome() == whole.outcome()


def test_infrastructure_failures_are_retried_and_model_failures_are_not() -> None:
    s = start(spec())
    base, ref = s.plan(T0)
    s.record_submission(base.id, {"assumption_group_id": "g1"}, now=T0)
    s.record_status(
        base.id,
        {"task_id": "t1", "status": st.FAILED},
        failure={"category": "job_failed", "message": "node lost"},
        now=T0,
    )
    assert (base.status, base.attempt, base.task_id) == ("proposed", 2, None)
    assert base.history[0]["task_id"] == "t1" and "job_failed" in base.history[0]["failure"]
    assert s.committed() == 3  # the base twice, the reference once
    project = Project.model_validate(PROJECT)
    assert st.run_name(project, "outer-1", base) == "Froskelaar tie-in | opt outer-1 e001 a2"

    s.record_submission(base.id, {"assumption_group_id": "g2"}, now=T0)
    s.record_status(
        base.id,
        {"task_id": "t2", "status": st.FAILED},
        failure={"category": "execution_error", "message": "GAP did not solve"},
        now=T0,
    )
    assert base.status == "scored" and base.score is not None and not base.score.feasible
    assert "execution_error" in base.score.reasons[0]

    s.record_submission(ref.id, {"assumption_group_id": "g3"}, now=T0)
    complete(s)
    score_all(s, outer_score)
    assert s.plan(T0) == []
    assert s.finished and s.stop_reason == "base_infeasible"


def test_runs_that_found_no_licence_do_not_use_up_attempts() -> None:
    s = start(spec())
    base, _ = s.plan(T0)
    no_licence = {"category": "job_failed", "message": "22: No OpenServer license available"}
    lost = {"category": "job_failed", "message": "node lost"}
    for n, failure in enumerate([no_licence] * 3 + [lost], start=1):
        s.record_submission(base.id, {"assumption_group_id": f"g{n}"}, now=T0)
        s.record_status(base.id, {"task_id": f"t{n}", "status": st.FAILED}, failure=failure)
        assert (base.status, base.attempt) == ("proposed", n + 1)
    s.record_submission(base.id, {"assumption_group_id": "g5"}, now=T0)
    s.record_status(base.id, {"task_id": "t5", "status": st.FAILED}, failure=lost, now=T0)
    assert base.status == "scored" and base.score is not None
    assert "node lost" in base.score.reasons[0]
    assert base.failed_runs == {f"{p}{n}" for p in "tg" for n in range(1, 5)}


def test_a_revived_run_is_waited_for_and_confirmed_if_it_ranks() -> None:
    s = start(
        settle_spec(
            fidelity={"search": "mh", "confirm": "monthly"}, constraints={}, budget={"confirm": 1}
        )
    )
    wave(s, by_label)  # the base and the reference case on MH
    hub, fair = s.plan(T0)
    for ev in (hub, fair):
        s.record_submission(ev.id, {"assumption_group_id": f"g-{ev.id}"}, now=T0)
    crashed = {"category": "execution_error", "message": "OpenServer stopped"}
    s.record_status(hub.id, {"task_id": "t-hub", "status": st.FAILED}, failure=crashed)
    assert hub.status == "scored" and hub.score is not None and not hub.score.feasible
    complete(s)
    score_all(s, by_label)
    submit(s)
    confirm = list(s.stage_ids["confirm"])
    assert [s.get(i).label for i in confirm] == ["base", "ref:baseline", "fair"]

    with pytest.raises(ValueError, match="no failed run"):
        s.revive(fair.id)
    s.revive(hub.id, T0)
    assert (hub.status, hub.attempt, hub.score, hub.spent) == ("proposed", 2, None, 2)
    assert hub.failed_runs == {"t-hub", f"g-{hub.id}"}
    complete(s)
    score_all(s, by_label)
    assert s.plan(T0) == [hub]  # the confirmed runs are in: confirm waits for the hub
    wave(s, by_label)
    late = s.plan(T0)
    assert [(ev.label, ev.fidelity, ev.source) for ev in late] == [("hub", "monthly", hub.id)]
    assert s.stage_ids["confirm"] == [*confirm, late[0].id]
    wave(s, by_label)
    assert s.plan(T0) == [] and s.finished
    assert s.outcome()["label"] == "hub" and s.outcome()["fidelity"] == "monthly"
    with pytest.raises(ValueError, match="has finished"):
        s.revive(hub.id)


def test_specs_are_checked_before_anything_runs() -> None:
    with pytest.raises(ValidationError, match="need at least"):
        spec(budget={"max_evaluations": 5})
    with pytest.raises(ValidationError, match="not also a reference"):
        spec(reference_cases=["tie_in"])
    with pytest.raises(ValidationError, match="no_loss_against"):
        spec(constraints={"no_loss": "*", "no_loss_against": "other"})
    with pytest.raises(ValidationError, match="outside its bounds"):
        spec(
            scheme="total_then_settle",
            candidates=[{"name": "far", "theta": {"alpha": 2}}],
        )
    assert spec().required_runs() == 2 + alg.screening_runs(3) + 2 * 2


def test_the_wall_clock_skips_the_search_and_confirms_what_was_found() -> None:
    s = start(spec(budget={"max_evaluations": 30, "max_hours": 1}))
    wave(s, outer_score)  # the base and the reference case
    wave(s, outer_score, limit=3)  # three of the screening runs
    screening = alg.screening_runs(3)
    assert s.stage == "screening" and len(s.proposed()) == screening - 3

    later = T0 + dt.timedelta(hours=2)
    proposed = s.plan(later)
    assert s.search_stop == "wall_clock" and s.stage == "confirm"
    skipped = [ev for ev in s.evaluations if ev.status == "skipped"]
    assert len(skipped) == screening - 3 and {ev.failure for ev in skipped} == {"wall_clock"}
    assert all(ev.spent == 0 for ev in skipped)
    assert s.committed() == 2 + 3
    assert [ev.stage for ev in proposed] == ["confirm"] * 5  # base, reference, best three

    drive(s, outer_score, now=later)
    assert s.stop_reason == "completed"


def test_cancel_returns_the_runs_to_stop_and_skips_the_rest() -> None:
    s = start(spec())
    base, ref = s.plan(T0)
    s.record_submission(base.id, {"assumption_group_id": "g1"}, now=T0)
    assert s.cancel(T0) == [{"id": base.id, "task_id": None, "group_id": "g1"}]
    assert base.status == ref.status == "skipped"
    assert (base.spent, ref.spent) == (1, 0)
    assert s.finished and s.stop_reason == "cancelled" and s.plan(T0) == []


# ------------------------------------------------- no loss, reuse, candidates
VALUES: dict[str, tuple[float, dict[str, float]]] = {
    "base": (150.0, {"HOST": 100.0, "SAT": 50.0}),
    "ref:baseline": (140.0, {"HOST": 90.0, "SAT": 60.0}),
    "hub": (200.0, {"HOST": 140.0, "SAT": 55.0, "NEW": 5.0}),
    "fair": (180.0, {"HOST": 110.0, "SAT": 65.0, "NEW": 5.0}),
}


def by_label(ev: st.Evaluation) -> st.Score:
    value, licences = VALUES[ev.label]
    return st.Score(feasible=True, objective=value, licence_values=licences)


def settle_spec(**overrides: Any) -> st.StudySpec:
    data: dict[str, Any] = {
        "name": "settle",
        "scheme": "total_then_settle",
        "base_case": "tie_in",
        "reference_cases": ["baseline"],
        "fidelity": {"search": "monthly", "confirm": "monthly"},
        "candidates": [{"name": "hub"}, {"name": "fair"}],
        "constraints": {"no_loss": "*", "no_loss_against": "baseline"},
    }
    data.update(overrides)
    return st.StudySpec.model_validate(data)


def test_no_loss_against_a_reference_case_with_reused_case_runs() -> None:
    s = start(settle_spec(), {"tie_in": "t-base", "baseline": "t-ref", "sweep": "t-x"})
    assert s.case_tasks == {"tie_in": "t-base", "baseline": "t-ref"}
    assert s.plan(T0) == []  # both reused: nothing to submit, only to score
    drive(s, by_label)
    assert s.stop_reason == "completed"

    base = s.baseline_of("monthly")
    assert base is not None and base.reuse_task == base.task_id == "t-base"
    assert base.spent == 0 and s.committed() == 2
    hub = s.find("monthly", candidate="hub")
    assert hub is not None and s.no_loss_shortfalls(hub) == {"SAT": 5.0}
    assert [ev.label for ev in s.best("monthly", 2)] == ["fair"]
    assert s.outcome()["label"] == "fair" and s.outcome()["gain"] == 30.0
    table = s.table().set_index("what")
    assert not table.loc["hub", "feasible"] and "SAT loses 5" in table.loc["hub", "reasons"]
    assert "confirm" not in s.stage_ids  # one grid: nothing to confirm

    fresh = start(settle_spec(reuse_case_runs=False), {"tie_in": "t-base"})
    assert fresh.case_tasks == {}
    assert [ev.label for ev in fresh.plan(T0)] == ["base", "ref:baseline"]


# ------------------------------------------------------------------- requests
def point(fidelity: str, **theta: float) -> st.Evaluation:
    return st.Evaluation(
        id="e099",
        stage="pattern",
        fidelity=fidelity,
        case="tie_in",
        theta={"alpha": 1.0, "beta": 0.0, "gamma": 1.0, **theta},
        proposed_at="2026-05-04T08:00:00+00:00",
    )


def cells(body: dict[str, Any]) -> dict[tuple[str, str, int], float]:
    return {
        (c["object_alias"], c["table_name"], c["index"]): c["values"][0]
        for c in body.get("dataobject_tables") or []
    }


def test_mh_requests_put_the_case_on_the_grid_and_write_only_moved_levers() -> None:
    project = Project.model_validate(PROJECT)
    s = start(spec())
    base, _ = s.plan(T0)
    body = st.build_request(s.spec, base, project, model(), run_name="x")
    assert body["user_specified_name"] == "x" and estimate_runs(body) == 1
    settings = body["resolve_settings"]
    assert all(set(r) == {"tag", "values"} and len(r["values"]) == 1 for r in settings)
    assert "RESOLVE.ScheduleList[1].InitialTimestep" in {r["tag"] for r in settings}
    assert body["schedule_ops"] == [{"op": "add", "index": -1}]
    aliases = {alias for alias, _, _ in cells(body)}
    assert "Uptime_base" in aliases and "Weightings" not in aliases

    moved = st.build_request(s.spec, point("mh", alpha=0.5), project, model(), run_name="y")
    assert cells(moved)[("Weightings", "Weight", 0)] == pytest.approx(2.0)  # 1 + 0.5 (3 - 1)
    assert estimate_runs(moved) == 1

    monthly = st.build_request(s.spec, point("monthly", alpha=0.5), project, model(), run_name="z")
    assert not monthly.get("resolve_settings") and "schedule_ops" not in monthly
    assert {alias for alias, _, _ in cells(monthly)} == {"Weightings"}


# -------------------------------------------------------------------- scoring
@pytest.fixture
def ref26(reference: Reference) -> Reference:
    """The test reference with prices from the forecast start."""
    prices = pd.DataFrame(
        {
            "date": pd.to_datetime(["2026-07-01"]),
            "oil_price_per_bbl": [100.0],
            "gas_price_per_sm3": [0.0],
        }
    )
    return Reference(reference.entities, reference.shares, prices, reference.economics)


def results(steps: list[pd.Timestamp], rates: Mapping[str, float]) -> pd.DataFrame:
    """Oil rates per well at each step and at the forecast end, as runs report them."""
    stamps = [*steps, mhgrid.FORECAST_END]
    return pd.DataFrame(
        [
            {
                "module": "GAP",
                "system": "PROD",
                "identifier": well,
                "identifier_type": "WELL",
                "timestamp": t,
                "run_number": 1,
                "property_name": "AvgOilRate",
                "value": rate,
                "unit": "Sm3/day",
                "case_name": "x",
            }
            for well, rate in rates.items()
            for t in stamps
        ]
    )


def test_scores_count_every_day_to_the_forecast_end_and_flag_grid_mismatches(
    ref26: Reference,
) -> None:
    s = spec(objective="oil_sm3")
    ev = point("mh")
    steps = s.fidelity.steps("mh")
    score = st.score_results(
        s, ev, status=st.COMPLETED, results=results(steps, {"H1": 1.0, "S1": 2.0}), ref=ref26
    )
    days = (mhgrid.FORECAST_END - mhgrid.FORECAST_START).days
    assert score.feasible and score.objective == pytest.approx(3.0 * days)
    assert len(score.by_period) == len(steps) and score.steps_unexpected == 0
    assert {"HOST", "SAT"} <= set(score.licence_values) and score.company_values
    assert score.notes == [
        "booking violations not checked: no tracked group limits",
        "solver logs not checked",
    ]

    odd = results([*steps[:3], pd.Timestamp("2026-09-15"), *steps[3:]], {"H1": 1.0})
    bad = st.score_results(s, ev, status=st.COMPLETED, results=odd, ref=ref26)
    assert not bad.feasible and bad.steps_unexpected == 1
    assert "doesn't predict" in bad.reasons[-1]

    short = st.score_results(
        s, ev, status=st.COMPLETED, results=results(steps[1:], {"H1": 1.0}), ref=ref26
    )
    assert not short.feasible and short.steps_missing == 1

    failed = st.score_results(s, ev, status=st.FAILED, results=None, ref=ref26)
    assert not failed.feasible and failed.reasons == ["status Failed"]


def tracked_bookings(
    times: list[pd.Timestamp], oil: float = 100.0, gas: float = 10.0
) -> pd.DataFrame:
    """Group G's applied limits at each step, as tracked variables report them (gas in
    1000 Sm3/d)."""
    return pd.DataFrame(
        [
            {"time": t, "variable": f"resolve.module[0].MOD[{{PROD}}].GROUP[{{G}}].{v}", "value": x}
            for t in times
            for v, x in (("MaxQoil", oil), ("MaxQTotGas", gas))
        ]
    )


def test_scores_record_booked_capacity_from_the_runs_own_limits(ref26: Reference) -> None:
    s = spec(objective="oil_sm3")
    ev = point("mh")
    grid = s.fidelity.steps("mh")
    res = results(grid, {"H1": 1.0, "S1": 3.0})
    days = (mhgrid.FORECAST_END - mhgrid.FORECAST_START).days
    members = {"G": ["H1", "S1"]}
    limits = {"oil": 200.0, "gas": 20_000.0, "water": 50.0, "liquid": 250.0}
    score = st.score_results(
        s,
        ev,
        status=st.COMPLETED,
        results=res,
        ref=ref26,
        steps=tracked_bookings(grid),
        members=members,
        limits=limits,
    )
    # G books 100 oil + 10 000 gas = 110 Sm3 oe/d, split 1:3 by production; the host
    # licence holds the unbooked 100 oil + 10 000 gas (no discounting in ref26).
    r = score.booked_capacity
    assert r["HOST"] == pytest.approx(110 * 0.25 * days)
    assert r["SAT"] == pytest.approx(110 * 0.75 * days)
    assert r["203"] == pytest.approx(110 * days)
    assert not any("booked capacity" in n for n in score.notes)

    bare = st.score_results(
        s,
        ev,
        status=st.COMPLETED,
        results=res,
        ref=ref26,
        steps=tracked_bookings(grid),
        members=members,
    )
    assert set(bare.booked_capacity) == {"HOST", "SAT"}
    assert "booked capacity without the host's residual: no FPSO limits" in bare.notes


def test_violations_the_base_has_too_are_noted_not_held_against_a_run(ref26: Reference) -> None:
    s = spec(objective="oil_sm3")
    grid = s.fidelity.steps("mh")
    n = len(grid)
    members = {"G": ["H1", "S1"]}
    applied = tracked_bookings(grid, oil=3.0, gas=1e6)

    def score(
        ev: st.Evaluation, s1: float, comparator: st.Score | None = None, sp: st.StudySpec = s
    ) -> st.Score:
        res = results(grid, {"H1": 1.0, "S1": s1})
        res = pd.concat([res, res.assign(property_name="OilRate")], ignore_index=True)
        return st.score_results(
            sp,
            ev,
            status=st.COMPLETED,
            results=res,
            ref=ref26,
            steps=applied,
            members=members,
            comparator=comparator,
        )

    # G produces 4 against an oil limit of 3 at every step, as GAP does in the model (M4).
    base_ev = point("mh").model_copy(update={"id": "e001", "base": True})
    base = score(base_ev, 3.0)
    assert base.feasible and base.checks["inherited_violations"] == n
    assert base.violation_steps is not None and len(base.violation_steps) == n
    assert base.violation_steps[0]["group"] == "G" and base.violation_steps[0]["phase"] == "oil"
    assert any("in the model as given" in note for note in base.notes)

    same = score(point("mh"), 3.05, comparator=base)  # 4.05 / 3: within 2 points of the base
    assert same.feasible and not same.reasons
    assert same.checks["inherited_violations"] == n and same.checks["violations"] == 0
    assert any("where the base is too" in note for note in same.notes)

    worse = score(point("mh"), 3.5, comparator=base)
    assert not worse.feasible and worse.checks["violations"] == n
    assert worse.checks["inherited_violations"] == 0

    unrecorded = score(
        point("mh"), 3.0, comparator=base.model_copy(update={"violation_steps": None})
    )
    assert not unrecorded.feasible and any("rescore" in note for note in unrecorded.notes)

    strict = spec(objective="oil_sm3", constraints={"inherit_violations": False})
    assert not score(base_ev, 3.0, sp=strict).feasible
    clean = score(point("mh"), 1.0, comparator=base)
    assert clean.feasible and clean.violation_steps == []


def test_fields_added_later_leave_started_studies_digests_alone() -> None:
    s = spec()
    old = s.model_dump(mode="json")
    del old["constraints"]["inherit_violations"]
    text = json.dumps(old, sort_keys=True, default=str)
    assert s.digest() == hashlib.sha256(text.encode()).hexdigest()[:16]
    assert spec(constraints={"inherit_violations": False}).digest() != s.digest()


def scored(eid: str, values: Mapping[str, float], capacity: Mapping[str, float]) -> st.Evaluation:
    return point("monthly").model_copy(
        update={
            "id": eid,
            "score": st.Score(
                feasible=True,
                objective=sum(values.values()),
                licence_values=dict(values),
                booked_capacity=dict(capacity),
            ),
        }
    )


def test_proportional_settlement_uses_the_bookings_in_force_or_the_plans_own() -> None:
    state = start(st.StudySpec.model_validate(STUDY))
    against = scored("e001", {"HOST": 100.0, "SAT": 100.0, "NEW": 0.0}, {"HOST": 3.0, "SAT": 1.0})
    plan = scored("e009", {"HOST": 110.0, "SAT": 90.0, "NEW": 30.0}, {"HOST": 1.0, "NEW": 1.0})

    def rule(table: pd.DataFrame, name: str) -> pd.DataFrame:
        return table[table["rule"] == name].set_index("license")

    # A policy scheme: the surplus G = 30 split 3:1 on the comparator's bookings.
    t = rn.settlement_table(state, plan, against, "base")
    assert list(dict.fromkeys(t["rule"])) == list(rn.SETTLEMENT_RULES)
    p = rule(t, "proportional")
    assert p["award"].to_dict() == pytest.approx({"HOST": 22.5, "NEW": 0.0, "SAT": 7.5})
    assert p["transfer"].to_dict() == pytest.approx({"HOST": 12.5, "NEW": -30.0, "SAT": 17.5})
    assert set(p["note"]) == {"basis: booked capacity of e001"}

    # A restructure changes the basis: the plan's own bookings.
    restructure = state.model_copy(
        update={"spec": state.spec.model_copy(update={"scheme": "restructure_bookings"})}
    )
    p = rule(rn.settlement_table(restructure, plan, against, "base"), "proportional")
    assert p["award"].to_dict() == pytest.approx({"HOST": 15.0, "NEW": 15.0, "SAT": 0.0})
    assert p["transfer"].sum() == pytest.approx(0.0)

    # Scored without tracked limits: the rule says why, the others still settle.
    bare = scored("e002", {"HOST": 100.0, "SAT": 100.0, "NEW": 0.0}, {})
    t = rn.settlement_table(state, plan, bare, "base")
    assert rule(t, "proportional")["note"].str.contains("no booked capacity for e002").all()
    assert rule(t, "minimal")["transfer"].sum() == pytest.approx(0.0)


# ----------------------------------------------------------- runner, end to end
def capacity(value: float) -> dict[str, Any]:
    return {
        "object_alias": "Capacities",
        "table_name": "TotalOil_Capacity",
        "index": 0,
        "values": [value],
    }


STUDY: dict[str, Any] = {
    "name": "settle",
    "scheme": "total_then_settle",
    "base_case": "tie_in",
    "reference_cases": ["baseline"],
    "candidates": [
        {"name": "push", "cells": [capacity(2000)]},
        {"name": "nudge", "cells": [capacity(1000)]},
    ],
    "budget": {"wave_size": 2, "confirm": 1},
}


def fake_results(body: Mapping[str, Any]) -> pd.DataFrame:
    """A run's results from its request: the grid, Froskelaar on or off, and a higher
    oil capacity moving oil from the satellite to the host."""
    settings = body.get("resolve_settings") or []
    mh = any("ScheduleList[1]" in r["tag"] for r in settings)
    fl_off = any(
        a.get("operation") == "schedule"
        and a["path"] in (FL1, FL2)
        and a["schedule"]["event_type"] == "WELL_OFF"
        for a in body.get("assumptions") or []
    )
    rates = {"H1": 10.0, "S1": 5.0, "N1": 0.0 if fl_off else 4.0}
    cap = cells(dict(body)).get(("Capacities", "TotalOil_Capacity", 0))
    if cap is not None:
        rates["H1"] += cap / 500.0
        rates["S1"] -= 1.0
    return results(mhgrid.predict_steps("mh" if mh else "monthly"), rates)


class FakeBackend:
    def __init__(self) -> None:
        self.active = 0
        self.bodies: dict[str, dict[str, Any]] = {}
        self.status: dict[str, str] = {}
        self.results: dict[str, pd.DataFrame] = {}
        self.failures: dict[str, dict[str, str]] = {}
        self.cancelled: list[str] = []

    def finish_all(self) -> None:
        for task, status in self.status.items():
            if status == "Running":
                self.status[task] = st.COMPLETED

    def active_runs(self) -> int:
        return self.active

    def simulate(self, model_id: str, body: Mapping[str, Any]) -> dict[str, Any]:
        n = len(self.bodies) + 1
        self.bodies[f"t{n}"] = dict(body)
        self.status[f"t{n}"] = "Running"
        self.results[f"t{n}"] = fake_results(body)
        return {"assumption_group_id": f"g{n}", "case_count": estimate_runs(body)}

    def group_tasks(self, group_id: str) -> list[dict[str, Any]]:
        task = "t" + group_id[1:]
        return [{"task_id": task, "status": self.status[task]}]

    def task(self, task_id: str) -> dict[str, Any]:
        failure = self.failures.get(task_id)
        return {"task_id": task_id, "status": self.status[task_id], "failure": failure}

    def download_results(self, task_id: str, dest_dir: Path) -> Path:
        dest_dir.mkdir(parents=True, exist_ok=True)
        path = dest_dir / f"{task_id}.parquet"
        self.results[task_id].to_parquet(path)
        return path

    def steps(self, task_id: str) -> pd.DataFrame:
        times = sorted(set(pd.to_datetime(self.results[task_id]["timestamp"])))
        return tracked_bookings(times)

    def log_lines(self, task_id: str) -> list[str]:
        return []

    def cancel(self, task_id: str) -> None:
        self.cancelled.append(task_id)


def test_study_runs_end_to_end_against_a_fake_autogration(tmp_path: Path, ref26: Reference) -> None:
    write_project(tmp_path)
    project, ppaths, log = Workspace(tmp_path).load("fl")
    backend = FakeBackend()
    tie_in = project.simulate_request(project.case("tie_in"))
    log.record_submission(
        "tie_in", "m-1", tie_in, {"assumption_group_id": "g0", "case_count": 1}, 1
    )
    log.record_tasks("tie_in", [{"task_id": "t-tie", "assumption_case": 1, "status": "Completed"}])
    log.save()
    backend.status["t-tie"] = st.COMPLETED
    backend.results["t-tie"] = fake_results(tie_in)

    paths = rn.StudyPaths(ppaths, "settle")
    paths.root.mkdir(parents=True)
    paths.spec.write_text(yaml.safe_dump({**STUDY, "description": "v1"}), encoding="utf-8")
    ctx = rn.StudyContext(
        slug="fl",
        project=project,
        project_paths=ppaths,
        paths=paths,
        tables=model(),
        members={"G": ["H1", "S1"]},
        ref=ref26,
        ref_digest="r1",
    )
    study = rn.Study.open(ctx, now=T0)
    assert study.state.case_tasks == {"tie_in": "t-tie"}

    backend.active = 40
    r = study.tick(backend, now=T0)
    assert r.submitted == [] and r.waiting == ["e001", "e002"]
    assert r.blocked is not None and "40 of your runs" in r.blocked

    # Nothing submitted yet: the study follows edits to study.yaml.
    paths.spec.write_text(yaml.safe_dump({**STUDY, "description": "v2"}), encoding="utf-8")
    study = rn.Study.open(ctx, now=T0)
    assert study.spec.description == "v2"

    backend.active = 0
    dry = study.tick(backend, now=T0, dry_run=True)
    assert [eid for eid, _ in dry.requests] == ["e001", "e002"] and not backend.bodies
    r = study.tick(backend, now=T0)
    assert r.submitted == ["e001", "e002"]
    saved = rn.load_state(paths.state)
    assert saved is not None and saved.evaluations[0].status == "submitted"

    for _ in range(10):
        backend.finish_all()
        r = study.tick(backend, now=T0)
        if r.finished:
            break
    assert r.stop_reason == "completed"

    s = study.state
    assert len(backend.bodies) == 6  # the monthly base run is reused
    assert s.get("e005").reuse_task == "t-tie"
    names = [b["user_specified_name"] for b in backend.bodies.values()]
    assert names[0] == "Froskelaar tie-in | opt settle e001"
    out = s.outcome()
    assert out["label"] == "push" and out["fidelity"] == "monthly" and out["gain"] > 0

    files = rn.write_report(s, paths.report)
    assert set(files) == {
        "evaluations.csv",
        "licence_values.csv",
        "company_values.csv",
        "objective_by_period.csv",
        "settlement.csv",
        "summary.json",
    }
    settle = pd.read_csv(files["settlement.csv"])
    assert set(settle["against"]) == {"base", "ref:baseline"}
    for _, g in settle.groupby(["against", "rule"]):
        assert g["transfer"].sum() == pytest.approx(0.0, abs=1e-3)
    minimal = settle[(settle["against"] == "base") & (settle["rule"] == "minimal")]
    sat = minimal.set_index("license").loc["SAT"]
    assert sat["delta"] < 0 and sat["transfer"] == pytest.approx(-sat["delta"])
    proportional = settle[(settle["against"] == "base") & (settle["rule"] == "proportional")]
    assert proportional["award"].notna().all() and (proportional["award"] >= 0).all()
    assert proportional["note"].str.startswith("basis: booked capacity of").all()
    assert proportional.set_index("license").loc["HOST", "basis"] > 0

    # With the switch states, Froskelaar off -> on is the tie-in: no surplus split.
    tied = rn.write_report(s, paths.report, {"tie_in": "on", "baseline": "off"})
    tied_rows = pd.read_csv(tied["settlement.csv"])
    ref_rows = tied_rows[tied_rows["against"] == "ref:baseline"]
    assert set(ref_rows["rule"]) == {"tie-in"} and ref_rows["transfer"].isna().all()
    assert ref_rows["note"].str.contains("tie-in agreement").all()
    base_rows = tied_rows[tied_rows["against"] == "base"]
    assert set(base_rows["rule"]) == set(rn.SETTLEMENT_RULES)

    # Rescoring (after a change to scoring) reads the cached results again.
    objectives = {ev.id: ev.score.objective for ev in s.evaluations if ev.score}
    for ev in s.evaluations:
        if ev.score:
            ev.score.violation_steps = None
    rescored = study.rescore(backend)
    completed = [ev.id for ev in s.evaluations if ev.task_status == st.COMPLETED]
    assert sorted(rescored) == sorted(completed) and rescored[0] in ("e001", "e002")
    assert all(s.get(i).score.violation_steps == [] for i in rescored)  # type: ignore[union-attr]
    assert {i: s.get(i).score.objective for i in objectives} == objectives  # type: ignore[union-attr]
    assert s.outcome() == out
    assert rn.load_state(paths.state).get(rescored[0]).score.violation_steps == []  # type: ignore[union-attr]

    # Started: the spec is fixed now.
    paths.spec.write_text(yaml.safe_dump({**STUDY, "description": "v3"}), encoding="utf-8")
    with pytest.raises(ProjectError, match=r"study\.yaml changed"):
        rn.Study.open(ctx)


def test_cancelling_a_study_cancels_its_unfinished_runs(tmp_path: Path, ref26: Reference) -> None:
    write_project(tmp_path)
    project, ppaths, _ = Workspace(tmp_path).load("fl")
    paths = rn.StudyPaths(ppaths, "settle")
    paths.root.mkdir(parents=True)
    paths.spec.write_text(yaml.safe_dump(STUDY), encoding="utf-8")
    ctx = rn.StudyContext("fl", project, ppaths, paths, model(), {}, ref26, "r1")
    backend = FakeBackend()
    study = rn.Study.open(ctx, now=T0)
    study.tick(backend, now=T0)
    assert study.cancel(backend) == ["t1", "t2"] == backend.cancelled
    state = rn.load_state(paths.state)
    assert state is not None and state.stop_reason == "cancelled"
    assert study.tick(backend, now=T0).finished
    assert RunLog(ppaths.runs).cases == {}  # study runs stay out of runs.json


def test_a_second_study_shares_identical_runs_instead_of_starting_them(
    tmp_path: Path, ref26: Reference
) -> None:
    write_project(tmp_path)
    project, ppaths, _ = Workspace(tmp_path).load("fl")
    backend = FakeBackend()
    studies = {}
    for name in ("settle", "other"):
        paths = rn.StudyPaths(ppaths, name)
        paths.root.mkdir(parents=True)
        paths.spec.write_text(yaml.safe_dump({**STUDY, "name": name}), encoding="utf-8")
        ctx = rn.StudyContext("fl", project, ppaths, paths, model(), {}, ref26, "r1")
        studies[name] = rn.Study.open(ctx, now=T0)

    first = studies["settle"].tick(backend, now=T0)
    assert first.submitted == ["e001", "e002"] and len(backend.bodies) == 2

    dry = studies["other"].tick(backend, now=T0, dry_run=True)
    assert dry.shares == {"e001": "settle e001", "e002": "settle e002"}
    second = studies["other"].tick(backend, now=T0)
    assert second.submitted == [] and second.shared == ["e001", "e002"]
    assert len(backend.bodies) == 2
    other = studies["other"].state
    assert other.get("e001").shared_from == "settle e001" and other.get("e001").spent == 0

    # Cancelling a study leaves the runs it only follows alone.
    copy = rn.Study(studies["other"].ctx, other.model_copy(deep=True))
    assert copy.cancel(backend) == [] and backend.cancelled == []
    studies["other"].save()

    backend.finish_all()
    r = studies["other"].tick(backend, now=T0)
    assert set(r.scored) >= {"e001", "e002"}
    studies["settle"].tick(backend, now=T0)
    assert other.get("e001").task_id == studies["settle"].state.get("e001").task_id == "t1"


def test_a_shared_run_that_failed_is_started_again_not_followed_again(
    tmp_path: Path, ref26: Reference
) -> None:
    write_project(tmp_path)
    project, ppaths, _ = Workspace(tmp_path).load("fl")
    backend = FakeBackend()
    studies = {}
    for name in ("settle", "other"):
        paths = rn.StudyPaths(ppaths, name)
        paths.root.mkdir(parents=True)
        paths.spec.write_text(yaml.safe_dump({**STUDY, "name": name}), encoding="utf-8")
        ctx = rn.StudyContext("fl", project, ppaths, paths, model(), {}, ref26, "r1")
        studies[name] = rn.Study.open(ctx, now=T0)
    studies["settle"].tick(backend, now=T0)
    studies["other"].tick(backend, now=T0)
    backend.status["t1"] = st.FAILED
    backend.failures["t1"] = {"category": "job_failed", "message": "No OpenServer license"}

    # The study that started the run sees the failure first; the other one still has it
    # as submitted. Following that again would fail both on the same run.
    r = studies["settle"].tick(backend, now=T0)
    started = studies["settle"].state.get("e001")
    assert r.submitted == ["e001"] and r.shared == [] and len(backend.bodies) == 3
    assert (started.attempt, started.group_id, started.shared_from) == (2, "g3", None)
    r = studies["other"].tick(backend, now=T0)
    follower = studies["other"].state.get("e001")
    assert r.shared == ["e001"] and r.submitted == [] and len(backend.bodies) == 3
    assert (follower.attempt, follower.group_id, follower.shared_from) == (2, "g3", "settle e001")
    assert follower.history[0]["shared_from"] == "settle e001"
    assert (started.spent, follower.spent) == (2, 0)

    backend.finish_all()
    for name in ("settle", "other"):
        studies[name].tick(backend, now=T0)
    for ev in (started, follower):
        assert ev.task_id == "t3" and ev.score is not None and ev.score.feasible
