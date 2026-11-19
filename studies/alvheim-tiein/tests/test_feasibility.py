from __future__ import annotations

import pandas as pd

from alvheim_tiein import feasibility as fe


def test_solver_errors_match_solver_lines_only() -> None:
    lines = [
        "Step 3 done",
        "OpenServer error: GAP.SOLVENETWORK failed",
        "GAP optimiser error in network",
        "Run did not converge after 50 iterations",
        "retrying connection",
    ]
    assert fe.solver_errors(lines) == lines[1:4]


def test_missing_steps_ignores_time_of_day() -> None:
    results = pd.DataFrame({"timestamp": ["2027-01-01 00:00", "2027-02-01 06:00"]})
    expected = list(pd.date_range("2027-01-01", periods=3, freq="MS"))
    assert fe.missing_steps(results, expected) == [pd.Timestamp("2027-03-01")]


def test_window_share_of_the_m3_oscillation_window() -> None:
    delta = pd.Series(
        [1.0, -3.0, 4.0], index=pd.to_datetime(["2030-01-01", "2030-11-01", "2031-02-01"])
    )
    assert fe.window_share(delta) == 7 / 8
    assert fe.window_share(pd.Series(dtype=float)) == 0.0


def test_feasible_run_and_badges() -> None:
    f = fe.check(
        "S1",
        status="Completed",
        results=pd.DataFrame({"timestamp": ["2027-01-01"]}),
        expected_steps=[pd.Timestamp("2027-01-01")],
        violations=pd.DataFrame({"utilisation": [1.01]}),
        log_lines=["ok"],
        gain_by_period=pd.Series([1.0], index=pd.to_datetime(["2028-01-01"])),
    )
    assert f.feasible and not f.window_flag
    assert f.badges() == ["complete", "no solver errors", "within limits"]
    assert f.as_dict()["reasons"] == ""


def test_infeasible_reasons() -> None:
    f = fe.check(
        "S2",
        status="Failed",
        results=pd.DataFrame({"timestamp": ["2027-01-01"]}),
        expected_steps=list(pd.date_range("2027-01-01", periods=3, freq="MS")),
        violations=pd.DataFrame({"utilisation": [1.05, 1.10, 1.01]}),
        log_lines=["solver failed at step 2"],
        gain_by_period=pd.Series([1.0], index=pd.to_datetime(["2030-12-01"])),
    )
    assert not f.feasible and not f.complete and f.window_flag
    assert f.missing == 2 and f.violations == 2
    assert round(f.worst_violation, 6) == 0.10
    assert "status Failed" in f.reasons()[0]
    assert "gain mostly in the M3 window" in f.badges()
    assert len(fe.table([f])) == 1
