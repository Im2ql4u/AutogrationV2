"""Feasibility of a run: may it be scored? (research/22, gates 2 and 4)

A run that fails a check is *infeasible*: it is recorded but never scored or chosen.

- **complete**: the task finished and every expected step is in the results;
- **solver errors**: no solver or OpenServer error in the task logs;
- **violations**: no booking group more than 2 % above its applied limit at any step
  (:meth:`alvheim_tiein.bookings.BookingReport.violations`; gas only once lift gas is
  tracked).

The oscillation window (M3, Oct 2030 to Apr 2031) is not a failure; a gain that comes
mostly from inside it is flagged as untrusted (gate 4).
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

import pandas as pd

OSCILLATION_WINDOW = (pd.Timestamp("2030-10-01"), pd.Timestamp("2031-04-30"))
WINDOW_SHARE_LIMIT = 0.5
COMPLETED = "Completed"
_ERROR = re.compile(
    r"openserver error|solver (?:error|failed)|did not converge|failed to (?:solve|converge)"
    r"|optimi[sz]er error",
    re.IGNORECASE,
)


def solver_errors(lines: Iterable[str]) -> list[str]:
    """Log lines that report a solver or OpenServer error."""
    return [line for line in lines if _ERROR.search(str(line))]


def missing_steps(results: pd.DataFrame, expected: Sequence[pd.Timestamp]) -> list[pd.Timestamp]:
    have = set(pd.to_datetime(results["timestamp"]).dt.normalize()) if len(results) else set()
    return [pd.Timestamp(t) for t in expected if pd.Timestamp(t).normalize() not in have]


def window_share(
    delta: pd.Series, window: tuple[pd.Timestamp, pd.Timestamp] = OSCILLATION_WINDOW
) -> float:
    """Share of the absolute change (indexed by period) that falls inside ``window``."""
    if delta.empty:
        return 0.0
    periods = pd.to_datetime(pd.Series(delta.index, index=delta.index))
    inside = periods.between(window[0], window[1])
    total = float(delta.abs().sum())
    return float(delta[inside.to_numpy()].abs().sum()) / total if total > 0 else 0.0


@dataclass
class Feasibility:
    case: str
    status: str
    missing: int = 0
    errors: list[str] = field(default_factory=list)
    violations: int = 0
    worst_violation: float = 0.0
    """Largest produced/limit - 1 among violating steps."""
    window_share: float | None = None
    tol: float = 0.02

    @property
    def complete(self) -> bool:
        return self.status == COMPLETED and self.missing == 0

    @property
    def feasible(self) -> bool:
        return self.complete and not self.errors and self.violations == 0

    @property
    def window_flag(self) -> bool:
        return self.window_share is not None and self.window_share > WINDOW_SHARE_LIMIT

    def reasons(self) -> list[str]:
        out = []
        if self.status != COMPLETED:
            out.append(f"status {self.status}")
        if self.missing:
            out.append(f"{self.missing} step(s) missing")
        if self.errors:
            out.append(f"{len(self.errors)} solver error line(s)")
        if self.violations:
            out.append(
                f"{self.violations} step(s) above a group limit by more than {self.tol:.0%} "
                f"(worst +{self.worst_violation:.1%})"
            )
        return out

    def badges(self) -> list[str]:
        out = ["complete" if self.complete else "incomplete"]
        out.append("solver errors" if self.errors else "no solver errors")
        out.append(f"violations > {self.tol:.0%}" if self.violations else "within limits")
        if self.window_flag:
            out.append("gain mostly in the M3 window")
        return out

    def as_dict(self) -> dict[str, object]:
        return {
            "case": self.case,
            "feasible": self.feasible,
            "complete": self.complete,
            "status": self.status,
            "missing_steps": self.missing,
            "solver_errors": len(self.errors),
            "violations": self.violations,
            "worst_violation": self.worst_violation,
            "window_share": self.window_share,
            "window_flag": self.window_flag,
            "reasons": "; ".join(self.reasons()),
        }


def check(
    case: str,
    *,
    status: str,
    results: pd.DataFrame | None = None,
    expected_steps: Sequence[pd.Timestamp] | None = None,
    violations: pd.DataFrame | None = None,
    log_lines: Iterable[str] | None = None,
    gain_by_period: pd.Series | None = None,
    tol: float = 0.02,
) -> Feasibility:
    """Every check that has its input; missing inputs are not held against the run."""
    f = Feasibility(case=case, status=status, tol=tol)
    if results is not None and expected_steps is not None:
        f.missing = len(missing_steps(results, expected_steps))
    if log_lines is not None:
        f.errors = solver_errors(log_lines)
    if violations is not None and not violations.empty:
        v = violations
        if "utilisation" in v:
            v = v[v["utilisation"] > 1 + tol]
            f.worst_violation = float(v["utilisation"].max() - 1) if len(v) else 0.0
        f.violations = len(v)
    if gain_by_period is not None:
        f.window_share = window_share(gain_by_period)
    return f


def table(checks: Iterable[Feasibility]) -> pd.DataFrame:
    return pd.DataFrame([c.as_dict() for c in checks])
