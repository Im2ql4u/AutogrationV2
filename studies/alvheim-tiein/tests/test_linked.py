import pytest

from alvheim_tiein import linked
from alvheim_tiein.project import ProjectError


def _cell(index: int, value: float, table: str = "MaxLiquidRate") -> dict:
    return {
        "object_alias": "Wells_constraints",
        "table_name": table,
        "index": index,
        "values": [value],
    }


def _body(**items: list) -> dict:
    return {
        "user_specified_name": "x",
        "asset": "Alvheim",
        "vm_size": "Standard_D4ads_v5",
        "tracked_variables": ["a"],
        "assumptions": [],
        **items,
    }


OFF_EVENT = {
    "operation": "schedule",
    "path": "RESOLVE.MODULE[0].MOD[0].EQUIP[754]",
    "schedule": {"index": 900, "date": "2027-01-01", "action": "mask"},
}


def test_shared_items_go_in_every_case_and_differences_on_the_link():
    bodies = {
        "off": _body(assumptions=[OFF_EVENT], dataobject_tables=[_cell(1, 5.0), _cell(42, 0)]),
        "on": _body(dataobject_tables=[_cell(1, 5.0), _cell(2, 7.0)]),
        "lift": _body(dataobject_tables=[_cell(1, 5.0), _cell(2, 9.0)]),
    }
    out = linked.combine(bodies, name="wave 1")

    assert out["user_specified_name"] == "wave 1"
    assert out["asset"] == "Alvheim"
    assert out["tracked_variables"] == ["a"]
    assert out["links"] == [
        {
            "key": "case",
            "label": "Case",
            "options": [
                {"key": "off", "label": "off"},
                {"key": "on", "label": "on"},
                {"key": "lift", "label": "lift"},
            ],
        }
    ]
    assert out["assumptions"] == [{**OFF_EVENT, "link": "case", "options": ["off"]}]
    cells = {c["index"]: c for c in out["dataobject_tables"]}
    assert cells[1] == _cell(1, 5.0)
    assert cells[42] == {**_cell(42, 0), "link": "case", "options": ["off"]}
    assert cells[2] == {
        **_cell(2, 7.0),
        "values": [7.0, 9.0],
        "link": "case",
        "options": ["on", "lift"],
    }
    assert linked.case_count(out) == 3


def test_a_shared_item_with_different_values_is_linked_in_every_option():
    bodies = {
        "a": _body(dataobject_tables=[_cell(1, 1.0)]),
        "b": _body(dataobject_tables=[_cell(1, 2.0)]),
    }
    out = linked.combine(bodies, name="n", link_key="scheme", labels={"a": "Scheme A"})
    assert out["dataobject_tables"] == [
        {**_cell(1, 1.0), "values": [1.0, 2.0], "link": "scheme", "options": ["a", "b"]}
    ]
    assert out["links"][0]["options"][0] == {"key": "a", "label": "Scheme A"}


@pytest.mark.parametrize(
    ("bodies", "message"),
    [
        ({"a": _body()}, "at least two"),
        ({"a": _body(), "b": _body()}, "nothing to link"),
        ({"a": _body(), "b": {**_body(), "vm_size": "Standard_D8ads_v5"}}, "vm_size"),
        (
            {"a": _body(dataobject_tables=[{**_cell(1, 1.0), "values": [1, 2]}]), "b": _body()},
            "runs, not 1",
        ),
        ({"a b": _body(), "c": _body()}, "no spaces"),
        ({"a": {**_body(), "exclude": [2]}, "b": _body()}, "exclusions"),
    ],
)
def test_combine_rejects(bodies, message):
    with pytest.raises(ProjectError, match=message):
        linked.combine(bodies, name="n")


def test_case_count_multiplies_links_and_unlinked_sweeps():
    body = {
        "links": [
            {"key": "fl", "options": ["off", "on"]},
            {"key": "scheme", "options": ["a", "b", "c"]},
        ],
        "assumptions": [{"path": "p", "property_name": "x", "values": [1, 2]}],
        "dataobject_tables": [
            {**_cell(1, 0), "link": "fl", "options": ["off"]},
            {**_cell(2, 0), "values": [1, 2, 3], "link": "scheme"},
            {**_cell(3, 0), "values": [4, 5], "link": "undeclared"},
        ],
    }
    assert linked.case_count(body) == 2 * 3 * 2 * 2
    assert linked.case_count({**body, "exclude": [1, 2], "include_base_case": True}) == 23
