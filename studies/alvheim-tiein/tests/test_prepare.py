from __future__ import annotations

from typing import Any

import pytest

from alvheim_tiein import prepare
from alvheim_tiein.project import Project

FL1 = r"RESOLVE.MODULE[0].MOD[0].EQUIP[754]"

PROJECT = {
    "name": "Tie-in",
    "type": "case_comparison",
    "asset": "Alvheim",
    "model_id": "m-1",
    "switch": {
        "label": "Froskelaar",
        "off_from": "2026-07-01",
        "wells": [{"name": "FL1", "path": FL1}],
    },
    "cases": [
        {"name": "baseline", "baseline": True, "switch": "off"},
        {
            "name": "uncapped",
            "switch": "on",
            "changes": {
                "dataobject_tables": [
                    {
                        "object_alias": "Capacities",
                        "table_name": "TotalGas_Capacity",
                        "index": 0,
                        "values": [5e4],
                    },
                    {
                        "object_alias": "Gas_upgrade",
                        "table_name": "TotalGas_capacity",
                        "index": 0,
                        "values": [5e4],
                    },
                ]
            },
        },
        {
            "name": "uncapped_again",
            "based_on": "uncapped",
            "changes": {
                "dataobject_tables": [
                    {
                        "object_alias": "Capacities",
                        "table_name": "TotalGas_Capacity",
                        "index": 0,
                        "values": [6e4],
                    }
                ]
            },
        },
    ],
}


class FakeBrowser:
    def __init__(self, matches: list[dict[str, Any]]) -> None:
        self.matches = matches

    def browse(
        self, model_id: str, path: str | None = None, *, search: str | None = None, limit: int = 50
    ) -> dict[str, Any]:
        name = (search or "").lower()
        return {"matches": [m for m in self.matches if name in m["name"].lower()]}


MATCHES = [
    {"path": FL1, "name": "FL1", "type": "EQUIPMENT", "equipment_type": "WELL"},
    {
        "path": "P/FL1_PROD_MF",
        "name": "FL1_PROD_MF",
        "type": "EQUIPMENT",
        "equipment_type": "JOINT",
    },
    {"path": "P/FL2", "name": "FL2", "type": "EQUIPMENT", "equipment_type": "WELL"},
]


def test_find_equipment_picks_the_exact_well() -> None:
    eq = prepare.find_equipment(FakeBrowser(MATCHES), "m", "fl1")
    assert eq.path == FL1
    with pytest.raises(prepare.PrepareError, match="found 0"):
        prepare.find_equipment(FakeBrowser(MATCHES), "m", "FL1_PROD_MF")
    with pytest.raises(prepare.PrepareError, match="FL1_PROD_MF"):
        prepare.find_equipment(FakeBrowser(MATCHES[1:]), "m", "FL1")


def test_cells_come_from_every_case_once() -> None:
    project = Project.model_validate(PROJECT)
    assert prepare.dataobject_cells(project) == [
        ("Capacities", "TotalGas_Capacity", 0),
        ("Gas_upgrade", "TotalGas_capacity", 0),
    ]


def test_cells_without_a_switch_expand_row_ranges() -> None:
    project = Project.model_validate(
        {
            "name": "Booking release",
            "type": "scenario_comparison",
            "asset": "Alvheim",
            "model_id": "m-1",
            "cases": [
                {"name": "base", "baseline": True},
                {
                    "name": "lift",
                    "changes": {
                        "dataobject_tables": [
                            {
                                "object_alias": "Bookings_oil",
                                "table_name": "Tyrving",
                                "rows": "0-1,3",
                                "value": 99999,
                            }
                        ]
                    },
                },
            ],
        }
    )
    assert project.switch is None
    assert prepare.dataobject_cells(project) == [
        ("Bookings_oil", "Tyrving", 0),
        ("Bookings_oil", "Tyrving", 1),
        ("Bookings_oil", "Tyrving", 3),
    ]


def test_check_cells_reports_missing_tables_and_indexes() -> None:
    tables = {
        "tables": [
            {
                "object_alias": "Capacities",
                "object_type": "FlexDataStore",
                "table_name": "TotalGas_Capacity",
                "values": [152.6],
            },
            {
                "object_alias": "Capacities",
                "object_type": "FlexDataStore",
                "table_name": "Maximumwaterrate",
                "values": [226548],
            },
        ]
    }
    cells = [
        ("Capacities", "TotalGas_Capacity", 0),
        ("Capacities", "Maximumwaterrate", 3),
        ("Capacities", "Oil", 0),
        ("Gas_upgrade", "TotalGas_capacity", 0),
    ]
    values, problems = prepare.check_cells(tables, cells)
    assert values == {("Capacities", "TotalGas_Capacity", 0): 152.6}
    assert any("out of range" in p for p in problems)
    assert any("Capacities.Oil doesn't exist; Capacities has" in p for p in problems)
    assert any("no DataObject Gas_upgrade" in p for p in problems)
