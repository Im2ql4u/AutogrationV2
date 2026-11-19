"""Several single-run simulate requests as one linked simulation.

Autogration's linked assumptions (``links`` on the simulate request) let items
vary together: a link has options, and each item that belongs to it says which
options it applies in and, for items with values, its value in each. Putting
every item that differs between the requests on one link, with an option per
request, gives one simulation whose cases are exactly those requests, in order.
Items that are the same in every request go in every case unlinked.

The runs then share one ``assumption_group_id``, so Autogration shows them as
one simulation and its results compare them directly.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from typing import Any

from .project import ProjectError, _key, estimate_runs

# Kinds of items, in the order the API numbers dimensions.
ITEM_KINDS = (
    "assumptions",
    "resolve_settings",
    "module_settings",
    "dataobject_tables",
    "module_ops",
    "schedule_ops",
)
# Request fields that must be the same in every request.
SHARED_FIELDS = ("asset", "vm_size", "tracked_variables", "include_base_case")
_OPTION_KEY = re.compile(r"^[^\s]{1,64}$")


def _valued(kind: str, item: Mapping[str, Any]) -> bool:
    """Whether the item has `values` to choose from, rather than just applying."""
    if kind == "assumptions":
        return item.get("operation", "replace") == "replace"
    return kind in ("resolve_settings", "module_settings", "dataobject_tables")


def _single_value(kind: str, item: Mapping[str, Any], case: str) -> Any:
    values = list(item.get("values") or [])
    if len(values) != 1:
        raise ProjectError(
            f"{case}: {kind} item {_key(kind, item)} has {len(values)} values; "
            "each request must be a single run"
        )
    return values[0]


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, default=str)


def combine(
    bodies: Mapping[str, Mapping[str, Any]],
    *,
    name: str,
    link_key: str = "case",
    link_label: str = "Case",
    labels: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    """One simulate request whose cases are ``bodies``, in order, keyed by option.

    Each body must start one run. The option keys are the keys of ``bodies``.
    """
    if len(bodies) < 2:
        raise ProjectError("a linked simulation needs at least two cases")
    options = list(bodies)
    for key in options:
        if not _OPTION_KEY.match(key):
            raise ProjectError(f"case key {key!r}: 1 to 64 characters, no spaces")
    for case, body in bodies.items():
        if "compute_set" in body or "preset" in body or "links" in body:
            raise ProjectError(f"{case}: only plain `assumptions` requests can be combined")
        if body.get("exclude") or body.get("exclude_cases"):
            raise ProjectError(f"{case}: requests with exclusions can't be combined")
        if (runs := estimate_runs(body)) != 1:
            raise ProjectError(f"{case}: the request starts {runs} runs, not 1")

    first = bodies[options[0]]
    out: dict[str, Any] = {"user_specified_name": name}
    for field in SHARED_FIELDS:
        seen = {_canonical(b.get(field)) for b in bodies.values()}
        if len(seen) > 1:
            raise ProjectError(f"`{field}` differs between the cases; it applies to all")
        if first.get(field) is not None:
            out[field] = first[field]

    linked_any = False
    for kind in ITEM_KINDS:
        # key -> option -> item, keeping the order items first appear in.
        found: dict[tuple[Any, ...], dict[str, Mapping[str, Any]]] = {}
        for case, body in bodies.items():
            for item in body.get(kind) or []:
                found.setdefault(_key(kind, item), {})[case] = item
        items: list[dict[str, Any]] = []
        for per_case in found.values():
            valued = _valued(kind, next(iter(per_case.values())))
            rest = {
                case: _canonical(
                    {k: v for k, v in item.items() if k not in ("values", "link", "options")}
                )
                for case, item in per_case.items()
            }
            values = (
                {case: _single_value(kind, item, case) for case, item in per_case.items()}
                if valued
                else {}
            )
            if len(set(rest.values())) > 1:
                raise ProjectError(
                    f"{kind} item {_key(kind, next(iter(per_case.values())))} differs "
                    "between the cases in more than its value"
                )
            template = {
                k: v
                for k, v in next(iter(per_case.values())).items()
                if k not in ("values", "link", "options")
            }
            everywhere = len(per_case) == len(options)
            same = len({_canonical(v) for v in values.values()}) <= 1
            if everywhere and same:
                items.append(
                    {**template, **({"values": [next(iter(values.values()))]} if valued else {})}
                )
                continue
            present = [o for o in options if o in per_case]
            item = {**template, "link": link_key, "options": present}
            if valued:
                item["values"] = [values[o] for o in present]
            items.append(item)
            linked_any = True
        if items:
            out[kind] = items
    out.setdefault("assumptions", [])
    if not linked_any:
        raise ProjectError("the cases are all the same; there is nothing to link")
    out["links"] = [
        {
            "key": link_key,
            "label": link_label,
            "options": [{"key": o, "label": (labels or {}).get(o, o)} for o in options],
        }
    ]
    return out


def case_count(body: Mapping[str, Any]) -> int:
    """Runs a request with ``links`` starts, before ``exclude_cases``: each link is one
    dimension, and each unlinked item with several values another."""
    declared = {link["key"]: len(link["options"]) for link in body.get("links") or []}
    sizes: dict[str, int] = dict(declared)
    n = 1
    for kind in ITEM_KINDS:
        for item in body.get(kind) or []:
            link = item.get("link")
            if link:
                if link not in declared:
                    sizes[link] = max(sizes.get(link, 1), len(item.get("values") or [1]))
                continue
            if _valued(kind, item):
                n *= max(1, len(item.get("values") or []))
    for size in sizes.values():
        n *= size
    n -= len(body.get("exclude") or [])
    if body.get("include_base_case"):
        n += 1
    return max(n, 1)
