from __future__ import annotations

import json
import math
from collections.abc import Callable, Mapping

import pytest

from alvheim_tiein.optimise import algorithms as alg
from alvheim_tiein.optimise.algorithms import (
    InterruptibleState,
    Iterate,
    Lever,
    PatternSearch,
)

# --------------------------------------------------------------------------------------------
# Levers and grids
# --------------------------------------------------------------------------------------------


def test_lever_maps_between_coded_and_values() -> None:
    lever = Lever("beta", 10.0, 20.0, baseline=12.0)
    assert lever.centre == 15.0
    assert lever.half_range == 5.0
    assert lever.default == 12.0
    assert lever.to_coded(10.0) == -1.0
    assert lever.to_coded(20.0) == 1.0
    assert lever.to_coded(12.5) == pytest.approx(-0.5)
    assert lever.from_coded(-1.0) == 10.0
    assert lever.from_coded(1.0) == 20.0
    assert lever.from_coded(0.0) == 15.0
    assert lever.from_coded(1.7) == 20.0
    assert lever.from_coded(-3.0) == 10.0
    assert lever.clip(25.0) == 20.0
    assert lever.clip(-1.0) == 10.0
    assert lever.clip(11.0) == 11.0
    for u in (-1.0, -0.375, 0.0, 0.25, 1.0):
        assert lever.to_coded(lever.from_coded(u)) == pytest.approx(u)
    assert Lever("x", 0.1, 0.3).from_coded(1.0) == 0.3
    assert Lever("x", -2.0, 4.0).default == 1.0


def test_lever_validation_and_round_trip() -> None:
    with pytest.raises(ValueError):
        Lever("x", 1.0, 1.0)
    with pytest.raises(ValueError):
        Lever("x", 0.0, math.inf)
    with pytest.raises(ValueError):
        Lever("x", 0.0, 1.0, baseline=2.0)
    with pytest.raises(ValueError):
        Lever("x", 0.0, 1.0, levels=(0.0, 1.5))
    with pytest.raises(ValueError):
        Lever("x", 0.0, 1.0, levels=(0.5, 0.5))
    with pytest.raises(ValueError):
        Lever("", 0.0, 1.0)
    lever = Lever("x", 0, 2, baseline=1, levels=(0, 1, 2))
    assert lever.levels == (0.0, 1.0, 2.0)
    restored = Lever.from_dict(json.loads(json.dumps(lever.to_dict())))
    assert restored == lever


def test_point_helpers() -> None:
    levers = [Lever("a", 0.0, 10.0), Lever("b", -1.0, 1.0)]
    assert alg.to_coded(levers, {"a": 7.5, "b": 0.5}) == [0.5, 0.5]
    assert alg.from_coded(levers, [-1.0, 0.0]) == {"a": 0.0, "b": 0.0}
    assert alg.clip_point(levers, {"a": 12.0, "b": -3.0, "other": 1.0}) == {"a": 10.0, "b": -1.0}
    with pytest.raises(ValueError):
        alg.from_coded(levers, [0.0])


def test_grid_is_full_factorial_in_deterministic_order() -> None:
    levers = [Lever("a", 0.0, 1.0, levels=(0.0, 0.5, 1.0)), Lever("b", 2.0, 3.0)]
    points = alg.grid(levers)
    assert points == [
        {"a": 0.0, "b": 2.0},
        {"a": 0.0, "b": 3.0},
        {"a": 0.5, "b": 2.0},
        {"a": 0.5, "b": 3.0},
        {"a": 1.0, "b": 2.0},
        {"a": 1.0, "b": 3.0},
    ]
    with pytest.raises(ValueError):
        alg.grid([Lever("a", 0.0, 1.0), Lever("a", 0.0, 2.0)])


# --------------------------------------------------------------------------------------------
# Conference matrices and definitive screening
# --------------------------------------------------------------------------------------------


def _gram(matrix: list[list[int]] | tuple[tuple[int, ...], ...]) -> list[list[int]]:
    cols = len(matrix[0])
    return [[sum(row[i] * row[j] for row in matrix) for j in range(cols)] for i in range(cols)]


@pytest.mark.parametrize("n", [4, 6, 8, 12, 14, 18])
def test_conference_matrix_is_orthogonal(n: int) -> None:
    c = alg.conference_matrix(n)
    assert len(c) == n and all(len(row) == n for row in c)
    gram = _gram(c)
    for i in range(n):
        for j in range(n):
            assert gram[i][j] == (n - 1 if i == j else 0)
    for i in range(n):
        assert c[i][i] == 0
        assert all(abs(c[i][j]) == 1 for j in range(n) if j != i)
    sign = 1 if (n - 1) % 4 == 1 else -1
    assert all(c[i][j] == sign * c[j][i] for i in range(n) for j in range(n))


@pytest.mark.parametrize("n", [2, 3, 5, 10, 16])
def test_conference_matrix_rejects_unsupported_orders(n: int) -> None:
    with pytest.raises(ValueError):
        alg.conference_matrix(n)


def test_screening_order_and_runs() -> None:
    assert [alg.screening_order(d) for d in range(1, 11)] == [4, 4, 4, 4, 6, 6, 8, 8, 12, 12]
    assert alg.screening_runs(6) == 13
    assert alg.screening_runs(8) == 17
    assert alg.screening_runs(4) == 9
    assert alg.screening_runs(12) == 25
    with pytest.raises(ValueError):
        alg.screening_order(0)


@pytest.mark.parametrize("d", [1, 2, 3, 4, 5, 6, 7, 8, 9])
def test_definitive_screening_structure(d: int) -> None:
    levers = [Lever(f"l{j}", 0.0, 1.0) for j in range(d)]
    design = alg.definitive_screening(levers)
    n = design.order
    rows = design.coded
    assert len(rows) == 2 * n + 1 == alg.screening_runs(d)
    if d in (4, 6, 8):
        assert len(rows) == 2 * d + 1
    assert all(len(row) == d for row in rows)
    # Fold-over: the second block is the first one negated; the last row is the centre.
    for i in range(n):
        assert rows[n + i] == tuple(-x for x in rows[i])
    assert rows[-1] == (0,) * d
    # Orthogonal, zero-sum columns with three centre points each.
    gram = _gram(rows)
    for i in range(d):
        for j in range(d):
            assert gram[i][j] == (2 * (n - 1) if i == j else 0)
        assert sum(row[i] for row in rows) == 0
        assert sum(1 for row in rows if row[i] == 0) == 3
    assert design.names == tuple(lv.name for lv in levers)
    assert json.loads(json.dumps(design.to_dict()))["order"] == n


def test_definitive_screening_maps_to_lever_bounds() -> None:
    levers = [Lever("alpha", 0.0, 1.0), Lever("beta", 10.0, 30.0), Lever("gamma", -4.0, -2.0)]
    design = alg.definitive_screening(levers)
    assert len(design.points) == len(design.coded)
    for row, point in zip(design.coded, design.points, strict=True):
        for lever, u in zip(levers, row, strict=True):
            expected = {-1: lever.lower, 0: lever.centre, 1: lever.upper}[u]
            assert point[lever.name] == expected


# --------------------------------------------------------------------------------------------
# Screening analysis
# --------------------------------------------------------------------------------------------


def _dsd(d: int) -> list[tuple[int, ...]]:
    return list(alg.definitive_screening([Lever(f"x{j + 1}", -1.0, 1.0) for j in range(d)]).coded)


def test_screen_recovers_main_effects_despite_quadratic_terms() -> None:
    coded = _dsd(6)

    def f(u: tuple[int, ...]) -> float:
        return 5 + 3 * u[0] - 2 * u[1] + 0.5 * u[2] + 4 * u[0] ** 2 - u[4] ** 2 + 0.7 * u[1] * u[2]

    result = alg.screen(coded, [f(u) for u in coded])
    assert result.method == "orthogonal"
    assert result.n_feasible == result.n_rows == 13
    effects = [e.effect for e in result.effects]
    assert effects == pytest.approx([3.0, -2.0, 0.5, 0.0, 0.0, 0.0], abs=1e-12)
    assert [e.rank for e in result.effects[:3]] == [1, 2, 3]
    assert alg.active_levers(result, k=3) == ["x1", "x2", "x3"]
    assert alg.active_levers(result, k=1) == ["x1"]
    with pytest.raises(ValueError):
        alg.active_levers(result, k=0)
    assert json.loads(json.dumps(result.to_dict()))["method"] == "orthogonal"


def test_screen_ignores_infeasible_rows() -> None:
    coded = _dsd(6)

    def f(u: tuple[int, ...]) -> float:
        return 1 + 2 * u[0] - u[3] + 0.25 * u[5]

    responses: list[float | None] = [f(u) for u in coded]
    feasible = [True] * len(coded)
    for i in (0, 4, 9):
        feasible[i] = False
        responses[i] = 1e9  # whatever an infeasible run reports must not matter
    responses[7] = None  # a failed run
    result = alg.screen(coded, responses, feasible, names=["a", "b", "c", "d", "e", "f"])
    assert result.method == "least_squares"
    assert result.n_feasible == 9
    assert result.intercept == pytest.approx(1.0)
    assert [e.effect for e in result.effects] == pytest.approx(
        [2.0, 0.0, 0.0, -1.0, 0.0, 0.25], abs=1e-9
    )
    assert alg.active_levers(result, k=2) == ["a", "d"]


def test_screen_curvature_indicator_and_best_level() -> None:
    coded = _dsd(4)
    result = alg.screen(coded, [-4.0 * u[0] ** 2 + 0.5 * u[1] for u in coded])
    x1, x2 = result.effects[0], result.effects[1]
    # Rows at x1 = 0 all give 0, rows at x1 = ±1 all give -4 (+/- the x2 term, which cancels).
    assert x1.curvature == pytest.approx(4.0)
    assert x1.best_level == 0.0
    assert x2.best_level == 1.0
    assert x1.effect == pytest.approx(0.0, abs=1e-12)
    assert x2.effect == pytest.approx(0.5)

    levers = [Lever(f"x{j + 1}", 0.0, 10.0, baseline=2.0) for j in range(4)]
    settings = alg.inactive_settings(result, levers, k=1)
    assert set(settings) == {"x1", "x3", "x4"}
    assert settings["x1"] == 5.0  # best level 0 -> centre


def test_screen_validates_inputs() -> None:
    coded = _dsd(4)
    with pytest.raises(ValueError):
        alg.screen(coded, [1.0] * (len(coded) - 1))
    with pytest.raises(ValueError):
        alg.screen(coded, [1.0] * len(coded), [True] * 3)
    with pytest.raises(ValueError):
        alg.screen(coded, [1.0] * len(coded), [True] * 4 + [False] * (len(coded) - 4))
    with pytest.raises(ValueError):
        alg.screen(coded, [1.0] * len(coded), names=["a"])
    with pytest.raises(ValueError):
        alg.screen([], [])


# --------------------------------------------------------------------------------------------
# Pattern search
# --------------------------------------------------------------------------------------------

Objective = Callable[[Mapping[str, float]], float]


def drive(
    search: PatternSearch,
    f: Objective,
    feasible: Callable[[Mapping[str, float]], bool] = lambda p: True,
    rounds: int = 1000,
) -> list[dict[str, float]]:
    proposed: list[dict[str, float]] = []
    for _ in range(rounds):
        points = search.poll()
        if not points:
            break
        proposed.extend(points)
        search.tell([(p, f(p), feasible(p)) for p in points])
    return proposed


def _key(levers: list[Lever], point: Mapping[str, float]) -> tuple[float, ...]:
    return tuple(round(c, 9) for c in alg.to_coded(levers, point))


def _coded_quadratic(levers: list[Lever], optimum: list[float]) -> Objective:
    def f(p: Mapping[str, float]) -> float:
        coded = alg.to_coded(levers, p)
        return -sum((u - c) ** 2 for u, c in zip(coded, optimum, strict=True))

    return f


THREE = [Lever("a", 0.0, 10.0), Lever("b", -5.0, 5.0), Lever("c", 100.0, 200.0)]


def test_pattern_search_maximises_concave_function_in_three_dimensions() -> None:
    optimum = [THREE[0].to_coded(3.7), THREE[1].to_coded(-1.2), THREE[2].to_coded(130.0)]
    f = _coded_quadratic(THREE, optimum)
    search = PatternSearch(THREE, seed=7, min_mesh=1 / 64, max_unsuccessful_polls=None, budget=200)
    proposed = drive(search, f)
    assert search.stop_reason() == "mesh_below_minimum"
    assert search.n_evaluations == len(proposed) <= 120
    assert search.incumbent_value is not None
    assert search.incumbent_value > -3 * (1 / 128) ** 2 - 1e-12
    incumbent = search.incumbent
    assert incumbent is not None
    assert incumbent["a"] == pytest.approx(3.7, abs=0.05)
    assert incumbent["b"] == pytest.approx(-1.2, abs=0.05)
    assert incumbent["c"] == pytest.approx(130.0, abs=0.5)
    feasible_values = [v for _, v, ok in search.evaluations() if ok and v is not None]
    assert search.incumbent_value == max(feasible_values)


def test_pattern_search_with_default_stop_rules_in_two_dimensions() -> None:
    levers = [Lever("x", 0.0, 1.0, baseline=0.5), Lever("y", 0.0, 1.0, baseline=0.5)]
    f = _coded_quadratic(levers, [0.3, -0.6])
    search = PatternSearch(levers, seed=1, budget=40)
    drive(search, f)
    assert search.stop_reason() in ("no_improvement", "mesh_below_minimum")
    assert search.n_evaluations <= 40
    assert search.incumbent_value is not None
    assert search.incumbent_value > f({"x": 0.5, "y": 0.5})
    assert search.incumbent_value > -0.1
    assert search.n_polls >= 2 and search.n_successes >= 1


def test_pattern_search_respects_bounds() -> None:
    levers = [Lever("x", 0.0, 1.0), Lever("y", 2.0, 3.0)]
    search = PatternSearch(levers, seed=3, max_unsuccessful_polls=None)
    proposed = drive(search, lambda p: p["x"] + p["y"])
    assert proposed
    for point in proposed:
        assert 0.0 <= point["x"] <= 1.0
        assert 2.0 <= point["y"] <= 3.0
    assert search.incumbent == {"x": 1.0, "y": 3.0}
    with pytest.raises(ValueError):
        search.tell([({"x": 1.5, "y": 2.0}, 1.0, True)])
    with pytest.raises(KeyError):
        search.tell([({"x": 0.5}, 1.0, True)])


def test_pattern_search_never_reproposes_evaluated_points() -> None:
    levers = [Lever("x", -1.0, 1.0), Lever("y", -1.0, 1.0)]
    f = _coded_quadratic(levers, [0.4, 0.1])
    search = PatternSearch(levers, seed=5, max_unsuccessful_polls=None, min_mesh=1 / 128)
    # Observations reused from elsewhere (e.g. screening) are cached up front.
    prior = [{"x": 0.0, "y": 0.0}, {"x": 0.5, "y": 0.0}, {"x": 0.0, "y": -0.5}]
    search.tell([(p, f(p), True) for p in prior])
    assert search.incumbent == {"x": 0.5, "y": 0.0}
    proposed = drive(search, f)
    keys = [_key(levers, p) for p in proposed]
    assert len(keys) == len(set(keys))
    assert not {_key(levers, p) for p in prior} & set(keys)
    assert search.n_reused >= 1
    assert search.n_evaluations == len(proposed) + len(prior)


def test_pattern_search_treats_infeasible_points_as_a_barrier() -> None:
    levers = [Lever("x", -1.0, 1.0), Lever("y", -1.0, 1.0)]
    f = _coded_quadratic(levers, [0.6, 0.0])

    def feasible(p: Mapping[str, float]) -> bool:
        return p["x"] <= 0.3

    search = PatternSearch(levers, seed=11, max_unsuccessful_polls=None, min_mesh=1 / 32)
    proposed = drive(search, f, feasible)
    assert any(not feasible(p) for p in proposed)
    for event in search.history:
        if event["event"] == "resolve" and event["incumbent"] is not None:
            assert event["incumbent"]["x"] <= 0.3
    incumbent = search.incumbent
    assert incumbent is not None
    assert 0.25 <= incumbent["x"] <= 0.3
    feasible_values = [v for _, v, ok in search.evaluations() if ok and v is not None]
    assert search.incumbent_value == max(feasible_values)


def test_pattern_search_handles_infeasible_start_and_failed_runs() -> None:
    levers = [Lever("x", -1.0, 1.0), Lever("y", -1.0, 1.0)]
    search = PatternSearch(levers, start={"x": 0.8, "y": 0.0}, seed=2)
    assert search.poll() == [{"x": 0.8, "y": 0.0}]
    search.tell([({"x": 0.8, "y": 0.0}, 5.0, False)])
    assert search.incumbent is None
    points = search.poll()
    assert len(points) == 4
    # Every run fails except one feasible point with a poor value: it still becomes the
    # incumbent, because no feasible point existed before.
    results = []
    for p in points:
        if p["x"] == pytest.approx(0.3):
            results.append((p, -10.0, True))
        else:
            results.append((p, None, True))
    search.tell(results)
    assert search.incumbent is not None
    assert search.incumbent["x"] == pytest.approx(0.3)
    assert search.incumbent_value == -10.0
    failed = [v for _, v, ok in search.evaluations() if not ok]
    assert len(failed) == 4 and failed.count(None) == 3 and 5.0 in failed
    # A failed run may be retried and told again; a feasible one may not change.
    retry = next(p for p, v, _ in search.evaluations() if v is None)
    search.tell([(retry, -20.0, True)])
    with pytest.raises(ValueError):
        search.tell([(retry, -21.0, True)])


def test_pattern_search_is_deterministic_given_the_seed() -> None:
    f = _coded_quadratic(THREE, [0.2, -0.3, 0.5])

    def run(seed: int) -> list[dict]:
        search = PatternSearch(THREE, seed=seed, budget=60, max_unsuccessful_polls=None)
        drive(search, f)
        return search.history

    assert run(4) == run(4)
    first_polls = set()
    for seed in range(6):
        search = PatternSearch(THREE, seed=seed)
        search.poll()
        search.tell([(search.start, 0.0, True)])
        first_polls.add(tuple(tuple(sorted(p.items())) for p in search.poll()))
    assert len(first_polls) > 1


def _round_trip(search: PatternSearch) -> PatternSearch:
    return PatternSearch.from_dict(json.loads(json.dumps(search.to_dict())))


def test_pattern_search_state_round_trip() -> None:
    f = _coded_quadratic(THREE, [0.3, 0.7, -0.45])

    def feasible(p: Mapping[str, float]) -> bool:
        return p["a"] < 9.0

    reference = PatternSearch(THREE, seed=9, budget=80, max_unsuccessful_polls=3)
    drive(reference, f, feasible)

    resumed = PatternSearch(THREE, seed=9, budget=80, max_unsuccessful_polls=3)
    for _ in range(1000):
        resumed = _round_trip(resumed)
        points = resumed.poll()
        if not points:
            break
        resumed = _round_trip(resumed)
        assert resumed.poll() == points  # outstanding points survive a resume
        # Results arrive one at a time, with a resume between each.
        for p in points:
            resumed.tell([(p, f(p), feasible(p))])
            resumed = _round_trip(resumed)
    assert resumed.history == reference.history
    assert resumed.incumbent == reference.incumbent
    assert resumed.stop_reason() == reference.stop_reason()
    assert resumed.to_dict() == reference.to_dict()


def test_partial_tell_keeps_the_poll_open() -> None:
    levers = [Lever("x", -1.0, 1.0), Lever("y", -1.0, 1.0)]
    search = PatternSearch(levers, seed=0)
    search.tell([(search.start, 0.0, True)])
    points = search.poll()
    assert len(points) == 4
    search.tell([(points[0], -1.0, True)])
    assert search.poll() == points[1:]
    assert search.n_polls == 0
    search.tell([(p, -1.0, True) for p in points[1:]])
    assert search.n_polls == 1
    assert search.mesh == 0.25


def test_stop_reason_budget_exhausted() -> None:
    search = PatternSearch(THREE, seed=0, budget=5)
    points = search.poll()
    assert len(points) == 1
    search.tell([(p, 0.0, True) for p in points])
    points = search.poll()
    assert len(points) == 4  # 6 poll points cut to the remaining budget
    search.tell([(p, -1.0, True) for p in points])
    assert search.stop_reason() == "budget_exhausted"
    assert search.n_evaluations == 5
    assert search.poll() == []


def test_stop_reason_mesh_below_minimum() -> None:
    levers = [Lever("x", -1.0, 1.0), Lever("y", -1.0, 1.0)]
    search = PatternSearch(levers, seed=0, max_unsuccessful_polls=None)
    drive(search, lambda p: 1.0)
    assert search.stop_reason() == "mesh_below_minimum"
    assert search.n_polls == 4  # 0.5 -> 0.25 -> 0.125 -> 0.0625 -> 0.03125 < 1/16
    assert search.mesh == 1 / 32
    assert search.incumbent == {"x": 0.0, "y": 0.0}


def test_stop_reason_no_improvement_with_threshold() -> None:
    levers = [Lever("x", -1.0, 1.0), Lever("y", -1.0, 1.0)]
    search = PatternSearch(levers, seed=0, min_improvement=0.01)
    # Improvements of 0.005 per poll are below the threshold.
    drive(search, lambda p: 0.01 * p["x"])
    assert search.stop_reason() == "no_improvement"
    assert search.n_polls == 2
    assert search.n_successes == 0
    assert search.incumbent == {"x": 0.0, "y": 0.0}


def test_mesh_grows_after_success_and_is_capped() -> None:
    levers = [Lever("x", -1.0, 1.0)]
    search = PatternSearch(levers, start={"x": -1.0}, seed=0, max_unsuccessful_polls=None)
    search.tell([(search.start, -1.0, True)])
    meshes = []
    for _ in range(4):
        points = search.poll()
        search.tell([(p, p["x"], True) for p in points])
        meshes.append(search.mesh)
    # -1 -> -0.5 -> 0.5 -> 1.0 (clipped) are successes; the fourth poll from the bound fails.
    assert meshes == [1.0, 1.0, 1.0, 0.5]
    assert search.incumbent == {"x": 1.0}


@pytest.mark.parametrize("reason", ["cancelled", "wall_clock"])
def test_driver_stop_reasons(reason: alg.DriverStop) -> None:
    search = PatternSearch(THREE, seed=0)
    assert search.stop_reason() is None
    search.stop(reason)
    assert search.stop_reason() == reason
    assert search.poll() == []
    assert _round_trip(search).stop_reason() == reason


def test_driver_stop_rejects_other_reasons() -> None:
    search = PatternSearch(THREE, seed=0)
    with pytest.raises(ValueError):
        search.stop("no_improvement")  # type: ignore[arg-type]


def test_pattern_search_validates_settings() -> None:
    with pytest.raises(ValueError):
        PatternSearch(THREE, mesh=2.0)
    with pytest.raises(ValueError):
        PatternSearch(THREE, budget=0)
    with pytest.raises(ValueError):
        PatternSearch(THREE, min_improvement=-1.0)
    with pytest.raises(ValueError):
        PatternSearch([])


# --------------------------------------------------------------------------------------------
# Interruptible capacity
# --------------------------------------------------------------------------------------------

# One period: A lends (uses 40 of 100), B and C are at their caps with unmet demand 60 and 30.
BOOKED = {("A", 0): 100.0, ("B", 0): 50.0, ("C", 0): 50.0}
FIRM = {("A", 0): 40.0, ("B", 0): 50.0, ("C", 0): 50.0}
DEMAND = {("A", 0): 40.0, ("B", 0): 110.0, ("C", 0): 80.0}
ZERO = dict.fromkeys(BOOKED, 0.0)


def test_spare_capacity_per_period() -> None:
    booked = {**BOOKED, ("A", 1): 100.0, ("B", 1): 50.0}
    used = {**FIRM, ("A", 1): 120.0, ("B", 1): 20.0}
    assert alg.spare_capacity(booked, used) == {0: 60.0, 1: 30.0}
    with pytest.raises(ValueError):
        alg.spare_capacity(booked, FIRM)


def test_spare_capacity_is_shared_pro_rata_to_unmet_demand() -> None:
    assert alg.recipients(BOOKED, FIRM, DEMAND, ZERO) == [("B", 0), ("C", 0)]
    raw = alg.raw_tranches(BOOKED, FIRM, DEMAND, ZERO)
    assert raw == pytest.approx({("A", 0): 0.0, ("B", 0): 40.0, ("C", 0): 20.0})
    assert sum(raw.values()) == pytest.approx(60.0)
    tranches = alg.next_tranches(BOOKED, FIRM, FIRM, DEMAND, ZERO, damping=0.0)
    assert tranches == pytest.approx(raw)


def test_tranches_never_exceed_unmet_demand() -> None:
    booked = {**BOOKED, ("A", 0): 300.0}
    used = {**FIRM, ("A", 0): 100.0}  # 200 spare, only 90 unmet demand
    raw = alg.raw_tranches(booked, used, DEMAND, ZERO)
    assert raw == pytest.approx({("A", 0): 0.0, ("B", 0): 60.0, ("C", 0): 30.0})
    tranches = alg.next_tranches(booked, used, used, DEMAND, ZERO, damping=0.0)
    unmet = alg.unmet_demand(booked, DEMAND)
    assert all(tranches[k] <= unmet[k] + 1e-12 for k in booked)


def test_groups_below_their_cap_receive_nothing() -> None:
    used = {**FIRM, ("B", 0): 45.0}
    assert alg.recipients(BOOKED, used, DEMAND, ZERO) == [("C", 0)]
    raw = alg.raw_tranches(BOOKED, used, DEMAND, ZERO)
    assert raw[("B", 0)] == 0.0
    assert raw[("C", 0)] == pytest.approx(30.0)  # 65 spare, capped at C's unmet demand
    # A group holding a tranche is at its cap only when it uses the tranche too.
    holding = {("A", 0): 0.0, ("B", 0): 20.0, ("C", 0): 0.0}
    assert ("B", 0) not in alg.recipients(BOOKED, {**FIRM, ("B", 0): 60.0}, DEMAND, holding)
    assert ("B", 0) in alg.recipients(BOOKED, {**FIRM, ("B", 0): 70.0}, DEMAND, holding)


def test_damping() -> None:
    prev = {("A", 0): 0.0, ("B", 0): 10.0, ("C", 0): 30.0}
    used = {**FIRM, ("B", 0): 60.0, ("C", 0): 80.0}
    # Spare 60, raw 40 / 20 (both at their caps).
    half = alg.next_tranches(BOOKED, used, FIRM, DEMAND, prev)
    assert half == pytest.approx({("A", 0): 0.0, ("B", 0): 25.0, ("C", 0): 25.0})
    assert alg.next_tranches(BOOKED, used, FIRM, DEMAND, prev, damping=1.0) == pytest.approx(prev)
    with pytest.raises(ValueError):
        alg.next_tranches(BOOKED, used, FIRM, DEMAND, prev, damping=1.5)


def test_recall_cuts_tranches_by_the_lenders_shortfall() -> None:
    used = {**FIRM, ("A", 0): 30.0}  # A squeezed 10 below its firm-run rate
    shortfall = alg.recall_shortfall(BOOKED, used, FIRM, [("B", 0), ("C", 0)])
    assert shortfall == {0: pytest.approx(10.0)}
    tranches = alg.next_tranches(BOOKED, used, FIRM, DEMAND, ZERO)
    # Spare 70 -> raw 46.67 / 23.33 -> damped 23.33 / 11.67 (35) -> cut by 10, pro rata.
    assert sum(tranches.values()) == pytest.approx(25.0)
    assert tranches[("B", 0)] == pytest.approx(2 * tranches[("C", 0)])
    assert tranches[("A", 0)] == 0.0
    # Within the tolerance there is no recall.
    within = {**FIRM, ("A", 0): 39.7}
    assert alg.recall_shortfall(BOOKED, within, FIRM, [("B", 0), ("C", 0)]) == {0: 0.0}
    # A shortfall larger than the tranches removes them, never below zero.
    squeezed = {**FIRM, ("A", 0): 0.0}
    firm = {**FIRM, ("A", 0): 90.0}
    cut = alg.next_tranches(BOOKED, squeezed, firm, DEMAND, ZERO)  # damped 45, shortfall 90
    assert cut == {("A", 0): 0.0, ("B", 0): 0.0, ("C", 0): 0.0}


def test_firm_bookings_are_never_lowered() -> None:
    booked = dict(BOOKED)
    used = {**FIRM, ("A", 0): 30.0}
    tranches = alg.next_tranches(booked, used, FIRM, DEMAND, ZERO)
    assert booked == BOOKED
    assert all(b >= 0.0 for b in tranches.values())
    capped = alg.caps(booked, {**tranches, ("A", 0): -5.0})
    assert all(capped[k] >= booked[k] for k in booked)
    assert capped[("A", 0)] == 100.0


def _simulate(caps: Mapping[tuple[str, int], float]) -> dict[tuple[str, int], float]:
    """Each group produces min(demand, cap); no shared limit binds."""
    return {k: min(DEMAND[k], caps[k]) for k in BOOKED}


def _objective(rates: Mapping[tuple[str, int], float]) -> float:
    return sum(rates.values())


def test_interruptible_state_converges_at_a_fixed_point() -> None:
    state = InterruptibleState(
        booked={"oil": dict(BOOKED)}, demand={"oil": dict(DEMAND)}, damping=0
    )
    assert state.caps() == {"oil": BOOKED}
    firm = _simulate(state.caps()["oil"])
    state.record({"oil": firm}, _objective(firm))
    assert state.iteration == 0
    assert state.stop_reason() is None
    assert state.tranches["oil"] == pytest.approx({("A", 0): 0.0, ("B", 0): 40.0, ("C", 0): 20.0})
    rates = _simulate(state.caps()["oil"])
    state.record({"oil": rates}, _objective(rates))
    assert state.iteration == 1
    assert state.stop_reason() == "converged"
    with pytest.raises(RuntimeError):
        state.record({"oil": rates}, _objective(rates))
    last = state.last_feasible()
    assert last is not None and last.objective == pytest.approx(200.0)
    assert last.rates["oil"] == pytest.approx({("A", 0): 40.0, ("B", 0): 90.0, ("C", 0): 70.0})


def test_interruptible_state_stops_after_max_iterations() -> None:
    state = InterruptibleState(booked={"oil": dict(BOOKED)}, demand={"oil": dict(DEMAND)})
    caps_seen = []
    while state.stop_reason() is None:
        caps_seen.append(state.caps()["oil"][("B", 0)])
        rates = _simulate(state.caps()["oil"])
        state.record({"oil": rates}, _objective(rates))
    assert state.stop_reason() == "max_iterations"
    assert state.iteration == alg.MAX_ITERATIONS
    # Damped approach to B's full tranche of 40: 50, 70, 80, 85, 87.5.
    assert caps_seen == pytest.approx([50.0, 70.0, 80.0, 85.0, 87.5])
    restored = InterruptibleState.from_dict(json.loads(json.dumps(state.to_dict())))
    assert restored.to_dict() == state.to_dict()
    assert restored.stop_reason() == "max_iterations"


def _iterate(cap: float, rate: float, objective: float | None, feasible: bool = True) -> Iterate:
    return Iterate({"oil": {("B", 0): cap}}, {"oil": {("B", 0): rate}}, objective, feasible)


def test_converged() -> None:
    base = _iterate(100.0, 80.0, 1000.0)
    assert alg.converged(base, _iterate(100.5, 80.5, 1005.0))
    assert not alg.converged(base, _iterate(102.0, 80.0, 1000.0))
    assert not alg.converged(base, _iterate(100.0, 82.0, 1000.0))
    assert not alg.converged(base, _iterate(100.0, 80.0, 1020.0))
    assert not alg.converged(base, _iterate(100.0, 80.0, 1000.0, feasible=False))
    assert alg.converged(base, _iterate(101.5, 81.0, 1015.0), rel=0.02)
    assert alg.converged(_iterate(1.0, 1.0, None), _iterate(1.0, 1.0, None))
    assert not alg.converged(_iterate(1.0, 1.0, None), _iterate(1.0, 1.0, 0.0))


def test_cycle_detected() -> None:
    a, b = _iterate(100.0, 80.0, 1000.0), _iterate(120.0, 95.0, 1100.0)
    assert alg.cycle_detected([a, b, _iterate(100.2, 80.1, 1001.0)])
    assert not alg.cycle_detected([a, b])
    assert not alg.cycle_detected([a, b, _iterate(110.0, 88.0, 1050.0)])
    state = InterruptibleState(
        booked={"oil": {("B", 0): 100.0}},
        demand={"oil": {("B", 0): 150.0}},
        tranches={"oil": {("B", 0): 20.0}},
        history=[a, b, _iterate(100.0, 80.0, 1000.0)],
    )
    assert state.stop_reason() == "cycle"


def test_interruptible_state_validates_inputs() -> None:
    with pytest.raises(ValueError):
        InterruptibleState(booked={"oil": dict(BOOKED)}, demand={"gas": dict(DEMAND)})
    with pytest.raises(ValueError):
        InterruptibleState(booked={"oil": dict(BOOKED)}, demand={"oil": {("A", 0): 1.0}})


# --------------------------------------------------------------------------------------------
# Budget
# --------------------------------------------------------------------------------------------


def test_estimate_budget_matches_the_research_table() -> None:
    six = alg.estimate_budget(6)
    assert (six.screening, six.local, six.retries, six.interruptible) == (13, 18, 3, 4)
    assert six.confirmation == pytest.approx(9.9)
    assert round(six.total_search) == 44
    assert round(six.total) == 48
    assert 92 <= six.vm_hours_search <= six.vm_hours <= 101

    eight = alg.estimate_budget(8)
    assert (eight.screening, eight.local, eight.retries) == (17, 18, 4)
    assert round(eight.total_search) == 49
    assert round(eight.total) == 53
    assert 102 <= eight.vm_hours_search <= eight.vm_hours <= 112

    small = alg.estimate_budget(2, interruptible=0)
    assert small.local == 3 * 2 * 2
    assert small.total == small.total_search
    assert json.loads(json.dumps(six.to_dict()))["screening"] == 13
    with pytest.raises(ValueError):
        alg.estimate_budget(0)
