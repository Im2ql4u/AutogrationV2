from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import pytest
import yaml
from pydantic import ValidationError

from alvheim_tiein import cli
from alvheim_tiein.project import (
    HARD_MAX_ACTIVE_RUNS,
    Limits,
    Project,
    ProjectError,
    RunLog,
    Workspace,
    check_run_budget,
    estimate_runs,
    petex_serial,
    resolve_tracked_variable,
)

FL1 = "RESOLVE.MODULE[0].MOD[0].EQUIP[754]"
FL2 = "RESOLVE.MODULE[0].MOD[0].EQUIP[764]"
BY3 = "RESOLVE.MODULE[0].MOD[0].EQUIP[223]"

PROJECT: dict[str, Any] = {
    "name": "Froskelaar tie-in",
    "type": "case_comparison",
    "asset": "Alvheim",
    "model_id": "m-1",
    "switch": {
        "label": "Froskelaar",
        "off_from": "2026-07-01",
        "wells": [{"name": "FL1", "path": FL1}, {"name": "FL2", "path": FL2}],
    },
    "bookings": {"groups": ["Boyla+Frosk"]},
    "tracked_variables": ["GAP.MOD[{PROD}].SEP[{S}].SolverResults[0].GasRate"],
    "cases": [
        {"name": "baseline", "baseline": True, "switch": "off"},
        {
            "name": "baseline_tuned",
            "based_on": "baseline",
            "changes": {
                "assumptions": [
                    {
                        "operation": "replace",
                        "path": BY3,
                        "property_name": "DPControlValue",
                        "values": [5],
                    },
                    {
                        "operation": "schedule",
                        "path": BY3,
                        "name": "BY3",
                        "schedule": {"date": "2028-01-01", "event_type": "WELL_OFF", "index": 0},
                    },
                ]
            },
        },
        {
            "name": "tie_in",
            "based_on": "baseline_tuned",
            "switch": "on",
            "changes": {
                "assumptions": [
                    {
                        "operation": "replace",
                        "path": BY3,
                        "property_name": "DPControlValue",
                        "values": [8],
                    }
                ]
            },
        },
        {
            "name": "sweep",
            "switch": "on",
            "changes": {
                "assumptions": [
                    {
                        "operation": "replace",
                        "path": BY3,
                        "property_name": "DPControlValue",
                        "values": [2, 4, 6],
                    }
                ],
                "dataobject_tables": [
                    {
                        "object_alias": "Capacities",
                        "table_name": "TotalGas_Capacity",
                        "index": 0,
                        "values": [4300, 4700],
                    }
                ],
                "exclude": [1],
            },
            "case_labels": {1: "dp2_gas4300"},
        },
    ],
}


def project(**overrides: Any) -> Project:
    data = copy.deepcopy(PROJECT)
    data.update(overrides)
    return Project.model_validate(data)


def schedules(body: dict[str, Any]) -> list[dict[str, Any]]:
    return [a for a in body["assumptions"] if a["operation"] == "schedule"]


# ------------------------------------------------------------------ validation
def test_exactly_one_baseline_with_the_reservoir_off() -> None:
    cases = copy.deepcopy(PROJECT["cases"])
    cases[0]["baseline"] = False
    with pytest.raises(ValidationError, match="exactly one baseline"):
        project(cases=cases)
    cases = copy.deepcopy(PROJECT["cases"])
    cases[0]["switch"] = "on"
    with pytest.raises(ValidationError, match="must have Froskelaar switched off"):
        project(cases=cases)


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"based_on": "nope"}, "is not a case"),
        ({"changes": {"replace": []}}, "unknown change keys"),
        ({"switch": None, "based_on": None}, "say `switch: on`"),
    ],
)
def test_case_problems_are_reported(change: dict[str, Any], message: str) -> None:
    cases = copy.deepcopy(PROJECT["cases"])
    cases[3].update(change)
    with pytest.raises(ValidationError, match=message):
        project(cases=cases)


def test_based_on_loops_are_refused() -> None:
    cases = copy.deepcopy(PROJECT["cases"])
    cases[0]["based_on"] = "tie_in"
    with pytest.raises(ValidationError, match="loops"):
        project(cases=cases)


def test_unquoted_yaml_on_off_work() -> None:
    text = (
        yaml.safe_dump(PROJECT)
        .replace("switch: 'off'", "switch: off")
        .replace("switch: 'on'", "switch: on")
    )
    assert "switch: off" in text
    p = Project.model_validate(yaml.safe_load(text))
    assert p.switch_state(p.case("tie_in")) == "on"


def test_limits_cannot_exceed_the_hard_ceiling() -> None:
    with pytest.raises(ValidationError):
        Limits(max_active_runs=HARD_MAX_ACTIVE_RUNS + 1)


# -------------------------------------------------------------------- requests
def test_baseline_shuts_the_switch_wells_with_openserver_dates() -> None:
    p = project()
    body = p.simulate_request(p.baseline_case)
    assert body["user_specified_name"] == "Froskelaar tie-in | baseline"
    assert petex_serial("2026-07-01") == 46203
    events = schedules(body)
    assert [(e["path"], e["schedule"]["date"], e["schedule"]["event_type"]) for e in events] == [
        (FL1, "46203", "WELL_OFF"),
        (FL2, "46203", "WELL_OFF"),
    ]
    assert len({e["schedule"]["index"] for e in events}) == 2


def test_cases_inherit_changes_and_only_switched_off_cases_shut_the_wells() -> None:
    p = project()
    tuned = p.simulate_request(p.case("baseline_tuned"), revision=2)
    assert tuned["user_specified_name"] == "Froskelaar tie-in | baseline_tuned r2"
    assert p.switch_state(p.case("baseline_tuned")) == "off"
    assert {e["path"] for e in schedules(tuned)} == {BY3, FL1, FL2}
    by3_event = next(e for e in schedules(tuned) if e["path"] == BY3)
    assert by3_event["schedule"]["date"] == str(petex_serial("2028-01-01"))

    tie_in = p.simulate_request(p.case("tie_in"))
    assert {e["path"] for e in schedules(tie_in)} == {BY3}
    dp = [a for a in tie_in["assumptions"] if a.get("property_name") == "DPControlValue"]
    assert dp == [
        {"operation": "replace", "path": BY3, "property_name": "DPControlValue", "values": [8]}
    ]


def test_off_changes_apply_to_every_switched_off_case_only() -> None:
    off = {
        "dataobject_tables": [
            {
                "object_alias": "Wells_constraints",
                "table_name": "MaxLiquidRate",
                "index": 42,
                "values": [0],
            }
        ]
    }
    p = project(switch={**PROJECT["switch"], "off_changes": off})
    for name in ("baseline", "baseline_tuned"):
        cells = p.simulate_request(p.case(name)).get("dataobject_tables", [])
        assert {(c["table_name"], c["index"], tuple(c["values"])) for c in cells} == {
            ("MaxLiquidRate", 42, (0,))
        }
    assert "dataobject_tables" not in p.simulate_request(p.case("tie_in"))
    assert estimate_runs(p.simulate_request(p.baseline_case)) == 1

    no_events = p.model_copy(update={"switch": p.switch.model_copy(update={"off_events": False})})
    assert schedules(no_events.simulate_request(no_events.baseline_case)) == []

    sweep = {"dataobject_tables": [{**off["dataobject_tables"][0], "values": [0, 1]}]}
    with pytest.raises(ValidationError, match="take one value"):
        project(switch={**PROJECT["switch"], "off_changes": sweep})


def test_tracked_variables_reach_gap_through_resolve_and_include_booking_limits() -> None:
    p = project()
    tracked = p.simulate_request(p.case("tie_in"))["tracked_variables"]
    assert tracked[0] == "resolve.module[0].MOD[{PROD}].SEP[{S}].SolverResults[0].GasRate"
    assert "resolve.module[0].MOD[{PROD}].GROUP[{Boyla+Frosk}].MaxQTotGas" in tracked
    assert len(tracked) == 1 + 4
    assert resolve_tracked_variable("RESOLVE.CurrentTime") == "RESOLVE.CurrentTime"


def test_run_estimate_multiplies_sweeps() -> None:
    p = project()
    assert estimate_runs(p.simulate_request(p.baseline_case)) == 1
    sweep = p.simulate_request(p.case("sweep"))
    assert sweep["exclude"] == [1]
    assert estimate_runs(sweep) == 3 * 2 - 1
    assert estimate_runs({**sweep, "include_base_case": True}) == 6


# ------------------------------------------------------------------ run budget
def test_run_budget_limits_per_submit_and_active_runs() -> None:
    limits = Limits(max_runs_per_submit=10, max_active_runs=20)
    assert check_run_budget(10, 10, limits) is None
    assert "one submission" in (check_run_budget(11, 0, limits) or "")
    assert "unfinished" in (check_run_budget(5, 16, limits) or "")


# --------------------------------------------------------------------- run log
def test_run_log_rows_put_the_baseline_first_and_label_sweeps(tmp_path: Path) -> None:
    p = project()
    log = RunLog(tmp_path / "runs.json")
    for name, group in (("sweep", "g2"), ("baseline", "g1")):
        log.record_submission(
            name,
            "m-1",
            {"user_specified_name": name},
            {"assumption_group_id": group, "case_count": 1},
            1,
        )
    log.record_tasks(
        "sweep",
        [
            {"task_id": "t2", "assumption_case": 1, "status": "Running"},
            {"task_id": "t3", "assumption_case": 2, "status": "Enqueued"},
        ],
    )
    log.record_tasks("baseline", [{"task_id": "t1", "assumption_case": 1, "status": "Completed"}])
    log.save()
    rows = RunLog(tmp_path / "runs.json").rows(p)
    assert [(r["case_name"], r["is_baseline"], r["switch"]) for r in rows] == [
        ("baseline", True, "off"),
        ("dp2_gas4300", False, "on"),
        ("sweep#2", False, "on"),
    ]


def test_next_revision_counts_history(tmp_path: Path) -> None:
    log = RunLog(tmp_path / "runs.json")
    for revision in (1, 2, 3):
        log.record_submission(
            "tie_in",
            "m",
            {"user_specified_name": "x"},
            {"assumption_group_id": f"g{revision}", "case_count": 1},
            revision,
        )
    log.cases["tie_in"]["revision"] = 1  # e.g. edited by hand: history still has r2
    assert log.next_revision("tie_in") == 3
    assert log.next_revision("new") == 1


# ------------------------------------------------------------------- workspace
def write_project(data_dir: Path, slug: str = "fl") -> Path:
    ws = Workspace(data_dir)
    paths = ws.paths(slug)
    paths.root.mkdir(parents=True)
    paths.definition.write_text(yaml.safe_dump(PROJECT, allow_unicode=True), encoding="utf-8")
    return paths.root


def test_every_command_needs_a_project(tmp_path: Path) -> None:
    ws = Workspace(tmp_path)
    with pytest.raises(ProjectError, match="no project selected"):
        ws.resolve(None)
    write_project(tmp_path)
    with pytest.raises(ProjectError, match="no project 'other'"):
        ws.resolve("other")
    ws.use("fl")
    assert ws.resolve(None) == "fl"
    with pytest.raises(ProjectError, match="slug"):
        ws.paths("Bad Slug")


def test_submit_refuses_without_a_project(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("STUDY_DATA_DIR", str(tmp_path))
    assert cli.main(["submit", "all", "--dry-run"]) == 1
    assert "no project selected" in capsys.readouterr().err


def test_submit_all_dry_run_prints_every_case(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("STUDY_DATA_DIR", str(tmp_path))
    write_project(tmp_path)
    Workspace(tmp_path).use("fl")
    assert cli.main(["submit", "all", "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert out.count("POST /models/m-1/simulate") == 4
    assert "8 run(s): baseline (1), baseline_tuned (1), tie_in (1), sweep (5)" in out


class FakeApi:
    def __init__(self, active: int) -> None:
        self.active = active
        self.submitted: list[dict[str, Any]] = []

    def __enter__(self) -> FakeApi:
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def me(self) -> dict[str, Any]:
        return {"email": "me@akerbp.com"}

    def tasks(self, **filters: Any) -> Any:
        assert filters["created_by"] == "me@akerbp.com"
        return iter([{}] * self.active)

    def simulate(self, model_id: str, body: dict[str, Any]) -> dict[str, Any]:
        self.submitted.append(body)
        return {"assumption_group_id": f"g{len(self.submitted)}", "case_count": estimate_runs(body)}


@pytest.mark.parametrize(("active", "expected"), [(0, 0), (35, 2)])
def test_submit_checks_the_run_budget(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, active: int, expected: int
) -> None:
    monkeypatch.setenv("STUDY_DATA_DIR", str(tmp_path))
    root = write_project(tmp_path)
    api = FakeApi(active)
    monkeypatch.setattr(cli.AutogrationClient, "from_env", classmethod(lambda cls, *a, **k: api))
    assert cli.main(["submit", "all", "--project", "fl"]) == expected
    log = RunLog(root / "runs.json")
    if expected == 0:
        assert sorted(log.cases) == ["baseline", "baseline_tuned", "sweep", "tie_in"]
        assert cli.main(["submit", "tie_in", "--project", "fl"]) == 2  # already submitted
    else:
        assert not log.cases and not api.submitted


# ----------------------------------------------------- optional, typed projects
SCENARIO: dict[str, Any] = {
    "name": "Booking release",
    "type": "scenario_comparison",
    "environment": "test",
    "asset": "Alvheim",
    "model_id": "m-1",
    "bookings": {"groups": ["Tyrving"], "lift_gas_property": "SolverResults[0].GasInj"},
    "cases": [
        {"name": "base", "baseline": True, "imported": True},
        {
            "name": "lift_tyrving",
            "changes": {
                "dataobject_tables": [
                    {
                        "object_alias": "Bookings_oil",
                        "table_name": "Tyrving",
                        "rows": "0-2,5",
                        "value": 99999,
                    }
                ]
            },
        },
    ],
}


def test_scenario_comparison_needs_no_switch_and_expands_row_ranges() -> None:
    p = Project.model_validate(SCENARIO)
    assert p.switch is None and p.switch_state(p.case("lift_tyrving")) is None
    body = p.simulate_request(p.case("lift_tyrving"))
    cells = body["dataobject_tables"]
    assert [c["index"] for c in cells] == [0, 1, 2, 5]
    assert all(c["values"] == [99999] for c in cells) and "rows" not in cells[0]
    assert estimate_runs(body) == 1
    assert (
        "resolve.module[0].MOD[{PROD}].GROUP[{Tyrving}].SolverResults[0].GasInj"
        in body["tracked_variables"]
    )
    with pytest.raises(ProjectError, match="imported"):
        p.simulate_request(p.baseline_case)


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"type": "case_comparison"}, "needs a `switch`"),
        ({"cases": [{"name": "b", "baseline": True, "switch": "off"}]}, "needs a project switch"),
        (
            {
                "cases": [
                    {
                        "name": "b",
                        "baseline": True,
                        "imported": True,
                        "changes": {"assumptions": []},
                    }
                ]
            },
            "imported case has no",
        ),
        (
            {
                "cases": [
                    {
                        "name": "b",
                        "baseline": True,
                        "changes": {
                            "dataobject_tables": [
                                {
                                    "object_alias": "A",
                                    "table_name": "T",
                                    "rows": "0-3",
                                    "values": [1, 2],
                                }
                            ]
                        },
                    }
                ]
            },
            "exactly one `value`",
        ),
    ],
)
def test_project_shape_problems(change: dict[str, Any], message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        Project.model_validate({**SCENARIO, **change})


def test_imported_runs_are_logged_and_labelled(tmp_path: Path) -> None:
    p = Project.model_validate(SCENARIO)
    log = RunLog(tmp_path / "runs.json")
    tasks = [
        {
            "task_id": "t9",
            "assumption_case": 12,
            "status": "Completed",
            "parent_task_id": "m-1",
            "user_specified_name": "kd fast grids",
            "created_by": {"email": "kd@x"},
            "assumption_group_id": "g",
        },
    ]
    log.record_import("base", tasks, source="t9")
    rows = log.rows(p)
    assert rows[0]["case_name"] == "base" and rows[0]["imported"] and rows[0]["is_baseline"]
    assert log.cases["base"]["model_id"] == "m-1" and log.cases["base"]["created_by"] == "kd@x"
    with pytest.raises(ProjectError, match="no runs"):
        log.record_import("x", [], source="nothing")


def test_projects_are_optional(tmp_path: Path) -> None:
    ws = Workspace(tmp_path)
    assert ws.resolve_optional(None) is None
    assert ws.adhoc.runs == tmp_path / "adhoc" / "runs.json"
    write_project(tmp_path)
    ws.use("fl")
    assert ws.resolve_optional(None) == "fl"
    ws.clear_current()
    assert ws.resolve_optional(None) is None


def test_settings_follow_a_projects_named_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    from alvheim_tiein.config import ConfigError, Settings

    monkeypatch.setenv("AUTOGRATION_QA_API_URL", "https://qa.example/api/v1/")
    monkeypatch.setenv("AUTOGRATION_QA_API_SCOPE", "api://qa/access_as_user")
    s = Settings.from_env()
    qa = s.for_environment("qa")
    assert qa.api_url == "https://qa.example/api/v1" and qa.api_scope == "api://qa/access_as_user"
    assert qa.environment == "qa" and qa.web_url == "https://qa.example"
    assert s.for_environment(None) is s
    with pytest.raises(ConfigError, match="not configured"):
        s.for_environment("nowhere")


def test_one_off_run_outside_projects(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("STUDY_DATA_DIR", str(tmp_path))
    request = tmp_path / "req.yaml"
    request.write_text(
        "model_id: m-9\n"
        "dataobject_tables:\n  - {object_alias: A, table_name: T, rows: 0-1, value: 5}\n"
        "tracked_variables: ['GAP.MOD[{PROD}].SEP[{S}].SolverResults[0].GasRate']\n",
        encoding="utf-8",
    )
    api = FakeApi(0)
    monkeypatch.setattr(cli.AutogrationClient, "from_env", classmethod(lambda cls, *a, **k: api))
    assert cli.main(["run", str(request), "--name", "quick look"]) == 0
    body = api.submitted[0]
    assert body["user_specified_name"] == "quick look" and body["assumptions"] == []
    assert [c["index"] for c in body["dataobject_tables"]] == [0, 1]
    assert body["tracked_variables"][0].startswith("resolve.module[0]")
    assert "quick look" in RunLog(tmp_path / "adhoc" / "runs.json").cases
    assert cli.main(["run", str(request), "--name", "quick look"]) == 1  # name already logged
    assert "already logged" in capsys.readouterr().err


def test_add_run_attaches_anyones_runs_to_a_project(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("STUDY_DATA_DIR", str(tmp_path))
    root = write_project(tmp_path)

    class ImportApi(FakeApi):
        def group_progress(self, ref: str) -> Any:
            from alvheim_tiein.client import GroupProgress

            tasks = [
                {
                    "task_id": f"{ref}-{n}",
                    "assumption_case": n,
                    "status": "Completed",
                    "parent_task_id": "m-1",
                    "user_specified_name": "kd lifts",
                    "created_by": {"email": "kd@x"},
                }
                for n in (1, 2)
            ]
            return GroupProgress(ref, {"Completed": 2}, tasks)

    api = ImportApi(0)
    monkeypatch.setattr(cli.AutogrationClient, "from_env", classmethod(lambda cls, *a, **k: api))
    assert cli.main(["project", "add-run", "g7", "--case", "kd_lifts", "--project", "fl"]) == 0
    p = Project.load(root / "project.yaml")
    case = p.case("kd_lifts")
    assert case.imported and p.switch_state(case) == "on"
    rows = RunLog(root / "runs.json").rows(p)
    assert [r["case_name"] for r in rows if r["case"] == "kd_lifts"] == ["kd_lifts#1", "kd_lifts#2"]
    assert cli.main(["project", "add-run", "g7", "--case", "kd_lifts", "--project", "fl"]) == 1
