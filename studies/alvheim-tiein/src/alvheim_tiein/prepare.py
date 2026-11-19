"""Look up what a project refers to in a registered model.

`tiein project new` finds the switch wells' equipment paths and the model's booking
groups; `tiein project check` confirms that the DataObject cells the cases edit exist.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any, Protocol

from alvheim_tiein.project import Project, expand_cells


class Browser(Protocol):
    def browse(
        self, model_id: str, path: str | None = None, *, search: str | None = None, limit: int = 50
    ) -> dict[str, Any]: ...


class PrepareError(LookupError):
    """The registered model doesn't have what the project refers to."""


@dataclass(frozen=True)
class Equipment:
    name: str
    path: str
    equipment_type: str | None


def find_equipment(
    api: Browser, model_id: str, name: str, equipment_type: str | None = "WELL"
) -> Equipment:
    """The one piece of equipment called `name` (case-insensitive)."""
    found = api.browse(model_id, search=name, limit=200).get("matches") or []
    exact = [
        m
        for m in found
        if (m.get("name") or "").lower() == name.lower()
        and m.get("type") == "EQUIPMENT"
        and (equipment_type is None or m.get("equipment_type") == equipment_type)
    ]
    if len(exact) != 1:
        kinds = f" of type {equipment_type}" if equipment_type else ""
        listed = ", ".join(f"{m.get('name')} ({m.get('equipment_type')})" for m in found[:10])
        raise PrepareError(
            f"expected one equipment named {name}{kinds}, found {len(exact)}"
            + (f"; search matched: {listed}" if listed else "")
        )
    m = exact[0]
    return Equipment(name=m["name"], path=m["path"], equipment_type=m.get("equipment_type"))


def dataobject_cells(project: Project) -> list[tuple[str, str, int]]:
    """DataObject cells any case of the project, or switching the reservoir off, edits."""
    cells: list[tuple[str, str, int]] = []
    sources = [case.changes for case in project.cases]
    if project.switch is not None:
        sources.append(project.switch.off_changes)
    for changes in sources:
        for c in expand_cells(changes.get("dataobject_tables") or []):
            cell = (c["object_alias"], c["table_name"], int(c["index"]))
            if cell not in cells:
                cells.append(cell)
    return cells


def check_cells(
    tables: Mapping[str, Any], cells: Iterable[tuple[str, str, int]]
) -> tuple[dict[tuple[str, str, int], Any], list[str]]:
    """Current values of the cells, and a problem for each cell the model lacks."""
    index = {
        (t["object_alias"], t["table_name"]): t.get("values") or []
        for t in tables.get("tables") or []
    }
    values: dict[tuple[str, str, int], Any] = {}
    problems: list[str] = []
    for alias, table, i in cells:
        column = index.get((alias, table))
        if column is None:
            same_alias = sorted(t for a, t in index if a == alias)
            hint = f"; {alias} has {same_alias}" if same_alias else f"; no DataObject {alias}"
            problems.append(f"{alias}.{table} doesn't exist{hint}")
        elif i >= len(column):
            problems.append(f"{alias}.{table}[{i}] is out of range (length {len(column)})")
        else:
            values[(alias, table, i)] = column[i]
    return values, problems
