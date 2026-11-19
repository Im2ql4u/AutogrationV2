from __future__ import annotations

from pathlib import Path

import pytest

from alvheim_tiein import report
from alvheim_tiein import settlement as s
from alvheim_tiein.demo import DEMO_BASELINE, DEMO_WITH, build_demo_data
from alvheim_tiein.economics import Reference, value_volumes
from alvheim_tiein.project import Workspace
from alvheim_tiein.results import load_task_results, period_volumes


def test_demo_project_runs_the_whole_analysis(tmp_path: Path) -> None:
    data_dir = build_demo_data(tmp_path / "demo")
    ws = Workspace(data_dir)
    data = report.load_project(ws)
    assert data.slug == "demo"
    assert data.baseline_name == DEMO_BASELINE
    assert set(data.runs["case_name"]) >= {DEMO_BASELINE, DEMO_WITH}

    results = load_task_results(data.completed().to_dict("records"), data.paths.results)
    ref = Reference.load(ws.reference_dir(data.paths))
    valued = value_volumes(period_volumes(results), ref)
    st = s.settle(valued, ref, DEMO_BASELINE, DEMO_WITH, data.project.analysis.user_licenses)

    paid_to = st.licence_flows.groupby("payee_license")["amount"].sum()
    assert paid_to["PL301"] > 0  # the satellite loses production to the new wells
    assert set(st.licence_flows["payer_license"]) == {"PL102", "PL201"}
    assert st.net.sum() == pytest.approx(0.0, abs=1e-3)
