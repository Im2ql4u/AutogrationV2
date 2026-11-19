"""``tiein optimise``, ``tiein mhgrid`` and ``tiein export-reference`` on a synthetic
workspace: a two-group model in the cache, reference files, a fake Autogration."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import httpx
import pandas as pd
import pytest
import yaml

from alvheim_tiein import cli, report
from alvheim_tiein.economics import Reference
from alvheim_tiein.optimise import runner as rn
from alvheim_tiein.optimise import study as st
from alvheim_tiein.optimise import templates
from alvheim_tiein.project import Case, Project, ProjectError, RunLog, Workspace

from .test_optimise_study import FakeBackend, fake_results, model
from .test_project import PROJECT, FakeApi

GROUPS = {"G": ["H1"], "H": ["S1"]}
MONTHS = list(pd.date_range("2026-07-01", periods=15, freq="MS"))


def project_data() -> dict[str, Any]:
    data = copy.deepcopy(PROJECT)
    data["bookings"] = {"groups": ["G", "H"]}
    data["cases"].append(
        {"name": "tie_in_lift", "based_on": "tie_in", "description": "bookings lifted"}
    )
    return data


def payload() -> dict[str, Any]:
    tables = [dict(t) for t in model().payload["tables"]]
    tables += [
        {"object_alias": "Bookings_oil", "table_name": "H", "values": [80.0] * 24},
        {"object_alias": "Future_Bookings_Liquid", "table_name": "H", "values": [800.0] * 60},
        {
            "object_alias": "Wells_constraints",
            "table_name": "Well",
            "values": ["H1", "S1", "FL1", "FL2"],
        },
        {
            "object_alias": "Wells_constraints",
            "table_name": "MaxLiquidRate",
            "values": [5000.0] * 4,
        },
    ]
    return {"tables": tables}


@pytest.fixture
def ws(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, reference: Reference) -> Workspace:
    monkeypatch.setenv("STUDY_DATA_DIR", str(tmp_path))
    w = Workspace(tmp_path)
    paths = w.paths("fl")
    paths.root.mkdir(parents=True)
    paths.definition.write_text(yaml.safe_dump(project_data()), encoding="utf-8")
    w.use("fl")
    cache = tmp_path / "models" / "m-1"
    cache.mkdir(parents=True)
    (cache / "dataobject-tables.json").write_text(json.dumps(payload()), encoding="utf-8")
    (cache / "groups.json").write_text(json.dumps(GROUPS), encoding="utf-8")
    ref = tmp_path / "reference"
    ref.mkdir()
    reference.entities.to_csv(ref / "entities.csv", index=False)
    shares = reference.shares.assign(valid_from="2020-01-01", valid_to="")
    shares.to_csv(ref / "licence_shares.csv", index=False)
    pd.DataFrame(
        {"date": ["2026-07-01"], "oil_price_per_bbl": [100.0], "gas_price_per_sm3": [0.0]}
    ).to_csv(ref / "prices.csv", index=False)
    (ref / "economics.yaml").write_text(
        yaml.safe_dump({"valuation_date": "2027-01-01", "discount_rate": 0.0}), encoding="utf-8"
    )
    return w


def complete(w: Workspace, case: str, task_id: str) -> dict[str, Any]:
    """Record a completed run of a case, as `tiein submit` and `tiein status` would."""
    project, _, log = w.load("fl")
    body = project.simulate_request(project.case(case))
    log.record_submission(
        case, "m-1", body, {"assumption_group_id": f"g-{case}", "case_count": 1}, 1
    )
    log.record_tasks(case, [{"task_id": task_id, "assumption_case": 1, "status": "Completed"}])
    log.save()
    return body


def test_every_scheme_template_is_a_valid_study() -> None:
    project = Project.model_validate(project_data())
    assert templates.default_cases(project) == ("tie_in", ["baseline"])
    for scheme in st.SCHEMES:
        data = templates.template(scheme, f"{scheme.replace('_', '-')}-1", project)
        spec = st.StudySpec.model_validate(yaml.safe_load(templates.study_yaml(data)))
        assert spec.base_case == "tie_in" and spec.reference_cases == ["baseline"]
        assert spec.required_runs() <= spec.budget.max_evaluations
    with pytest.raises(ProjectError, match="study Bad"):
        templates.template("outer", "Bad", project)
    with pytest.raises(ProjectError, match="no case 'nope'"):
        templates.template("outer", "x", project, base_case="nope")


def test_a_study_from_new_to_report_against_a_fake_autogration(
    ws: Workspace, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    backend = FakeBackend()
    body = complete(ws, "tie_in", "t-tie")
    backend.status["t-tie"] = st.COMPLETED
    backend.results["t-tie"] = fake_results(body)
    api = FakeApi(0)
    monkeypatch.setattr(cli.AutogrationClient, "from_env", classmethod(lambda cls, *a, **k: api))
    monkeypatch.setattr(rn, "ApiBackend", lambda _: backend)

    assert cli.main(["optimise", "new", "settle", "--scheme", "total_then_settle"]) == 0
    out = capsys.readouterr().out
    assert "runs start from tie_in, compared with baseline" in out
    assert cli.main(["optimise", "new", "settle", "--scheme", "outer"]) == 1
    assert "--force replaces it" in capsys.readouterr().err

    assert cli.main(["optimise", "check", "settle", "--offline"]) == 0
    out = capsys.readouterr().out
    assert "completed monthly runs reused: tie_in (t-tie)" in out
    assert "neutral_and_release" in out and "problem" in out

    assert cli.main(["optimise", "step", "settle", "--dry-run"]) == 0
    assert "dry run: 2 new run(s) would start, 0 shared" in capsys.readouterr().out
    sp = rn.StudyPaths(ws.paths("fl"), "settle")
    assert len(list((sp.root / "dry-run").glob("*.json"))) == 2 and not backend.bodies

    for _ in range(10):
        assert cli.main(["optimise", "step", "settle"]) == 0
        out = capsys.readouterr().out
        if "finished: completed" in out:
            break
        backend.finish_all()
    assert "finished: completed" in out and "against the base case" in out
    assert RunLog(ws.paths("fl").runs).cases.keys() == {"tie_in"}  # study runs stay out

    assert cli.main(["optimise", "status", "settle"]) == 0
    assert "done: completed" in capsys.readouterr().out
    assert cli.main(["optimise", "report", "settle"]) == 0
    out = capsys.readouterr().out
    # Against the base case (both Froskelaar on) the decided rule; against the
    # Froskelaar-off baseline the tie-in, which the surplus rules don't settle.
    assert "settlement (proportional)" in out and "tie-in agreement" in out
    settle = pd.read_csv(sp.report / "settlement.csv")
    assert set(settle.loc[settle["against"] == "ref:baseline", "rule"]) == {"tie-in"}
    assert cli.main(["optimise", "report", "settle", "--rule", "minimal"]) == 0
    out = capsys.readouterr().out
    assert "settlement (minimal)" in out and "transfer" in out
    assert (sp.report / "settlement.csv").exists() and (sp.report / "summary.json").exists()
    assert cli.main(["optimise", "list"]) == 0
    assert "done: completed" in capsys.readouterr().out
    assert cli.main(["optimise", "new", "settle", "--scheme", "outer", "--force"]) == 1
    assert "has started" in capsys.readouterr().err


def test_step_watches_several_studies_and_rides_out_a_gateway_error(
    ws: Workspace, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    backend = FakeBackend()
    body = complete(ws, "tie_in", "t-tie")
    backend.status["t-tie"] = st.COMPLETED
    backend.results["t-tie"] = fake_results(body)
    api = FakeApi(0)
    monkeypatch.setattr(cli.AutogrationClient, "from_env", classmethod(lambda cls, *a, **k: api))
    monkeypatch.setattr(rn, "ApiBackend", lambda _: backend)
    for name in ("one", "two"):
        assert cli.main(["optimise", "new", name, "--scheme", "total_then_settle"]) == 0

    simulate, failures = backend.simulate, [cli.AutogrationError(504, "POST", "simulate", "")]

    def flaky(model_id: str, request: Any) -> dict[str, Any]:
        if failures:
            raise failures.pop()
        return simulate(model_id, request)

    monkeypatch.setattr(backend, "simulate", flaky)
    rounds: list[int] = []

    def sleep(_: float) -> None:
        rounds.append(1)
        assert len(rounds) < 30, "the watch never ended"
        backend.finish_all()

    monkeypatch.setattr(cli.time, "sleep", sleep)
    capsys.readouterr()
    assert cli.main(["optimise", "step", "one", "two", "--watch", "1"]) == 0
    captured = capsys.readouterr()
    assert "one: POST simulate -> 504" in captured.err and "trying again" in captured.err
    assert captured.out.count("finished: completed") == 2
    assert "shared (another study's identical run, no new run): e001, e002" in captured.out

    assert cli._transient(httpx.ConnectError("down"))
    assert cli._transient(cli.SignInError("sign-in failed: getaddrinfo failed"))
    assert cli._transient(cli.AutogrationError(401, "GET", "tasks", "expired"))
    assert not cli._transient(cli.AutogrationError(422, "POST", "simulate", "bad request"))


def test_cancel_stops_a_study_and_its_runs(
    ws: Workspace, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    backend = FakeBackend()
    api = FakeApi(0)
    monkeypatch.setattr(cli.AutogrationClient, "from_env", classmethod(lambda cls, *a, **k: api))
    monkeypatch.setattr(rn, "ApiBackend", lambda _: backend)
    assert cli.main(["optimise", "new", "soft", "--scheme", "soften_bookings"]) == 0
    assert cli.main(["optimise", "step", "soft"]) == 0
    assert backend.bodies
    assert cli.main(["optimise", "cancel", "soft"]) == 0
    assert sorted(backend.cancelled) == sorted(backend.bodies)
    assert cli.main(["optimise", "status", "soft"]) == 0
    assert "done: cancelled" in capsys.readouterr().out


class FakeReport:
    def __init__(self, satisfaction: pd.DataFrame, wells: pd.DataFrame) -> None:
        self._satisfaction = satisfaction
        self.wells = wells

    def satisfaction(self) -> pd.DataFrame:
        return self._satisfaction.copy()


def booking_report() -> FakeReport:
    """S1 (tie_in): G produces its full booking of 100, H 50 of its 80. S2 (lifted): G
    would produce 140, H still 50; Froskelaar peaks at 1000 and 2000 Sm3/d liquid. FL is
    an unbooked group (booked 0, no table column): plans must leave it out."""
    rows = []
    for p in MONTHS:
        rows += [
            {"case_name": "tie_in", "group": "G", "period": p, "phase": "oil",
             "booked_sm3d": 100.0, "produced_sm3d": 100.0},
            {"case_name": "tie_in", "group": "H", "period": p, "phase": "oil",
             "booked_sm3d": 80.0, "produced_sm3d": 50.0},
            {"case_name": "tie_in", "group": "FL", "period": p, "phase": "oil",
             "booked_sm3d": 0.0, "produced_sm3d": 300.0},
            {"case_name": "tie_in_lift", "group": "G", "period": p, "phase": "oil",
             "booked_sm3d": float("nan"), "produced_sm3d": 140.0},
            {"case_name": "tie_in_lift", "group": "H", "period": p, "phase": "oil",
             "booked_sm3d": float("nan"), "produced_sm3d": 50.0},
            {"case_name": "tie_in_lift", "group": "FL", "period": p, "phase": "oil",
             "booked_sm3d": 0.0, "produced_sm3d": 400.0},
        ]  # fmt: skip
    # Results end with a timestamp after the last step; no run step reads a booking there.
    end = pd.Timestamp("2041-01-01")
    rows += [
        {"case_name": c, "group": "G", "period": end, "phase": "oil",
         "booked_sm3d": 100.0, "produced_sm3d": 100.0}
        for c in ("tie_in", "tie_in_lift")
    ]  # fmt: skip
    wells = pd.DataFrame(
        [
            {"case_name": "tie_in_lift", "identifier": w, "period": p, "phase": "liquid",
             "rate_sm3d": peak * (1 - i / 30)}
            for w, peak in (("FL1", 1000.0), ("FL2", 2000.0))
            for i, p in enumerate(MONTHS)
        ]
    )  # fmt: skip
    return FakeReport(pd.DataFrame(rows), wells)


def test_plans_write_booking_plans_and_candidates_a_check_accepts(
    ws: Workspace, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    complete(ws, "tie_in", "t-tie")
    complete(ws, "tie_in_lift", "t-lift")
    monkeypatch.setattr(report, "booking_report", lambda *a, **k: booking_report())
    assert cli.main(["optimise", "new", "restr", "--scheme", "restructure_bookings"]) == 0
    assert cli.main(["optimise", "check", "restr", "--offline"]) == 1
    assert "no booking plan" in capsys.readouterr().err

    assert cli.main(["optimise", "plans", "restr", "--s2", "tie_in_lift", "--offline"]) == 0
    out = capsys.readouterr().out
    assert "S1 tie_in, S2 tie_in_lift: 2 groups, 15 periods" in out
    assert "surrogate ranking" in out

    sp = rn.StudyPaths(ws.paths("fl"), "restr")
    lend = pd.read_csv(sp.plans / "r1_lend.csv").groupby("group")["booked_sm3d"].mean()
    assert lend.to_dict() == pytest.approx({"G": 130.0, "H": 50.0})
    split = pd.read_csv(sp.plans / "r4_pro_rata.csv").groupby("group")["booked_sm3d"].mean()
    assert split.to_dict() == pytest.approx({"G": 180 * 140 / 190, "H": 180 * 50 / 190})

    spec = rn.load_spec(sp.spec)
    assert [c.name for c in spec.candidates] == ["r1_lend", "r4_pro_rata", "r3_phi50", "r3_phi80"]
    caps = {(c["index"], c["values"][0]) for c in spec.candidate("r3_phi50").cells}
    assert caps == {(2, 500.0), (3, 1000.0)}
    assert sp.spec.read_text(encoding="utf-8").startswith("# Optimisation study")

    assert cli.main(["optimise", "check", "restr", "--offline"]) == 0
    out = capsys.readouterr().out
    assert "r1_lend.csv" in out and "r3_phi80" in out

    assert cli.main(["export-reference", "--offline", "--study", "restr"]) == 0
    capsys.readouterr()


def test_mhgrid_writes_the_grid_as_case_changes(
    ws: Workspace, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    out_yaml, out_csv = tmp_path / "grid.yaml", tmp_path / "grid.csv"
    args = ["mhgrid", "--offline", "--case", "baseline", "--write", str(out_yaml)]
    assert cli.main([*args, "--table", str(out_csv)]) == 0
    out = capsys.readouterr().out
    assert "grid mh: 45 steps" in out and "Uptime_base" in out
    changes = yaml.safe_load(out_yaml.read_text(encoding="utf-8"))["changes"]
    assert changes["schedule_ops"] == [{"op": "add", "index": -1}]
    assert changes["resolve_settings"] == st.request_resolve_settings("mh")
    Case.model_validate({"name": "baseline_mh", "changes": changes})
    assert not pd.read_csv(out_csv).empty


def test_export_reference_writes_what_the_results_page_reads(
    ws: Workspace, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.main(["export-reference", "--offline"]) == 0
    assert "economics to enter on the Results page" in capsys.readouterr().out
    out = ws.paths("fl").root / "reference-upload"
    columns = {
        "licence_shares.csv": ["license", "company", "share", "valid_from", "valid_to"],
        "prices.csv": ["date", "oil_price_per_bbl", "gas_price_per_sm3"],
        "bookings.csv": ["group", "period", "phase", "booked_sm3d", "case"],
        "booking_members.csv": ["group", "well"],
        "facility_limits.csv": ["period", "phase", "limit_sm3d"],
    }
    for name, cols in columns.items():
        assert list(pd.read_csv(out / name).columns) == cols, name
    booked = pd.read_csv(out / "bookings.csv")
    oil = booked[(booked["group"] == "G") & (booked["phase"] == "oil")]
    # Held from the first row until the next; blank: no longer booked (future window).
    assert oil["period"].tolist() == ["2026-07-01", "2027-10-01"]
    assert oil["booked_sm3d"].iloc[0] == 100.0 and pd.isna(oil["booked_sm3d"].iloc[1])
    liquid = booked[(booked["group"] == "H") & (booked["phase"] == "liquid")]
    assert liquid["period"].tolist()[0] == "2027-10-01"
    assert len(liquid) == 2  # 800 from Oct 2027, then blank after the table's 60 rows
    members = pd.read_csv(out / "booking_members.csv")
    assert members.values.tolist() == [["G", "H1"], ["H", "S1"]]
