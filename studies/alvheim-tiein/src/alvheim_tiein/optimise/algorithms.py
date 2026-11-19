"""Optimisation algorithms for the outer loop around Autogration runs (research/22).

Each evaluation is one full simulation (hours), the budget is tens of runs, the response is
discontinuous in places and some points are infeasible. So the search is staged:

1. **Screening** with a definitive screening design (:func:`definitive_screening`,
   :func:`screen`), which keeps the 2-3 levers that matter (:func:`active_levers`).
2. **Local search** on those levers with a MADS-style pattern search (:class:`PatternSearch`)
   that treats infeasible runs as a barrier.
3. **Confirmation** of the best points at full fidelity (done by the study driver).

Scheme 1c (firm plus interruptible capacity) is prototyped as an outer iteration of full runs:
:func:`next_tranches`, :func:`converged`, :func:`cycle_detected` and
:class:`InterruptibleState`. :func:`estimate_budget` reproduces the scheme 3 budget ledger.

Everything is pure Python (``math``, ``random``, ``itertools``) so it ports to a backend
without numpy or scipy. Randomness is seeded and derived per step, so a study is reproducible
and its state (``to_dict``/``from_dict``, JSON-safe) can be resumed across CLI calls.
"""

from __future__ import annotations

import copy
import itertools
import math
import random
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

# --------------------------------------------------------------------------------------------
# Constants (research/22, scheme 3 budget ledger and stop rules)
# --------------------------------------------------------------------------------------------

MH_HOURS = 2.1
"""Wall hours of one MH (fast-grid) run on a D4 VM."""
MONTHLY_HOURS = 7.0
"""Wall hours of one monthly run on a D4 VM."""
MH_PER_MONTHLY = 3.3
"""A monthly run in MH-equivalents (≈ 7 h / 2.1 h)."""
RETRY_FRACTION = 0.1
"""Share of screening and local-search runs that fail and are retried."""
CONFIRM_MONTHLY = 3
"""Monthly confirmation runs of the best feasible points."""
DEFAULT_ACTIVE_LEVERS = 3
"""Levers kept for the local search after screening."""
DEFAULT_POLLS = 3
"""Pattern-search polls budgeted per study."""

DEFAULT_MESH = 0.5
"""Initial pattern-search mesh size, in coded units (the box is [-1, 1] per lever)."""
MIN_MESH = 1.0 / 16.0
"""The search stops once the mesh is below this size."""
MAX_MESH = 1.0
"""The mesh never grows beyond this size."""
NO_IMPROVEMENT_POLLS = 2
"""Consecutive unsuccessful polls after which the search stops."""
KEY_DIGITS = 9
"""Coded coordinates are rounded to this many decimals to key the evaluation cache."""

MAX_ITERATIONS = 4
"""Interruptible-capacity iterations after the firm run."""
CONVERGENCE_REL = 0.01
"""Relative change in caps, rates and objective below which the iteration has converged."""

StopReason = Literal[
    "mesh_below_minimum", "budget_exhausted", "no_improvement", "cancelled", "wall_clock"
]
DriverStop = Literal["cancelled", "wall_clock"]
InterruptibleStop = Literal["converged", "cycle", "max_iterations"]

Point = dict[str, float]
Evaluation = tuple[Mapping[str, float], float | None, bool]
"""(point in lever units, value or None, feasible) as told to :meth:`PatternSearch.tell`."""

_ZERO_TOL = 1e-9


# --------------------------------------------------------------------------------------------
# Levers and the coded unit cube
# --------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Lever:
    """A named, bounded real parameter.

    The coded value u ∈ [-1, 1] maps linearly onto [lower, upper]:
    θ = c + u·h, with centre c = (lower + upper)/2 and half-range h = (upper − lower)/2.
    Designs and the pattern search work in coded units so all levers share one scale.

    ``baseline`` is the lever's default (today's value) and defaults to the centre.
    ``levels`` are the values :func:`grid` uses; without them the grid uses (lower, upper).
    """

    name: str
    lower: float
    upper: float
    baseline: float | None = None
    levels: tuple[float, ...] | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name:
            raise ValueError("a lever needs a non-empty name")
        lower, upper = float(self.lower), float(self.upper)
        if not (math.isfinite(lower) and math.isfinite(upper)) or not lower < upper:
            raise ValueError(
                f"lever {self.name!r}: need finite lower < upper, got {lower}, {upper}"
            )
        object.__setattr__(self, "lower", lower)
        object.__setattr__(self, "upper", upper)
        if self.baseline is not None:
            baseline = float(self.baseline)
            if not lower <= baseline <= upper:
                raise ValueError(f"lever {self.name!r}: baseline {baseline} outside its bounds")
            object.__setattr__(self, "baseline", baseline)
        if self.levels is not None:
            levels = tuple(float(v) for v in self.levels)
            if not levels:
                raise ValueError(f"lever {self.name!r}: levels must not be empty")
            if any(not lower <= v <= upper for v in levels):
                raise ValueError(f"lever {self.name!r}: a level is outside its bounds")
            if len(set(levels)) != len(levels):
                raise ValueError(f"lever {self.name!r}: duplicate levels")
            object.__setattr__(self, "levels", levels)

    @property
    def centre(self) -> float:
        """Midpoint of the bounds (coded 0)."""
        return 0.5 * (self.lower + self.upper)

    @property
    def half_range(self) -> float:
        """Half the width of the bounds (one coded unit)."""
        return 0.5 * (self.upper - self.lower)

    @property
    def default(self) -> float:
        """The baseline, or the centre when there is none."""
        return self.centre if self.baseline is None else self.baseline

    def clip(self, value: float) -> float:
        """``value`` clipped into [lower, upper]."""
        return min(max(float(value), self.lower), self.upper)

    def to_coded(self, value: float) -> float:
        """Coded value u = (θ − c)/h; inside the bounds u ∈ [-1, 1]."""
        return (float(value) - self.centre) / self.half_range

    def from_coded(self, coded: float) -> float:
        """Lever value θ = c + u·h, with u clipped into [-1, 1] (so ±1 give the exact bounds)."""
        u = float(coded)
        if u <= -1.0:
            return self.lower
        if u >= 1.0:
            return self.upper
        return self.clip(self.centre + u * self.half_range)

    def grid_levels(self) -> tuple[float, ...]:
        """The levels used by :func:`grid`."""
        return self.levels if self.levels is not None else (self.lower, self.upper)

    def to_dict(self) -> dict[str, Any]:
        """JSON-safe form."""
        return {
            "name": self.name,
            "lower": self.lower,
            "upper": self.upper,
            "baseline": self.baseline,
            "levels": None if self.levels is None else list(self.levels),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Lever:
        """Inverse of :meth:`to_dict`."""
        levels = data.get("levels")
        return cls(
            name=data["name"],
            lower=data["lower"],
            upper=data["upper"],
            baseline=data.get("baseline"),
            levels=None if levels is None else tuple(levels),
        )


def _check_levers(levers: Sequence[Lever]) -> tuple[Lever, ...]:
    result = tuple(levers)
    if not result:
        raise ValueError("need at least one lever")
    names = [lever.name for lever in result]
    if len(set(names)) != len(names):
        raise ValueError(f"duplicate lever names: {names}")
    return result


def to_coded(levers: Sequence[Lever], point: Mapping[str, float]) -> list[float]:
    """Map a point (lever name → value) to coded coordinates, in lever order."""
    return [lever.to_coded(point[lever.name]) for lever in levers]


def from_coded(levers: Sequence[Lever], coded: Sequence[float]) -> Point:
    """Map coded coordinates (in lever order) to a point; coordinates are clipped to [-1, 1]."""
    if len(coded) != len(levers):
        raise ValueError(f"expected {len(levers)} coordinates, got {len(coded)}")
    return {lever.name: lever.from_coded(u) for lever, u in zip(levers, coded, strict=True)}


def clip_point(levers: Sequence[Lever], point: Mapping[str, float]) -> Point:
    """Clip each lever's value into its bounds; keys that are not levers are dropped."""
    return {lever.name: lever.clip(point[lever.name]) for lever in levers}


def grid(levers: Sequence[Lever]) -> list[Point]:
    """Full factorial over each lever's levels (or [lower, upper] when it has none).

    Deterministic order: the first lever varies slowest (``itertools.product``).
    """
    checked = _check_levers(levers)
    names = [lever.name for lever in checked]
    return [
        dict(zip(names, values, strict=True))
        for values in itertools.product(*(lever.grid_levels() for lever in checked))
    ]


# --------------------------------------------------------------------------------------------
# Definitive screening
# --------------------------------------------------------------------------------------------


def is_prime(n: int) -> bool:
    """Trial-division primality test (n is small here)."""
    if n < 2:
        return False
    if n % 2 == 0:
        return n == 2
    return all(n % f for f in range(3, math.isqrt(n) + 1, 2))


def conference_matrix(n: int) -> list[list[int]]:
    """Paley conference matrix of order n, for n − 1 = q an odd prime.

    With χ the Legendre symbol mod q (χ(0) = 0, χ(a) = 1 if a is a non-zero square mod q,
    −1 otherwise), the Jacobsthal matrix Q_ij = χ(j − i) satisfies Q·Qᵀ = q·I − J and has
    zero row and column sums. Bordering it,

        C = [[0, 1ᵀ], [ε·1, Q]],   ε = χ(−1),

    gives a zero diagonal, ±1 elsewhere and CᵀC = (n − 1)·I. For q ≡ 1 (mod 4), ε = +1 and
    C is symmetric; for q ≡ 3 (mod 4), ε = −1 and C is antisymmetric.
    """
    q = n - 1
    if n % 2 or not is_prime(q) or q < 3:
        raise ValueError(f"Paley construction needs n even with n - 1 an odd prime, got n={n}")
    squares = {(x * x) % q for x in range(1, q)}

    def chi(a: int) -> int:
        a %= q
        if a == 0:
            return 0
        return 1 if a in squares else -1

    eps = chi(-1)
    rows = [[0] + [1] * q]
    rows.extend([eps] + [chi(j - i) for j in range(q)] for i in range(q))
    return rows


def screening_order(d: int) -> int:
    """Conference-matrix order for d levers: the smallest even n ≥ max(d, 4) with n − 1 prime."""
    if d < 1:
        raise ValueError("need at least one lever")
    n = max(d + d % 2, 4)
    while not is_prime(n - 1):
        n += 2
    return n


def screening_runs(d: int) -> int:
    """Runs in a definitive screening design for d levers: 2n + 1, n = :func:`screening_order`.

    That is 2d + 1 when d is even and d − 1 is prime (d = 4, 6, 8, 12, 14, ...).
    """
    return 2 * screening_order(d) + 1


@dataclass(frozen=True)
class ScreeningDesign:
    """A definitive screening design: coded rows (−1/0/+1) and the matching points."""

    names: tuple[str, ...]
    coded: tuple[tuple[int, ...], ...]
    points: tuple[Point, ...]
    order: int
    """Order n of the conference matrix the design was built from."""

    def to_dict(self) -> dict[str, Any]:
        """JSON-safe form."""
        return {
            "names": list(self.names),
            "coded": [list(row) for row in self.coded],
            "points": [dict(p) for p in self.points],
            "order": self.order,
        }


def definitive_screening(levers: Sequence[Lever]) -> ScreeningDesign:
    """Definitive screening design (Jones and Nachtsheim) for the levers.

    With C the conference matrix of order n = :func:`screening_order` (d), the design is the
    first d columns of the fold-over [C; −C; 0]: 2n + 1 runs, i.e. 2d + 1 when d is even and
    d − 1 is prime. Its columns are orthogonal (DᵀD = 2(n − 1)·I) and, by the fold-over, every
    main effect is orthogonal to the intercept, to every quadratic term and to every two-factor
    interaction, so main effects are unbiased by second-order terms. Each lever also sits at
    its centre in three runs, which gives an (indicative) curvature check.

    Coded −1/0/+1 map to lower/centre/upper of each lever.
    """
    checked = _check_levers(levers)
    d = len(checked)
    n = screening_order(d)
    c = conference_matrix(n)
    rows = [tuple(row[:d]) for row in c]
    rows += [tuple(-x for x in row[:d]) for row in c]
    rows.append(tuple(0 for _ in range(d)))
    points = tuple(from_coded(checked, row) for row in rows)
    return ScreeningDesign(
        names=tuple(lever.name for lever in checked), coded=tuple(rows), points=points, order=n
    )


@dataclass(frozen=True)
class LeverEffect:
    """Screening result for one lever (coded units).

    ``effect`` is the least-squares slope β per coded unit, so moving from lower to upper
    changes the response by 2β. ``curvature`` is mean(y | u = 0) − mean(y | u = ±1) over the
    feasible rows: positive suggests an interior maximum. In a definitive screening design it
    is confounded with the other levers' quadratic terms, so it is indicative only.
    ``best_level`` is the coded level (−1, 0 or +1 in a DSD) with the highest mean feasible
    response, a simple choice for fixing an inactive lever. ``rank`` 1 is the largest |β|.
    """

    name: str
    effect: float
    curvature: float | None
    best_level: float | None
    rank: int


@dataclass(frozen=True)
class ScreenResult:
    """Main effects of a screening design, in lever (column) order."""

    effects: tuple[LeverEffect, ...]
    intercept: float
    n_feasible: int
    n_rows: int
    method: Literal["orthogonal", "least_squares"]

    def ranked(self) -> list[LeverEffect]:
        """Effects by rank (largest |β| first)."""
        return sorted(self.effects, key=lambda e: e.rank)

    def by_name(self) -> dict[str, LeverEffect]:
        """Effects keyed by lever name."""
        return {e.name: e for e in self.effects}

    def to_dict(self) -> dict[str, Any]:
        """JSON-safe form."""
        return {
            "effects": [
                {
                    "name": e.name,
                    "effect": e.effect,
                    "curvature": e.curvature,
                    "best_level": e.best_level,
                    "rank": e.rank,
                }
                for e in self.effects
            ],
            "intercept": self.intercept,
            "n_feasible": self.n_feasible,
            "n_rows": self.n_rows,
            "method": self.method,
        }


def _mean(values: Sequence[float]) -> float:
    return math.fsum(values) / len(values)


def _solve(a: list[list[float]], b: list[float]) -> list[float]:
    """Solve a·x = b by Gaussian elimination with partial pivoting."""
    n = len(b)
    m = [list(row) + [rhs] for row, rhs in zip(a, b, strict=True)]
    scale = max((abs(x) for row in a for x in row), default=0.0)
    for col in range(n):
        pivot = col
        for r in range(col + 1, n):
            if abs(m[r][col]) > abs(m[pivot][col]):
                pivot = r
        if abs(m[pivot][col]) <= 1e-12 * scale:
            raise ValueError("singular system")
        m[col], m[pivot] = m[pivot], m[col]
        for r in range(col + 1, n):
            factor = m[r][col] / m[col][col]
            if factor:
                for c in range(col, n + 1):
                    m[r][c] -= factor * m[col][c]
    x = [0.0] * n
    for r in reversed(range(n)):
        x[r] = (m[r][n] - math.fsum(m[r][c] * x[c] for c in range(r + 1, n))) / m[r][r]
    return x


def _is_orthogonal(rows: Sequence[Sequence[float]]) -> bool:
    """Columns have zero sums and are mutually orthogonal (so the intercept separates too)."""
    d = len(rows[0])
    tol = _ZERO_TOL * len(rows)
    for j in range(d):
        if abs(math.fsum(r[j] for r in rows)) > tol:
            return False
        for k in range(j + 1, d):
            if abs(math.fsum(r[j] * r[k] for r in rows)) > tol:
                return False
    return True


def screen(
    coded: Sequence[Sequence[float]],
    responses: Sequence[float | None],
    feasible: Sequence[bool] | None = None,
    *,
    names: Sequence[str] | None = None,
) -> ScreenResult:
    """Main effects, curvature indicator and ranking per lever from a screening design.

    Model: y ≈ β₀ + Σ_j β_j·u_j, fitted by least squares on the feasible rows only (a row is
    used when it is feasible and its response is a finite number). When every row is used
    and the columns are orthogonal with zero sums (a complete DSD), the fit separates:
    β₀ = mean(y) and β_j = Σ u_j·y / Σ u_j². Otherwise the (d + 1)-square normal equations
    XᵀX·β = Xᵀy are solved. Lever names default to ``x1``, ``x2``, ...
    """
    rows = [[float(x) for x in row] for row in coded]
    if not rows:
        raise ValueError("empty design")
    d = len(rows[0])
    if d == 0 or any(len(row) != d for row in rows):
        raise ValueError("design rows must be non-empty and of equal length")
    m = len(rows)
    if len(responses) != m:
        raise ValueError(f"{m} design rows but {len(responses)} responses")
    flags = [True] * m if feasible is None else [bool(f) for f in feasible]
    if len(flags) != m:
        raise ValueError(f"{m} design rows but {len(flags)} feasibility flags")
    labels = [f"x{j + 1}" for j in range(d)] if names is None else list(names)
    if len(labels) != d:
        raise ValueError(f"{d} columns but {len(labels)} names")

    x: list[list[float]] = []
    y: list[float] = []
    for row, response, ok in zip(rows, responses, flags, strict=True):
        if ok and response is not None and math.isfinite(response):
            x.append(row)
            y.append(float(response))
    if len(y) < d + 1:
        raise ValueError(f"{len(y)} feasible rows cannot estimate {d} main effects")

    method: Literal["orthogonal", "least_squares"]
    if len(y) == m and _is_orthogonal(x):
        method = "orthogonal"
        intercept = _mean(y)
        beta: list[float] = []
        for j in range(d):
            ss = math.fsum(r[j] * r[j] for r in x)
            if ss == 0.0:
                raise ValueError(f"column {labels[j]!r} is constant")
            beta.append(math.fsum(r[j] * yi for r, yi in zip(x, y, strict=True)) / ss)
    else:
        method = "least_squares"
        design = [[1.0, *r] for r in x]
        xtx = [
            [math.fsum(row[a] * row[b] for row in design) for b in range(d + 1)]
            for a in range(d + 1)
        ]
        xty = [
            math.fsum(row[a] * yi for row, yi in zip(design, y, strict=True)) for a in range(d + 1)
        ]
        try:
            solution = _solve(xtx, xty)
        except ValueError as exc:
            raise ValueError("main effects are not identifiable from the feasible rows") from exc
        intercept, beta = solution[0], solution[1:]

    order = sorted(range(d), key=lambda j: (-abs(beta[j]), j))
    ranks = {j: r + 1 for r, j in enumerate(order)}
    effects: list[LeverEffect] = []
    for j in range(d):
        at_zero = [yi for r, yi in zip(x, y, strict=True) if abs(r[j]) <= _ZERO_TOL]
        off_zero = [yi for r, yi in zip(x, y, strict=True) if abs(r[j]) > _ZERO_TOL]
        curvature = _mean(at_zero) - _mean(off_zero) if at_zero and off_zero else None
        by_level: dict[float, list[float]] = {}
        for r, yi in zip(x, y, strict=True):
            by_level.setdefault(round(r[j], KEY_DIGITS) + 0.0, []).append(yi)
        best_level: float | None = None
        best_mean = -math.inf
        for level in sorted(by_level):
            level_mean = _mean(by_level[level])
            if level_mean > best_mean:
                best_level, best_mean = level, level_mean
        effects.append(LeverEffect(labels[j], beta[j], curvature, best_level, ranks[j]))
    return ScreenResult(tuple(effects), intercept, len(y), m, method)


def active_levers(screen_result: ScreenResult, k: int = DEFAULT_ACTIVE_LEVERS) -> list[str]:
    """Names of the k levers with the largest |main effect|, largest first."""
    if k < 1:
        raise ValueError("k must be at least 1")
    return [e.name for e in screen_result.ranked()[:k]]


def inactive_settings(
    screen_result: ScreenResult, levers: Sequence[Lever], k: int = DEFAULT_ACTIVE_LEVERS
) -> Point:
    """Values to fix the levers outside the top k at: their best screened level, else default."""
    active = set(active_levers(screen_result, k))
    effects = screen_result.by_name()
    settings: Point = {}
    for lever in levers:
        if lever.name in active:
            continue
        effect = effects.get(lever.name)
        if effect is None or effect.best_level is None:
            settings[lever.name] = lever.default
        else:
            settings[lever.name] = lever.from_coded(effect.best_level)
    return settings


# --------------------------------------------------------------------------------------------
# Pattern search
# --------------------------------------------------------------------------------------------

_Key = tuple[float, ...]
_StepKind = Literal["init", "poll", "search"]


def _round_key(coords: Iterable[float]) -> _Key:
    # Adding 0.0 turns -0.0 into 0.0, so keys serialise the same way they compare.
    return tuple(round(c, KEY_DIGITS) + 0.0 for c in coords)


class PatternSearch:
    """MADS-style generalised pattern search, maximising over a box with an extreme barrier.

    The search works in coded units (each lever's box is [-1, 1]) on a mesh of size Δ.

    * **Poll.** Around the incumbent x, propose x ± Δ·dᵢ for the columns dᵢ of an orthogonal
      basis D, i.e. the 2k points of the positive spanning set [D, −D]. D is a signed
      permutation of the axes drawn afresh per poll from a generator seeded by
      (seed, draw count), so the order of the proposals, which matters when a wave is cut by
      the budget, is random but reproducible. Points are clipped to the box and points
      already evaluated are not proposed again: their cached values are reused.
    * **Update.** Maximisation. A poll is successful if a feasible point beats the incumbent
      by more than ``min_improvement`` (absolute); the best such point becomes the incumbent
      and Δ doubles (capped at ``max_mesh``). Otherwise Δ halves.
    * **Barrier.** Infeasible points, and points without a value (failed runs), are recorded
      and never become the incumbent; since they are cached they are never proposed again.

    Usage: call :meth:`poll` for points to run and :meth:`tell` with the results, until
    :meth:`stop_reason` is not None. Until the first feasible incumbent exists, the first
    poll proposes the start point; points told outside a poll (e.g. observations reused from
    screening) are a "search" step that may move the incumbent but leaves the mesh alone.
    A poll is resolved once all its points have results, so results may arrive one at a
    time; until then :meth:`poll` returns the points still outstanding.
    """

    def __init__(
        self,
        levers: Sequence[Lever],
        *,
        start: Mapping[str, float] | None = None,
        seed: int = 0,
        mesh: float = DEFAULT_MESH,
        min_mesh: float = MIN_MESH,
        max_mesh: float = MAX_MESH,
        budget: int | None = None,
        min_improvement: float = 0.0,
        max_unsuccessful_polls: int | None = NO_IMPROVEMENT_POLLS,
    ) -> None:
        self.levers = _check_levers(levers)
        if not 0.0 < min_mesh <= mesh <= max_mesh:
            raise ValueError("need 0 < min_mesh <= mesh <= max_mesh")
        if budget is not None and budget < 1:
            raise ValueError("budget must be at least 1 evaluation")
        if min_improvement < 0.0 or not math.isfinite(min_improvement):
            raise ValueError("min_improvement must be finite and non-negative")
        if max_unsuccessful_polls is not None and max_unsuccessful_polls < 1:
            raise ValueError("max_unsuccessful_polls must be at least 1 (or None)")
        self.seed = int(seed)
        self.mesh = float(mesh)
        self.min_mesh = float(min_mesh)
        self.max_mesh = float(max_mesh)
        self.budget = budget
        self.min_improvement = float(min_improvement)
        self.max_unsuccessful_polls = max_unsuccessful_polls
        start_point = {lv.name: lv.default for lv in self.levers} if start is None else start
        self._start = self._key(start_point)
        self._incumbent: _Key | None = None
        self._incumbent_value: float | None = None
        self._cache: dict[_Key, tuple[float | None, bool]] = {}
        self._pending: list[_Key] | None = None
        self._pending_kind: _StepKind | None = None
        self._told: list[_Key] = []
        self._forced_stop: DriverStop | None = None
        self.step = 0
        self.draws = 0
        self.n_evaluations = 0
        self.n_polls = 0
        self.n_successes = 0
        self.n_reused = 0
        self.unsuccessful_streak = 0
        self.history: list[dict[str, Any]] = []

    # -- coordinates -------------------------------------------------------------------------

    def _key(self, point: Mapping[str, float]) -> _Key:
        coords = []
        for lever in self.levers:
            if lever.name not in point:
                raise KeyError(f"point has no value for lever {lever.name!r}")
            u = lever.to_coded(point[lever.name])
            if not math.isfinite(u) or abs(u) > 1.0 + _ZERO_TOL:
                raise ValueError(f"{lever.name}={point[lever.name]} is outside the lever's bounds")
            coords.append(min(max(u, -1.0), 1.0))
        return _round_key(coords)

    def _point(self, key: _Key) -> Point:
        return from_coded(self.levers, key)

    # -- public state ------------------------------------------------------------------------

    @property
    def dimension(self) -> int:
        """Number of levers searched."""
        return len(self.levers)

    @property
    def incumbent(self) -> Point | None:
        """Best feasible point so far (in lever units), or None."""
        return None if self._incumbent is None else self._point(self._incumbent)

    @property
    def incumbent_value(self) -> float | None:
        """Value at the incumbent, or None."""
        return self._incumbent_value

    @property
    def start(self) -> Point:
        """The start point (clipped to the box)."""
        return self._point(self._start)

    def evaluations(self) -> list[tuple[Point, float | None, bool]]:
        """Every evaluated point with its value and feasibility, in the order first told."""
        return [(self._point(k), v, f) for k, (v, f) in self._cache.items()]

    def is_evaluated(self, point: Mapping[str, float]) -> bool:
        """Whether the point (rounded to the cache key) has a result."""
        return self._key(point) in self._cache

    def cached_value(self, point: Mapping[str, float]) -> tuple[float | None, bool] | None:
        """(value, feasible) for an evaluated point, else None."""
        return self._cache.get(self._key(point))

    # -- stop rules --------------------------------------------------------------------------

    def stop(self, reason: DriverStop) -> None:
        """Stop on the driver's behalf: "cancelled" by the user or "wall_clock" limit reached."""
        if reason not in ("cancelled", "wall_clock"):
            raise ValueError(f"the driver can only stop with 'cancelled' or 'wall_clock': {reason}")
        self._forced_stop = reason
        self.history.append({"event": "stop", "step": self.step, "reason": reason})

    def stop_reason(self) -> StopReason | None:
        """Why the search has stopped, or None while it should continue.

        Order: driver stop, "budget_exhausted" (evaluations told ≥ budget),
        "mesh_below_minimum" (Δ < min_mesh), "no_improvement" (``max_unsuccessful_polls``
        consecutive polls without an improvement above ``min_improvement``).
        """
        if self._forced_stop is not None:
            return self._forced_stop
        if self.budget is not None and self.n_evaluations >= self.budget:
            return "budget_exhausted"
        if self.mesh < self.min_mesh:
            return "mesh_below_minimum"
        if (
            self.max_unsuccessful_polls is not None
            and self.unsuccessful_streak >= self.max_unsuccessful_polls
        ):
            return "no_improvement"
        return None

    # -- ask / tell --------------------------------------------------------------------------

    def _basis(self) -> list[tuple[int, int]]:
        rng = random.Random(f"pattern-search:{self.seed}:{self.draws}")
        self.draws += 1
        axes = list(range(self.dimension))
        rng.shuffle(axes)
        return [(axis, rng.choice((-1, 1))) for axis in axes]

    def poll(self) -> list[Point]:
        """Points to evaluate next (lever units); empty once the search has stopped.

        Proposes nothing that has been evaluated. A poll whose points are all cached is
        resolved at once from the cache and the next poll is drawn.
        """
        if self.stop_reason() is not None:
            return []
        if self._pending is not None:
            return [self._point(k) for k in self._pending if k not in self._cache]
        if self._incumbent is None and self._start not in self._cache:
            self._propose("init", [self._start], [], None, None)
            return [self._point(self._start)]
        while self.stop_reason() is None:
            centre = self._incumbent if self._incumbent is not None else self._start
            draw = self.draws
            basis = self._basis()
            directions = basis + [(axis, -sign) for axis, sign in basis]
            new: list[_Key] = []
            reused: list[_Key] = []
            seen = {centre}
            for axis, sign in directions:
                coords = list(centre)
                coords[axis] = min(max(coords[axis] + sign * self.mesh, -1.0), 1.0)
                key = _round_key(coords)
                if key in seen:
                    continue
                seen.add(key)
                (reused if key in self._cache else new).append(key)
            if self.budget is not None:
                new = new[: max(0, self.budget - self.n_evaluations)]
            self.n_reused += len(reused)
            self._propose("poll", new, reused, centre, draw)
            if new:
                return [self._point(k) for k in new]
            self._resolve()
        return []

    def _propose(
        self,
        kind: _StepKind,
        new: list[_Key],
        reused: list[_Key],
        centre: _Key | None,
        draw: int | None,
    ) -> None:
        self._pending, self._pending_kind = new + reused, kind
        self.history.append(
            {
                "event": "propose",
                "step": self.step,
                "kind": kind,
                "draw": draw,
                "mesh": self.mesh,
                "centre": None if centre is None else self._point(centre),
                "points": [self._point(k) for k in new],
                "reused": [self._point(k) for k in reused],
            }
        )

    def tell(self, evaluations: Iterable[Evaluation]) -> None:
        """Record results: (point, value or None, feasible).

        A value that is None or not finite is recorded as infeasible. Re-telling a point
        overwrites an infeasible or failed result (a retry); a different result for a
        feasible point raises, since runs are deterministic. The open poll is resolved once
        all its points have results; results outside a poll form a "search" step.
        """
        told_any = False
        for point, value, feasible in evaluations:
            key = self._key(point)
            val = None if value is None or not math.isfinite(value) else float(value)
            ok = bool(feasible) and val is not None
            previous = self._cache.get(key)
            if previous is not None and previous[1] and (not ok or previous[0] != val):
                raise ValueError(
                    f"conflicting result for {self._point(key)}: had {previous[0]}, got {val}"
                )
            self._cache[key] = (val, ok)
            self.n_evaluations += 1
            self._told.append(key)
            told_any = True
            self.history.append(
                {
                    "event": "evaluate",
                    "step": self.step,
                    "point": self._point(key),
                    "value": val,
                    "feasible": ok,
                }
            )
        if self._pending is None:
            if told_any:
                self._pending_kind = "init" if self._incumbent is None else "search"
                self._pending = []
                self._resolve()
        elif all(k in self._cache for k in self._pending):
            self._resolve()

    def _resolve(self) -> None:
        kind = self._pending_kind or "search"
        keys = list(dict.fromkeys([*(self._pending or []), *self._told]))
        best_key: _Key | None = None
        best_value: float | None = None
        for key in keys:
            value, ok = self._cache[key]
            if ok and value is not None and (best_value is None or value > best_value):
                best_key, best_value = key, value
        improved = best_value is not None and (
            self._incumbent_value is None
            or best_value > self._incumbent_value + self.min_improvement
        )
        mesh_before = self.mesh
        if improved:
            self._incumbent, self._incumbent_value = best_key, best_value
            self.unsuccessful_streak = 0
        if kind == "poll":
            self.n_polls += 1
            if improved:
                self.n_successes += 1
                self.mesh = min(2.0 * self.mesh, self.max_mesh)
            else:
                self.mesh = 0.5 * self.mesh
                self.unsuccessful_streak += 1
        self.history.append(
            {
                "event": "resolve",
                "step": self.step,
                "kind": kind,
                "success": improved,
                "mesh_before": mesh_before,
                "mesh_after": self.mesh,
                "incumbent": self.incumbent,
                "incumbent_value": self._incumbent_value,
            }
        )
        self.step += 1
        self._pending, self._pending_kind, self._told = None, None, []

    # -- persistence -------------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """JSON-safe state, enough to resume the search exactly (see :meth:`from_dict`)."""
        return {
            "version": 1,
            "levers": [lever.to_dict() for lever in self.levers],
            "seed": self.seed,
            "mesh": self.mesh,
            "min_mesh": self.min_mesh,
            "max_mesh": self.max_mesh,
            "budget": self.budget,
            "min_improvement": self.min_improvement,
            "max_unsuccessful_polls": self.max_unsuccessful_polls,
            "start": list(self._start),
            "incumbent": None if self._incumbent is None else list(self._incumbent),
            "incumbent_value": self._incumbent_value,
            "cache": [
                {"coded": list(k), "value": v, "feasible": f} for k, (v, f) in self._cache.items()
            ],
            "pending": None if self._pending is None else [list(k) for k in self._pending],
            "pending_kind": self._pending_kind,
            "told": [list(k) for k in self._told],
            "forced_stop": self._forced_stop,
            "step": self.step,
            "draws": self.draws,
            "n_evaluations": self.n_evaluations,
            "n_polls": self.n_polls,
            "n_successes": self.n_successes,
            "n_reused": self.n_reused,
            "unsuccessful_streak": self.unsuccessful_streak,
            "history": copy.deepcopy(self.history),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> PatternSearch:
        """Rebuild a search from :meth:`to_dict` output (e.g. after a JSON round trip)."""
        if data.get("version") != 1:
            raise ValueError(f"unsupported pattern-search state version {data.get('version')}")
        levers = [Lever.from_dict(lv) for lv in data["levers"]]
        search = cls(
            levers,
            seed=data["seed"],
            mesh=data["min_mesh"],
            min_mesh=data["min_mesh"],
            max_mesh=data["max_mesh"],
            budget=data["budget"],
            min_improvement=data["min_improvement"],
            max_unsuccessful_polls=data["max_unsuccessful_polls"],
        )

        def key(values: Iterable[float]) -> _Key:
            return tuple(float(v) for v in values)

        search.mesh = float(data["mesh"])
        search._start = key(data["start"])
        search._incumbent = None if data["incumbent"] is None else key(data["incumbent"])
        value = data["incumbent_value"]
        search._incumbent_value = None if value is None else float(value)
        search._cache = {
            key(e["coded"]): (None if e["value"] is None else float(e["value"]), e["feasible"])
            for e in data["cache"]
        }
        pending = data["pending"]
        search._pending = None if pending is None else [key(k) for k in pending]
        search._pending_kind = data["pending_kind"]
        search._told = [key(k) for k in data["told"]]
        search._forced_stop = data["forced_stop"]
        search.step = int(data["step"])
        search.draws = int(data["draws"])
        search.n_evaluations = int(data["n_evaluations"])
        search.n_polls = int(data["n_polls"])
        search.n_successes = int(data["n_successes"])
        search.n_reused = int(data["n_reused"])
        search.unsuccessful_streak = int(data["unsuccessful_streak"])
        search.history = copy.deepcopy(list(data["history"]))
        return search


# --------------------------------------------------------------------------------------------
# Interruptible capacity (scheme 1c prototype: an outer iteration of full runs)
# --------------------------------------------------------------------------------------------

Period = int | str
Key = tuple[str, Period]
"""(group, period) for one phase."""
Rates = Mapping[Key, float]


def _require(name: str, data: Rates, keys: Iterable[Key]) -> None:
    missing = [k for k in keys if k not in data]
    if missing:
        raise ValueError(
            f"{name} has no value for {missing[:5]}{'...' if len(missing) > 5 else ''}"
        )


def _periods(booked: Rates) -> dict[Period, list[str]]:
    by_period: dict[Period, list[str]] = {}
    for group, period in booked:
        by_period.setdefault(period, []).append(group)
    return by_period


def caps(booked: Rates, tranches: Rates) -> dict[Key, float]:
    """Caps for the next run: firm booking plus borrowed tranche, B + b (firm never lowered)."""
    return {k: b + max(0.0, tranches.get(k, 0.0)) for k, b in booked.items()}


def spare_capacity(booked: Rates, used: Rates) -> dict[Period, float]:
    """Booked capacity left unused per period: Σ_h max(0, B_h(t) − q_h(t))."""
    _require("used", used, booked)
    spare: dict[Period, float] = {}
    for (group, period), b in booked.items():
        spare[period] = spare.get(period, 0.0) + max(0.0, b - used[(group, period)])
    return spare


def unmet_demand(booked: Rates, demand: Rates) -> dict[Key, float]:
    """Unmet demand under the firm rule, (d_g − B_g)⁺, with d the uncapped (lift-all) rate."""
    _require("demand", demand, booked)
    return {k: max(0.0, demand[k] - b) for k, b in booked.items()}


def recipients(
    booked: Rates, used: Rates, demand: Rates, tranches: Rates, *, tol: float = 0.01
) -> list[Key]:
    """Groups at their cap with unmet demand, in booking order.

    At the cap: q_g ≥ B_g·(1 − tol) + b_g, with b_g the tranche of the run that gave q.
    Unmet demand: d_g − B_g > tol·B_g, with d the uncapped (lift-all) rate.
    """
    _require("used", used, booked)
    _require("demand", demand, booked)
    result = []
    for k, b in booked.items():
        tranche = max(0.0, tranches.get(k, 0.0))
        at_cap = used[k] >= b * (1.0 - tol) + tranche
        if at_cap and demand[k] - b > tol * b:
            result.append(k)
    return result


def raw_tranches(
    booked: Rates, used: Rates, demand: Rates, tranches: Rates, *, tol: float = 0.01
) -> dict[Key, float]:
    """Undamped target tranches b̂: the spare capacity shared pro rata to unmet demand.

    Per period t with spare S(t) and recipients R(t) with unmet demand u_g = (d_g − B_g)⁺,
    b̂_g = u_g·min(1, S/Σ_R u): the shares sum to at most S and no recipient gets more than
    its unmet demand (it can't produce more). Other groups get 0.
    """
    spare = spare_capacity(booked, used)
    unmet = unmet_demand(booked, demand)
    receiving = recipients(booked, used, demand, tranches, tol=tol)
    total_unmet: dict[Period, float] = {}
    for group, period in receiving:
        total_unmet[period] = total_unmet.get(period, 0.0) + unmet[(group, period)]
    raw = dict.fromkeys(booked, 0.0)
    for group, period in receiving:
        u_total = total_unmet[period]
        if u_total > 0.0:
            raw[(group, period)] = unmet[(group, period)] * min(1.0, spare[period] / u_total)
    return raw


def recall_shortfall(
    booked: Rates,
    used_prev: Rates,
    used_firm: Rates,
    receiving: Iterable[Key],
    *,
    tol: float = 0.01,
) -> dict[Period, float]:
    """Capacity to recall per period: Σ over non-recipients of their shortfall to the firm run.

    A group h that is not a recipient at t is short when q_h(t) < q_h⁰(t)·(1 − tol), with q⁰
    the firm run; its shortfall is q_h⁰(t) − q_h(t).
    """
    _require("used_prev", used_prev, booked)
    _require("used_firm", used_firm, booked)
    skip = set(receiving)
    shortfall = dict.fromkeys(_periods(booked), 0.0)
    for k in booked:
        if k in skip:
            continue
        firm, now = used_firm[k], used_prev[k]
        if now < firm * (1.0 - tol):
            shortfall[k[1]] += firm - now
    return shortfall


def next_tranches(
    booked: Rates,
    used_prev: Rates,
    used_firm: Rates,
    demand: Rates,
    tranches_prev: Rates,
    *,
    damping: float = 0.5,
    tol: float = 0.01,
) -> dict[Key, float]:
    """Borrowed tranches b(t) for the next iteration of one phase.

    1. Raw target b̂ (:func:`raw_tranches`): the previous run's spare capacity
       S(t) = Σ_h max(0, B_h − q_h), shared over the groups at their cap pro rata to unmet
       demand (d_g − B_g)⁺, never more than it.
    2. Damping: b = damping·b_prev + (1 − damping)·b̂.
    3. Recall: if non-recipients fell short of their firm-run rates at t (beyond ``tol``,
       relative), the tranches at t are cut by that shortfall R(t), pro rata to tranche size:
       b_g ← b_g·(1 − min(1, R/Σ b)).

    Keys are (group, period) for the booked groups; ``tranches_prev`` may omit zeros. The firm
    bookings are inputs only: caps for the run are B + b with b ≥ 0 (:func:`caps`).
    """
    if not 0.0 <= damping <= 1.0:
        raise ValueError("damping must be in [0, 1]")
    if tol < 0.0:
        raise ValueError("tol must be non-negative")
    receiving = recipients(booked, used_prev, demand, tranches_prev, tol=tol)
    raw = raw_tranches(booked, used_prev, demand, tranches_prev, tol=tol)
    damped = {
        k: damping * max(0.0, tranches_prev.get(k, 0.0)) + (1.0 - damping) * raw[k] for k in booked
    }
    shortfall = recall_shortfall(booked, used_prev, used_firm, receiving, tol=tol)
    held: dict[Period, float] = {}
    for (_, period), b in damped.items():
        held[period] = held.get(period, 0.0) + b
    result: dict[Key, float] = {}
    for k, b in damped.items():
        total = held[k[1]]
        cut = shortfall[k[1]]
        result[k] = b * (1.0 - min(1.0, cut / total)) if total > 0.0 and cut > 0.0 else b
    return result


PhaseRates = Mapping[str, Mapping[Key, float]]
"""phase → (group, period) → value."""


@dataclass(frozen=True)
class Iterate:
    """One run of the interruptible iteration: the caps applied, the rates it gave, its value.

    Iterate 0 is the firm run (caps = bookings).
    """

    caps: PhaseRates
    rates: PhaseRates
    objective: float | None = None
    feasible: bool = True


def _close_mapping(a: Mapping[Key, float], b: Mapping[Key, float], rel: float) -> bool:
    keys = set(a) | set(b)
    scale = max((abs(v) for v in itertools.chain(a.values(), b.values())), default=0.0)
    return all(abs(a.get(k, 0.0) - b.get(k, 0.0)) <= rel * scale for k in keys)


def _close_phases(a: PhaseRates, b: PhaseRates, rel: float) -> bool:
    if set(a) != set(b):
        return False
    return all(_close_mapping(a[p], b[p], rel) for p in a)


def _close_objective(a: float | None, b: float | None, rel: float) -> bool:
    if a is None or b is None:
        return a is None and b is None
    return abs(a - b) <= rel * max(abs(a), abs(b))


def _iterates_close(a: Iterate, b: Iterate, rel: float) -> bool:
    return (
        _close_phases(a.caps, b.caps, rel)
        and _close_phases(a.rates, b.rates, rel)
        and _close_objective(a.objective, b.objective, rel)
    )


def converged(prev: Iterate, cur: Iterate, rel: float = CONVERGENCE_REL) -> bool:
    """Both iterates feasible and caps, rates and objective changed by less than ``rel``.

    Caps and rates compare per phase in the max norm relative to that phase's largest value,
    |x_k − y_k| ≤ rel·max_j |·|, so tiny rates don't dominate; the objective compares as
    |a − b| ≤ rel·max(|a|, |b|).
    """
    return prev.feasible and cur.feasible and _iterates_close(prev, cur, rel)


def cycle_detected(history: Sequence[Iterate], rel: float = CONVERGENCE_REL) -> bool:
    """Iterate k is within ``rel`` of iterate k − 2 (a two-cycle), with k the latest."""
    return len(history) >= 3 and _iterates_close(history[-3], history[-1], rel)


def _encode(rates: PhaseRates) -> dict[str, list[list[Any]]]:
    return {phase: [[g, t, v] for (g, t), v in m.items()] for phase, m in rates.items()}


def _decode(data: Mapping[str, Sequence[Sequence[Any]]]) -> dict[str, dict[Key, float]]:
    return {phase: {(g, t): float(v) for g, t, v in rows} for phase, rows in data.items()}


@dataclass
class InterruptibleState:
    """State of the firm-plus-interruptible outer iteration (scheme 1c prototype).

    Record the firm run first (iterate 0, caps = bookings), then each interruptible run
    with :meth:`record`; after each, the tranches for the next run are recomputed per phase
    with :func:`next_tranches`. ``iteration`` counts the interruptible runs recorded.

    Stop reasons: "converged" when the last two iterates are within ``rel``, or when the
    next caps equal the caps just run (a fixed point: the next run would repeat it);
    "cycle" when iterate k ≈ k − 2; "max_iterations" after ``max_iterations`` runs. When not
    converged the study reports the last feasible iterate (:meth:`last_feasible`).
    """

    booked: dict[str, dict[Key, float]]
    demand: dict[str, dict[Key, float]]
    damping: float = 0.5
    tol: float = 0.01
    rel: float = CONVERGENCE_REL
    max_iterations: int = MAX_ITERATIONS
    tranches: dict[str, dict[Key, float]] = field(default_factory=dict)
    history: list[Iterate] = field(default_factory=list)

    def __post_init__(self) -> None:
        if set(self.demand) != set(self.booked):
            raise ValueError("booked and demand must have the same phases")
        for phase, booked in self.booked.items():
            _require(f"demand[{phase!r}]", self.demand[phase], booked)
        for phase in self.booked:
            self.tranches.setdefault(phase, dict.fromkeys(self.booked[phase], 0.0))

    @property
    def iteration(self) -> int:
        """Interruptible runs recorded (the firm run is iteration 0)."""
        return max(0, len(self.history) - 1)

    def caps(self) -> dict[str, dict[Key, float]]:
        """Caps for the next run, per phase: B + b."""
        return {phase: caps(b, self.tranches[phase]) for phase, b in self.booked.items()}

    def record(
        self, rates: PhaseRates, objective: float | None = None, *, feasible: bool = True
    ) -> None:
        """Record the run made with :meth:`caps` and compute the next tranches."""
        if self.history and self.stop_reason() is not None:
            raise RuntimeError(f"iteration has stopped: {self.stop_reason()}")
        rates_copy = {phase: dict(rates[phase]) for phase in self.booked}
        self.history.append(Iterate(self.caps(), rates_copy, objective, feasible))
        firm = self.history[0].rates
        self.tranches = {
            phase: next_tranches(
                booked,
                rates_copy[phase],
                firm[phase],
                self.demand[phase],
                self.tranches[phase],
                damping=self.damping,
                tol=self.tol,
            )
            for phase, booked in self.booked.items()
        }

    def stop_reason(self) -> InterruptibleStop | None:
        """The stop reason ("converged", "cycle", "max_iterations") or None; see the class."""
        if not self.history:
            return None
        last = self.history[-1]
        if len(self.history) >= 2 and converged(self.history[-2], last, self.rel):
            return "converged"
        if last.feasible and _close_phases(last.caps, self.caps(), self.rel):
            return "converged"
        if cycle_detected(self.history, self.rel):
            return "cycle"
        if self.iteration >= self.max_iterations:
            return "max_iterations"
        return None

    def last_feasible(self) -> Iterate | None:
        """The latest feasible iterate, or None."""
        return next((it for it in reversed(self.history) if it.feasible), None)

    def to_dict(self) -> dict[str, Any]:
        """JSON-safe state; keys (group, period) become [group, period, value] rows."""
        return {
            "version": 1,
            "booked": _encode(self.booked),
            "demand": _encode(self.demand),
            "damping": self.damping,
            "tol": self.tol,
            "rel": self.rel,
            "max_iterations": self.max_iterations,
            "tranches": _encode(self.tranches),
            "history": [
                {
                    "caps": _encode(it.caps),
                    "rates": _encode(it.rates),
                    "objective": it.objective,
                    "feasible": it.feasible,
                }
                for it in self.history
            ],
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> InterruptibleState:
        """Inverse of :meth:`to_dict`."""
        if data.get("version") != 1:
            raise ValueError(f"unsupported interruptible state version {data.get('version')}")
        return cls(
            booked=_decode(data["booked"]),
            demand=_decode(data["demand"]),
            damping=float(data["damping"]),
            tol=float(data["tol"]),
            rel=float(data["rel"]),
            max_iterations=int(data["max_iterations"]),
            tranches=_decode(data["tranches"]),
            history=[
                Iterate(
                    caps=_decode(it["caps"]),
                    rates=_decode(it["rates"]),
                    objective=None if it["objective"] is None else float(it["objective"]),
                    feasible=bool(it["feasible"]),
                )
                for it in data["history"]
            ],
        )


# --------------------------------------------------------------------------------------------
# Budget
# --------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class BudgetEstimate:
    """Scheme 3 budget ledger in MH-equivalent runs (a monthly run ≈ ``mh_per_monthly`` MH).

    ``total`` includes the interruptible iterations, ``total_search`` leaves them out; the
    research/22 table quotes the range total_search–total (d = 6: ≈ 44–48, d = 8: ≈ 49–53).
    VM-hours are MH-equivalents × MH hours.
    """

    levers: int
    screening: int
    local: int
    retries: int
    interruptible: int
    confirmation: float
    total_search: float
    total: float
    vm_hours_search: float
    vm_hours: float

    def to_dict(self) -> dict[str, Any]:
        """JSON-safe form."""
        return {
            "levers": self.levers,
            "screening": self.screening,
            "local": self.local,
            "retries": self.retries,
            "interruptible": self.interruptible,
            "confirmation": self.confirmation,
            "total_search": self.total_search,
            "total": self.total,
            "vm_hours_search": self.vm_hours_search,
            "vm_hours": self.vm_hours,
        }


def estimate_budget(
    d: int,
    *,
    local_levers: int = DEFAULT_ACTIVE_LEVERS,
    polls: int = DEFAULT_POLLS,
    retry_fraction: float = RETRY_FRACTION,
    confirm_monthly: int = CONFIRM_MONTHLY,
    mh_per_monthly: float = MH_PER_MONTHLY,
    interruptible: int = MAX_ITERATIONS,
    mh_hours: float = MH_HOURS,
) -> BudgetEstimate:
    """Runs needed for a d-lever study, in MH-equivalents.

    * screening: :func:`screening_runs` (d) = 2d + 1 for d = 6 or 8;
    * local search: polls × 2k with k = min(local_levers, d) (a poll is 2k points);
    * retries: retry_fraction × (screening + local), rounded half up;
    * interruptible iterations: at most ``interruptible`` MH runs;
    * confirmation: confirm_monthly × mh_per_monthly.
    """
    if d < 1:
        raise ValueError("need at least one lever")
    if local_levers < 1 or polls < 0 or retry_fraction < 0 or confirm_monthly < 0:
        raise ValueError("budget parameters must be non-negative (local_levers >= 1)")
    screening = screening_runs(d)
    local = polls * 2 * min(local_levers, d)
    retries = math.floor(retry_fraction * (screening + local) + 0.5)
    confirmation = confirm_monthly * mh_per_monthly
    total_search = screening + local + retries + confirmation
    total = total_search + interruptible
    return BudgetEstimate(
        levers=d,
        screening=screening,
        local=local,
        retries=retries,
        interruptible=interruptible,
        confirmation=confirmation,
        total_search=total_search,
        total=total,
        vm_hours_search=total_search * mh_hours,
        vm_hours=total * mh_hours,
    )
