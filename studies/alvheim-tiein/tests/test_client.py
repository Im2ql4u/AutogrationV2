from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from alvheim_tiein.client import (
    AutogrationClient,
    AutogrationError,
    idempotency_key,
    step_results_frame,
)

BASE = "https://autogration.example/api/v1"


def make_client(handler) -> AutogrationClient:
    return AutogrationClient(BASE, lambda: "tok", transport=httpx.MockTransport(handler))


def test_tasks_follow_cursor_and_send_bearer_and_repeated_filters() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        cursor = request.url.params.get("cursor")
        if cursor is None:
            return httpx.Response(
                200, json={"items": [{"task_id": "1"}], "next_cursor": "c2", "status_counts": {}}
            )
        return httpx.Response(
            200, json={"items": [{"task_id": "2"}], "next_cursor": None, "status_counts": {}}
        )

    tasks = list(
        make_client(handler).tasks(task_type="register_model", status=["Completed", "Failed"])
    )
    assert [t["task_id"] for t in tasks] == ["1", "2"]
    first = seen[0]
    assert first.url.path == "/api/v1/tasks"
    assert first.headers["Authorization"] == "Bearer tok"
    assert first.url.params.get_list("status") == ["Completed", "Failed"]


def test_simulate_posts_body_and_group_progress_counts() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            assert request.url.path == "/api/v1/models/m1/simulate"
            assert json.loads(request.content)["asset"] == "Alvheim"
            return httpx.Response(202, json={"assumption_group_id": "g1", "case_count": 2})
        assert request.url.params["assumption_group_id"] == "g1"
        return httpx.Response(
            200,
            json={
                "items": [
                    {"task_id": "a", "assumption_case": 1, "status": "Completed"},
                    {"task_id": "b", "assumption_case": 2, "status": "Running"},
                ],
                "next_cursor": None,
                "status_counts": {"Completed": 1, "Running": 1},
            },
        )

    api = make_client(handler)
    assert api.simulate("m1", {"asset": "Alvheim"})["case_count"] == 2
    progress = api.group_progress("g1")
    assert (progress.total, progress.unfinished, progress.finished) == (2, 1, False)
    assert progress.by_case()[2]["task_id"] == "b"


def test_redirect_to_sign_in_and_error_details_are_explained() -> None:
    api = make_client(lambda r: httpx.Response(302, headers={"Location": "https://login"}))
    with pytest.raises(AutogrationError, match="bearer token"):
        api.assets()
    api = make_client(
        lambda r: httpx.Response(422, json={"detail": "The input doesn't fit model m1"})
    )
    with pytest.raises(AutogrationError, match="doesn't fit") as err:
        api.simulate("m1", {})
    assert err.value.status == 422


def test_bundle_download_rejects_truncated_json(tmp_path: Path) -> None:
    api = make_client(lambda r: httpx.Response(200, content=b'{"results": [1, 2'))
    with pytest.raises(AutogrationError, match="truncated"):
        api.download_bundle("t1", tmp_path)
    assert not list(tmp_path.iterdir())
    api = make_client(lambda r: httpx.Response(200, content=b'{"results": []}'))
    assert api.download_bundle("t1", tmp_path) == tmp_path / "t1.json"


def test_step_results_frame_converts_openserver_dates() -> None:
    frame = step_results_frame(
        [
            {
                "task_id": "t",
                "vm_id": "v",
                "results": [
                    # Verified on a GAP run: step 0 of a 2026-07-01 forecast.
                    {"time": 46203.0, "commands_results": {"GAP.X": 1.5}},
                    {"time": None, "commands_results": None},
                ],
            }
        ]
    )
    assert len(frame) == 1
    assert str(frame["time"].iloc[0].date()) == "2026-07-01"


def test_register_model_posts_s_drive_task_and_waits() -> None:
    calls: list[tuple[str, str]] = []
    states = iter(["Preparing", "Running", "Completed"])

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.method, request.url.path))
        if request.method == "POST":
            body = json.loads(request.content)
            assert body == {
                "task_type": "register_model",
                "user_specified_name": "Alvheim base",
                "asset": "Alvheim",
                "s_drive_path": "S:\\ALVHEIM\\x\\model.rsl",
            }
            return httpx.Response(202, json={"task_id": "t1", "status": "Preparing"})
        return httpx.Response(200, json={"task_id": "t1", "status": next(states)})

    api = make_client(handler)
    task = api.register_model(
        name="Alvheim base", asset="Alvheim", s_drive_path="S:\\ALVHEIM\\x\\model.rsl"
    )
    assert task["task_id"] == "t1"
    done = api.wait_for_task("t1", poll_seconds=0)
    assert done["status"] == "Completed"
    assert calls[0] == ("POST", "/api/v1/tasks")
    assert calls[-1] == ("GET", "/api/v1/tasks/t1")


def test_dataobject_tables_and_access_request_routes() -> None:
    seen: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((request.method, request.url.path))
        if request.method == "POST":
            return httpx.Response(204)
        return httpx.Response(200, json={"tables": []})

    api = make_client(handler)
    assert api.dataobject_tables("m1") == {"tables": []}
    api.request_access()
    assert seen == [
        ("GET", "/api/v1/models/m1/dataobject-tables"),
        ("POST", "/api/v1/users/me/access-request"),
    ]


def test_simulate_retries_gateway_timeouts_with_one_idempotency_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("alvheim_tiein.client.time.sleep", lambda _s: None)
    keys: list[str] = []
    answers = [
        httpx.Response(504, text="gateway timeout"),
        httpx.Response(
            409, json={"detail": 'A request with Idempotency-Key "k" is still being checked'}
        ),
        httpx.Response(202, json={"assumption_group_id": "g1", "case_count": 1}),
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        keys.append(request.headers["Idempotency-Key"])
        assert request.headers["Authorization"].startswith("Bearer ")
        return answers[len(keys) - 1]

    started = make_client(handler).simulate("m1", {"user_specified_name": "x", "assumptions": []})
    assert started["assumption_group_id"] == "g1"
    assert len(keys) == 3 and len(set(keys)) == 1 and keys[0].startswith("tiein-")


def test_idempotency_key_is_stable_per_request_and_model() -> None:
    body = {"user_specified_name": "x", "assumptions": []}
    assert idempotency_key("m1", body) == idempotency_key("m1", dict(reversed(body.items())))
    assert idempotency_key("m1", body) != idempotency_key("m2", body)
    assert idempotency_key("m1", body) != idempotency_key("m1", {**body, "vm_size": "D4"})


def test_simulate_does_not_retry_a_rejected_request() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(422, json={"detail": "no cases"})

    with pytest.raises(AutogrationError, match="422"):
        make_client(handler).simulate("m1", {"user_specified_name": "x"})
    assert calls == 1
