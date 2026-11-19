from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from alvheim_tiein.results import (
    SM3_PER_BBL,
    export_workbench_folder,
    period_volumes,
    volume_convention_check,
)
from tests.conftest import result_rows


def test_period_volumes_uses_days_to_next_step_and_calendar_month_at_end() -> None:
    df = pd.DataFrame(result_rows("c", "W", [10.0, 20.0, 30.0]))  # Jan, Feb, Mar 2027
    vol = period_volumes(df)
    assert vol["days"].tolist() == [31.0, 28.0, 31.0]
    assert vol["oil_sm3"].tolist() == [310.0, 560.0, 930.0]
    assert vol["gas_sm3"].eq(0).all() and vol["water_sm3"].eq(0).all()


def test_period_volumes_prefers_average_rates_and_converts_units() -> None:
    rows = result_rows("c", "W", [100.0, 100.0], unit="STB/day")
    rows += result_rows("c", "W", [999.0, 999.0], prop="OilRate")
    vol = period_volumes(pd.DataFrame(rows))
    assert vol["oil_sm3"].iloc[0] == pytest.approx(100 * SM3_PER_BBL * 31)


def test_period_volumes_drops_sentinels_and_rejects_unknown_units() -> None:
    vol = period_volumes(pd.DataFrame(result_rows("c", "W", [3.4e35, 1.0])))
    assert vol["oil_sm3"].iloc[0] == 0.0
    with pytest.raises(ValueError, match="unknown rate unit"):
        period_volumes(pd.DataFrame(result_rows("c", "W", [1.0], unit="furlongs/fortnight")))


def test_volume_convention_check_identifies_forward_rates() -> None:
    rates = [10.0, 20.0, 30.0, 40.0]
    days = [31, 28, 31]
    cum = [0.0]
    for q, d in zip(rates, days, strict=False):
        cum.append(cum[-1] + q * d)
    rows = result_rows("c", "W", rates) + result_rows("c", "W", cum, prop="CumOil", unit="Sm3")
    check = volume_convention_check(pd.DataFrame(rows)).set_index("convention")["relative_error"]
    assert check["forward"] == pytest.approx(0.0)
    assert check["backward"] > 0.1


def test_export_workbench_folder_renumbers_cases(tmp_path: Path) -> None:
    results = tmp_path / "results"
    results.mkdir()
    for task in ("t1", "t2"):
        df = pd.DataFrame(result_rows("x", "W", [1.0])).drop(columns="case_name")
        df.to_parquet(results / f"{task}.parquet", index=False)
    rows = [
        {"arm": "switch", "case_name": "without", "task_id": "t1", "status": "Completed"},
        {"arm": "switch", "case_name": "with", "task_id": "t2", "status": "Completed"},
        {"arm": "other", "case_name": "failed", "task_id": "t3", "status": "Failed"},
    ]
    out = export_workbench_folder(rows, results, tmp_path / "wb", baseline="without")
    cases = pd.read_csv(out / "cases.csv")
    assert cases["run_number"].tolist() == [1, 2, 3]
    assert cases.set_index("case_name")["is_baseline"].to_dict() == {
        "without": True,
        "with": False,
        "failed": False,
    }
    assert pd.read_parquet(out / "results" / "t2.parquet")["run_number"].unique().tolist() == [2]
    assert not (out / "results" / "t3.parquet").exists()
