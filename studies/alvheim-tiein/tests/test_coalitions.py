from __future__ import annotations

import pandas as pd
import pytest

from alvheim_tiein import coalitions as co

GROUPS = ["Boyla+Frosk", "Volund", "Vilje+Skogul", "Tyrving"]


def test_case_names_follow_the_booking_release_project() -> None:
    assert co.coalition_case(frozenset(), GROUPS) == "baseline"
    assert co.coalition_case(frozenset(GROUPS), GROUPS) == "m_lift_all"
    assert co.coalition_case(frozenset(["Volund"]), GROUPS) == "m_lift_volund"
    pair = co.coalition_case(frozenset(["Tyrving", "Boyla+Frosk"]), GROUPS)
    assert pair == "m_lift_boyla_frosk__tyrving"
    plan = co.coalition_plan(GROUPS)
    assert len(plan) == 16 and plan["case"].is_unique
    assert plan["size"].value_counts().to_dict() == {0: 1, 1: 4, 2: 6, 3: 4, 4: 1}


def test_shapley_table_from_hub_values() -> None:
    g = ["a", "b"]
    hub = {"baseline": 100.0, "m_lift_a": 110.0, "m_lift_b": 105.0, "m_lift_all": 125.0}
    t = co.shapley_table(hub, g).set_index("group")
    assert t["phi"].to_dict() == pytest.approx({"a": 15.0, "b": 10.0})
    assert t.loc["a", "synergy"] == pytest.approx(5.0)
    assert t["share_of_total"].sum() == pytest.approx(1.0)
    with pytest.raises(KeyError, match="m_lift_b"):
        co.shapley_table({k: v for k, v in hub.items() if k != "m_lift_b"}, g)


def test_phi_to_licences() -> None:
    split = pd.DataFrame(
        {"group": ["a", "a", "b"], "license": ["L1", "L2", "L2"], "share": [0.6, 0.4, 1.0]}
    )
    phi = co.phi_to_licences({"a": 15.0, "b": 10.0}, split)
    assert phi.to_dict() == pytest.approx({"L1": 9.0, "L2": 16.0})


def test_interaction_2x2_and_order_averaged_split() -> None:
    def ser(v: float) -> pd.Series:
        return pd.Series({"x": v}, name="pv").rename_axis("license")

    out = co.interaction_2x2(ser(0.0), ser(10.0), ser(2.0), ser(15.0)).set_index("license")
    assert out.loc["x", "interaction"] == 3.0
    assert out.loc["x", "fl_part"] == 11.5
    assert out.loc["x", "policy_part"] == 3.5
    assert out.loc["x", "fl_part"] + out.loc["x", "policy_part"] == out.loc["x", "total"]
