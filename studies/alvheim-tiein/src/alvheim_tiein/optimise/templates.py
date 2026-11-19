"""``study.yaml`` templates per scheme (``tiein optimise new``; research/22).

Each template is a working starting point for the project it is written for: the base
case is the first switched-on case (else the baseline), the reference case the
Froskelår-off baseline. Bounds, budgets and candidates are meant to be edited before
the first ``tiein optimise step``.
"""

from __future__ import annotations

from typing import Any

import yaml

from alvheim_tiein.optimise import study as st
from alvheim_tiein.project import Project, ProjectError

PLAN_FILES = {"r1_lend": "r1_lend.csv", "r4_pro_rata": "r4_pro_rata.csv"}
"""Booking plans ``tiein optimise plans`` writes for a restructure study."""
R3_PHI = (0.5, 0.8)

_HEADER = """\
# Optimisation study ({scheme}). `tiein optimise check {name}` validates it and shows
# the runs it needs; `tiein optimise step {name}` advances it (submit, follow, score).
# Once the first run is submitted the file is fixed: copy it to a new study to change it.
#
# base_case: every run starts from this case and adds lever cells, a candidate's cells or
#   a booking plan. reference_cases run as they are, on each grid, to compare against.
# objective: pv (resource ledger, discounted), cash_flow, revenue, oe_sm3 or oil_sm3.
# fidelity: search runs on a coarse grid (mh: monthly to Oct 2027, then half-yearly;
#   about 2 h on D4) with the step tables remapped; the best points are confirmed
#   monthly. Use search: monthly if the MH grid misranks cases (the fidelity gate).
# Levers (kind):
#   weights       alpha: w = 1 + alpha (w0 - 1); 1 is today, 0 plain oil
#   release       beta: cap = B + beta (L - B) for `groups` in `window` (booking, future,
#                 all); 0 is today, 1 the FPSO limit
#   liquid_scale  gamma: future liquid bookings times gamma
#   well_cell     one per-well cell, e.g. gas lift or drawdown:
#                 {{name: lift_nt1, kind: well_cell, wells: [NT1], column: MaxGasInj,
#                   lower: 0, upper: 150, baseline: 80}}
# constraints.no_loss: licences ("*": all) that may not lose against no_loss_against
#   (`base` or a reference case) by more than no_loss_tol (PV) on the participant ledger.
"""

_NOTES = {
    "outer": """\
#
# outer: screening (which levers matter), then a pattern search on the
# `algorithm.active_levers` that matter most, then the best points confirmed monthly.
""",
    "soften_bookings": """\
#
# soften_bookings: a grid over how hard the bookings steer GAP. alpha softens the
# weights, beta releases the booked caps towards the FPSO limits. These are allocation
# experiments (what today's rules cost), not proposals: they remove the protection the
# bookings give. Booking shortfalls per licence are in the report.
""",
    "total_then_settle": """\
#
# total_then_settle: candidates that maximise the hub (neutral weights, released
# bookings), valued against the base case and the Froskelaar-off baseline; then
# `tiein optimise report` settles who pays whom (proportional to booked capacity, the
# decided rule; minimal: losers made whole; equal).
""",
    "restructure_bookings": """\
#
# restructure_bookings: booking plans when Froskelaar opens, run with Froskelaar on.
# `tiein optimise plans {name} --s2 <lifted case>` writes the plans from the base case
# (S1, today's bookings) and a run with the bookings lifted (S2, each group's demand):
#   r1_lend      capacity a group left unused in S1 is lent to groups at their cap
#   r4_pro_rata  each window's envelope re-split pro rata to S2 demand
#   r3_phi50/80  a Froskelaar liquid cap at 50 / 80 % of its S2 peak rate
# Add `constraints: {{no_loss: "*", no_loss_against: baseline}}` to keep only plans that
# leave every licence at least as well off as before the tie-in (wave 3).
""",
}


def default_cases(project: Project) -> tuple[str, list[str]]:
    """Base case and reference cases: the first switched-on case against the baseline,
    else the baseline alone."""
    baseline = project.baseline_case.name
    on = [c.name for c in project.cases if not c.baseline and project.switch_state(c) == "on"]
    if on:
        return on[0], [baseline]
    return baseline, []


def _levers(scheme: str, groups: list[str]) -> list[dict[str, Any]]:
    release_window = "all" if scheme == "total_then_settle" else "booking"
    alpha: dict[str, Any] = {"name": "alpha", "kind": "weights", "lower": 0, "upper": 1}
    beta: dict[str, Any] = {
        "name": "beta",
        "kind": "release",
        "lower": 0,
        "upper": 1,
        "groups": groups,
        "window": release_window,
    }
    if scheme == "soften_bookings":
        return [
            {**alpha, "baseline": 1, "levels": [0, 0.5, 1]},
            {**beta, "baseline": 0, "levels": [0, 0.5, 1]},
        ]
    if scheme == "total_then_settle":
        return [{**alpha, "baseline": 1}, {**beta, "baseline": 0}]
    if scheme == "outer":
        return [
            {**alpha, "baseline": 1},
            {**beta, "baseline": 0},
            {
                "name": "gamma",
                "kind": "liquid_scale",
                "lower": 0.8,
                "upper": 1.2,
                "baseline": 1,
                "groups": groups,
            },
        ]
    return []


def template(
    scheme: str,
    name: str,
    project: Project,
    *,
    base_case: str | None = None,
    reference_cases: list[str] | None = None,
) -> dict[str, Any]:
    """The spec of a new study as a mapping (validated)."""
    if scheme not in st.SCHEMES:
        raise ProjectError(f"no scheme {scheme!r}; schemes: {', '.join(st.SCHEMES)}")
    base, refs = default_cases(project)
    base = base_case or base
    refs = [r for r in (refs if reference_cases is None else reference_cases) if r != base]
    for case in [base, *refs]:
        project.case(case)
    groups = list(project.bookings.groups)
    data: dict[str, Any] = {
        "name": name,
        "scheme": scheme,
        "description": "",
        "base_case": base,
        "reference_cases": refs,
        "objective": "pv",
        "reuse_case_runs": True,
        "fidelity": {"search": "mh", "confirm": "monthly", "weights": "months"},
    }
    levers = _levers(scheme, groups)
    if levers:
        data["levers"] = levers
    if scheme == "outer":
        data["algorithm"] = {"active_levers": 2, "seed": 0}
        data["budget"] = {"max_evaluations": 30, "wave_size": 6, "confirm": 2, "max_hours": 72}
    elif scheme == "soften_bookings":
        data["budget"] = {"max_evaluations": 14, "wave_size": 6, "confirm": 3}
    elif scheme == "total_then_settle":
        data["candidates"] = [
            {
                "name": "neutral_weights",
                "description": "GAP maximises plain oil (alpha 0)",
                "theta": {"alpha": 0},
            },
            {
                "name": "release_bookings",
                "description": "booked caps at the FPSO limits in every window (beta 1)",
                "theta": {"beta": 1},
            },
            {
                "name": "neutral_and_release",
                "description": "both",
                "theta": {"alpha": 0, "beta": 1},
            },
        ]
        data["budget"] = {"max_evaluations": 8, "wave_size": 5, "confirm": 2}
    else:
        data["candidates"] = [
            {
                "name": cand,
                "description": "written by `tiein optimise plans`",
                "booking_plan": plan,
            }
            for cand, plan in PLAN_FILES.items()
        ]
        data["budget"] = {"max_evaluations": 10, "wave_size": 6, "confirm": 2}
    data["constraints"] = {"no_loss": [], "no_loss_against": "base"}
    try:
        st.StudySpec.model_validate(data)
    except ValueError as e:
        raise ProjectError(f"study {name}: {e}") from e
    return data


def header(scheme: str, name: str) -> str:
    return _HEADER.format(scheme=scheme, name=name) + _NOTES[scheme].format(name=name)


def study_yaml(data: dict[str, Any], *, comments: str = "") -> str:
    body = yaml.safe_dump(data, sort_keys=False, allow_unicode=True, width=100)
    return comments + body


__all__ = ["PLAN_FILES", "R3_PHI", "default_cases", "header", "study_yaml", "template"]
