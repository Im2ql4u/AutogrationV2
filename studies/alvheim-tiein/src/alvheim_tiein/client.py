"""Thin client for the Autogration REST API (``/api/v1``).

Covers what a study needs: discover models and assets, start simulations, follow a
simulation's tasks and tracked variables, and download results. Endpoint semantics are
documented in the backend routes (``autogration/apps/backend/backend/modules``).
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import time
from collections.abc import Callable, Iterable, Iterator, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx
import pandas as pd

from alvheim_tiein.auth import TokenProvider, token_provider
from alvheim_tiein.config import Settings

UNFINISHED = ("Preparing", "Enqueued", "Running")
FINAL = ("Completed", "Failed", "Cancelled")
# OpenServer dates are Excel-style serial days.
_OPENSERVER_EPOCH = dt.datetime(1899, 12, 31)  # 46203 = 2026-07-01, as in Autogration


class AutogrationError(RuntimeError):
    def __init__(self, status: int, method: str, url: str, detail: str) -> None:
        super().__init__(f"{method} {url} -> {status}: {detail}")
        self.status = status
        self.detail = detail


@dataclass
class GroupProgress:
    """State of one simulation (all tasks sharing an ``assumption_group_id``)."""

    assumption_group_id: str
    status_counts: dict[str, int]
    tasks: list[dict[str, Any]] = field(default_factory=list)

    @property
    def total(self) -> int:
        return sum(self.status_counts.values())

    @property
    def unfinished(self) -> int:
        return sum(self.status_counts.get(s, 0) for s in UNFINISHED)

    @property
    def finished(self) -> bool:
        return self.total > 0 and self.unfinished == 0

    def by_case(self) -> dict[int, dict[str, Any]]:
        return {t["assumption_case"]: t for t in self.tasks if t.get("assumption_case") is not None}

    def summary(self) -> str:
        parts = [
            f"{s} {self.status_counts[s]}" for s in (*UNFINISHED, *FINAL) if s in self.status_counts
        ]
        return f"{self.total} task(s): " + (", ".join(parts) if parts else "none yet")


def _clean(params: Mapping[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in params.items() if v is not None and v != []}


def openserver_date(serial: float) -> dt.datetime:
    return _OPENSERVER_EPOCH + dt.timedelta(days=serial)


def idempotency_key(model_id: str, request: Mapping[str, Any]) -> str:
    """The same key for the same simulate request, so resubmitting it is a no-op."""
    canonical = json.dumps({"model_id": model_id, **request}, sort_keys=True, default=str)
    return "tiein-" + hashlib.sha256(canonical.encode()).hexdigest()[:40]


class AutogrationClient:
    def __init__(
        self,
        base_url: str,
        token: TokenProvider | None = None,
        *,
        timeout: float = 120.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self._token = token
        self._http = httpx.Client(
            base_url=self.base_url + "/",
            timeout=timeout,
            transport=transport,
            follow_redirects=False,
        )

    @classmethod
    def from_env(cls, settings: Settings | None = None, **kwargs: Any) -> AutogrationClient:
        settings = settings or Settings.from_env()
        return cls(settings.api_url, token_provider(settings), **kwargs)

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> AutogrationClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # ---------------------------------------------------------------- transport
    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._token()}"} if self._token else {}

    def _check(self, response: httpx.Response) -> httpx.Response:
        request = response.request
        if response.is_redirect:
            raise AutogrationError(
                response.status_code,
                request.method,
                str(request.url),
                "redirected (to sign-in?). The request reached the gateway without a valid "
                "bearer token; check AUTOGRATION_AUTH / AUTOGRATION_API_SCOPE",
            )
        if response.status_code >= 400:
            try:
                detail = response.json().get("detail", response.text)
            except (ValueError, AttributeError):
                detail = response.text
            raise AutogrationError(
                response.status_code, request.method, str(request.url), str(detail)[:2000]
            )
        return response

    def _send(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        headers = kwargs.pop("headers", None) or self._headers()
        response = self._http.request(method, path.lstrip("/"), headers=headers, **kwargs)
        return self._check(response)

    def _json(self, method: str, path: str, **kwargs: Any) -> Any:
        response = self._send(method, path, **kwargs)
        return response.json() if response.content else None

    # ------------------------------------------------------------ who and what
    def me(self) -> dict[str, Any]:
        return self._json("GET", "users/me")

    def api_access(self) -> dict[str, Any]:
        return self._json("GET", "users/me/api-access")

    def request_access(self) -> None:
        """Ask the admins (in Teams) to make you a contributor. Only where roles exist."""
        self._send("POST", "users/me/access-request")

    def assets(self) -> list[str]:
        return self._json("GET", "assets/")

    # -------------------------------------------------------------------- tasks
    def task_page(
        self,
        *,
        task_type: Iterable[str] | str | None = None,
        status: Iterable[str] | str | None = None,
        search: str | None = None,
        asset: str | None = None,
        created_by: str | None = None,
        parent_task_id: str | None = None,
        assumption_group_id: str | None = None,
        created_after: dt.date | None = None,
        created_before: dt.date | None = None,
        limit: int = 100,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        as_list = lambda v: [v] if isinstance(v, str) else (list(v) if v is not None else None)  # noqa: E731
        params = _clean(
            {
                "task_type": as_list(task_type),
                "status": as_list(status),
                "search": search,
                "asset": asset,
                "created_by": created_by,
                "parent_task_id": parent_task_id,
                "assumption_group_id": assumption_group_id,
                "created_after": created_after.isoformat() if created_after else None,
                "created_before": created_before.isoformat() if created_before else None,
                "limit": limit,
                "cursor": cursor,
            }
        )
        return self._json("GET", "tasks", params=params)

    def tasks(self, **filters: Any) -> Iterator[dict[str, Any]]:
        """All matching tasks, newest first, following ``next_cursor``."""
        cursor = None
        while True:
            page = self.task_page(**filters, cursor=cursor)
            yield from page["items"]
            cursor = page.get("next_cursor")
            if not cursor:
                return

    def registered_models(
        self, asset: str | None = None, search: str | None = None
    ) -> list[dict[str, Any]]:
        return list(
            self.tasks(task_type="register_model", status="Completed", asset=asset, search=search)
        )

    def register_model(self, *, name: str, asset: str, s_drive_path: str) -> dict[str, Any]:
        """Register an `.rsl` from the S-drive. Returns the new task (status Preparing);
        its `task_id` becomes the model id once it completes."""
        body = {
            "task_type": "register_model",
            "user_specified_name": name,
            "asset": asset,
            "s_drive_path": s_drive_path,
        }
        return self._json("POST", "tasks", json=body)

    def wait_for_task(
        self,
        task_id: str,
        *,
        poll_seconds: float = 30.0,
        timeout_seconds: float | None = None,
        on_progress: Callable[[dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        deadline = None if timeout_seconds is None else time.monotonic() + timeout_seconds
        while True:
            task = self.task(task_id)
            if on_progress:
                on_progress(task)
            if task["status"] in FINAL:
                return task
            if deadline is not None and time.monotonic() >= deadline:
                raise TimeoutError(f"{task_id}: still {task['status']}")
            time.sleep(poll_seconds)

    def task(
        self, task_id: str, *, include: Iterable[str] = (), log_tail: int = 100
    ) -> dict[str, Any]:
        params = _clean(
            {"include": ",".join(include) or None, "log_tail": log_tail if include else None}
        )
        return self._json("GET", f"tasks/{task_id}", params=params)

    def task_logs(self, task_id: str) -> list[dict[str, Any]]:
        return self._json("GET", f"tasks/{task_id}/logs")

    def assumption_set(self, task_id: str) -> dict[str, Any]:
        return self._json("GET", f"tasks/{task_id}/assumption-set")

    def step_results(self, task_id: str) -> list[dict[str, Any]]:
        return self._json("GET", f"tasks/{task_id}/step-results")

    def cancel(self, task_id: str) -> Any:
        return self._json("POST", f"tasks/{task_id}/cancel")

    # ------------------------------------------------------------------- models
    def model_systems(self, model_id: str) -> list[dict[str, Any]]:
        return self._json("GET", f"models/{model_id}/systems")

    def browse(
        self, model_id: str, path: str | None = None, *, search: str | None = None, limit: int = 50
    ) -> dict[str, Any]:
        params = _clean({"path": path, "search": search, "limit": limit})
        return self._json("GET", f"models/{model_id}/browse", params=params)

    def resolve_settings(self, model_id: str) -> list[dict[str, Any]]:
        return self._json("GET", f"models/{model_id}/resolve-settings")

    def module_settings(self, model_id: str) -> dict[str, Any]:
        return self._json("GET", f"models/{model_id}/module-settings")

    def dataobject_tables(self, model_id: str) -> dict[str, Any]:
        """RESOLVE DataObject (FlexDataStore) tables and current cells; the
        `object_alias`, `table_name` and cell index are what `dataobject_tables`
        sweeps in a simulate request address."""
        return self._json("GET", f"models/{model_id}/dataobject-tables")

    def simulate(
        self, model_id: str, request: Mapping[str, Any], *, retries: int = 4
    ) -> dict[str, Any]:
        """Start a simulation. Returns ``{"assumption_group_id", "case_count"}``.

        Sends an ``Idempotency-Key`` derived from the model and the request, so a
        gateway timeout (which may still have started it) or a crash before the answer
        was recorded can be retried, now or by running the command again, without
        starting a second simulation: the backend answers with the first one."""
        body = dict(request)
        key = idempotency_key(model_id, body)
        delay = 5.0
        for attempt in range(retries + 1):
            try:
                return self._json(
                    "POST",
                    f"models/{model_id}/simulate",
                    json=body,
                    headers={**self._headers(), "Idempotency-Key": key},
                )
            except AutogrationError as e:
                pending = e.status == 409 and "still being" in e.detail
                if attempt == retries or not (e.status in (502, 503, 504) or pending):
                    raise
            except httpx.TransportError:
                if attempt == retries:
                    raise
            time.sleep(delay)
            delay = min(delay * 2, 60.0)
        raise AssertionError("unreachable")

    # ----------------------------------------------------------- monitoring
    def group_progress(self, assumption_group_id: str) -> GroupProgress:
        first = self.task_page(assumption_group_id=assumption_group_id, limit=500)
        tasks = list(first["items"])
        cursor = first.get("next_cursor")
        while cursor:
            page = self.task_page(assumption_group_id=assumption_group_id, limit=500, cursor=cursor)
            tasks.extend(page["items"])
            cursor = page.get("next_cursor")
        return GroupProgress(assumption_group_id, dict(first.get("status_counts", {})), tasks)

    def wait_for_group(
        self,
        assumption_group_id: str,
        *,
        poll_seconds: float = 60.0,
        timeout_seconds: float | None = None,
        on_progress: Callable[[GroupProgress], None] | None = None,
    ) -> GroupProgress:
        deadline = None if timeout_seconds is None else time.monotonic() + timeout_seconds
        while True:
            progress = self.group_progress(assumption_group_id)
            if on_progress:
                on_progress(progress)
            if progress.finished:
                return progress
            if deadline is not None and time.monotonic() >= deadline:
                raise TimeoutError(f"{assumption_group_id}: {progress.summary()}")
            time.sleep(poll_seconds)

    # ---------------------------------------------------------------- results
    def download_results_parquet(self, task_id: str, dest_dir: Path) -> Path:
        """Save ``GET /runs/{task_id}/results/parquet`` as ``<dest_dir>/<task_id>.parquet``."""
        response = self._send("GET", f"runs/{task_id}/results/parquet")
        dest_dir.mkdir(parents=True, exist_ok=True)
        target = dest_dir / f"{task_id}.parquet"
        tmp = target.with_suffix(".part")
        tmp.write_bytes(response.content)
        tmp.replace(target)
        return target

    def download_bundle(self, task_id: str, dest_dir: Path) -> Path | None:
        """Stream the DataExchange JSON to ``<dest_dir>/<task_id>.json``.

        The backend streams without Content-Length and truncates the body if it fails
        mid-way, so the file is only kept if it parses as JSON. Returns None on 204 (no
        results)."""
        dest_dir.mkdir(parents=True, exist_ok=True)
        target = dest_dir / f"{task_id}.json"
        tmp = target.with_suffix(".part")
        with self._http.stream("GET", f"runs/{task_id}", headers=self._headers()) as response:
            if response.status_code >= 400 or response.is_redirect:
                response.read()
                self._check(response)
            if response.status_code == 204:
                return None
            with tmp.open("wb") as fh:
                for chunk in response.iter_bytes():
                    fh.write(chunk)
        try:
            with tmp.open("rb") as fh:
                json.load(fh)
        except ValueError as e:
            tmp.unlink(missing_ok=True)
            raise AutogrationError(200, "GET", f"runs/{task_id}", f"truncated download: {e}") from e
        tmp.replace(target)
        return target


def step_results_frame(batches: Iterable[Mapping[str, Any]]) -> pd.DataFrame:
    """Long table of tracked variables: one row per step x variable."""
    rows = [
        {
            "task_id": batch["task_id"],
            "vm_id": batch.get("vm_id"),
            "time": openserver_date(step["time"]),
            "variable": variable,
            "value": value,
        }
        for batch in batches
        for step in batch.get("results", [])
        if step.get("time") is not None
        for variable, value in (step.get("commands_results") or {}).items()
    ]
    return pd.DataFrame(rows, columns=["task_id", "vm_id", "time", "variable", "value"])
