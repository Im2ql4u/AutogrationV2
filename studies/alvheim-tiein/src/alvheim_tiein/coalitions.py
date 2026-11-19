"""Attribution from coalition runs (research/22, scheme 2).

- **Shapley over booking groups.** v(S) is the hub value change when the groups in S
  have their bookings released and everything else is at reference. All 2^n coalitions
  must come from one grid, VM size, model registration and reference data. Σ φ_g =
  v(all): the gain from booking flexibility, attributed to the groups. Groups span
  licences, so φ goes to licences by an agreed split within each group.
- **The 2×2.** Froskelår off/on under the reference and the new policy. The
  interaction I = v(on,new) - v(on,ref) - v(off,new) + v(off,ref) goes wholly to
  whichever settlement comes second, so it is shown apart or split by averaging both
  orders.
"""

from __future__ import annotations

import itertools
import re
from collections.abc import Callable, Mapping, Sequence

import pandas as pd

from alvheim_tiein.settlement import shapley_values


def slug(group: str) -> str:
    """``Boyla+Frosk`` -> ``boyla_frosk`` (the booking-release project's case names)."""
    return re.sub(r"[^a-z0-9]+", "_", group.lower()).strip("_")


def coalitions(groups: Sequence[str]) -> list[frozenset[str]]:
    return [frozenset(c) for k in range(len(groups) + 1) for c in itertools.combinations(groups, k)]


def coalition_case(
    coalition: frozenset[str],
    groups: Sequence[str],
    *,
    prefix: str = "m",
    none: str = "baseline",
) -> str:
    """Case name of a coalition, following the booking-release project:
    ∅ -> ``baseline``, all -> ``m_lift_all``, {g} -> ``m_lift_<g>``, otherwise
    ``m_lift_<g1>__<g2>`` in the order of ``groups``."""
    if not coalition:
        return none
    if set(coalition) == set(groups):
        return f"{prefix}_lift_all"
    return f"{prefix}_lift_" + "__".join(slug(g) for g in groups if g in coalition)


def coalition_plan(
    groups: Sequence[str], *, prefix: str = "m", none: str = "baseline"
) -> pd.DataFrame:
    """Every coalition, its case name and size: the runs a Shapley study needs."""
    rows = [
        {
            "coalition": "+".join(g for g in groups if g in c) or "(none)",
            "size": len(c),
            "case": coalition_case(c, groups, prefix=prefix, none=none),
        }
        for c in coalitions(groups)
    ]
    return pd.DataFrame(rows)


def coalition_values(
    hub: Mapping[str, float],
    groups: Sequence[str],
    *,
    case_for: Callable[[frozenset[str]], str] | None = None,
) -> dict[frozenset[str], float]:
    """``v(S) = V(case(S)) - V(case(∅))`` from hub values per case. Every coalition must
    have a value."""
    name = case_for or (lambda c: coalition_case(c, groups))
    missing = [name(c) for c in coalitions(groups) if name(c) not in hub]
    if missing:
        raise KeyError(f"{len(missing)} coalition case(s) without a result: {missing}")
    empty = float(hub[name(frozenset())])
    return {c: float(hub[name(c)]) - empty for c in coalitions(groups)}


def shapley_table(
    hub: Mapping[str, float],
    groups: Sequence[str],
    *,
    case_for: Callable[[frozenset[str]], str] | None = None,
    tol: float = 1e-6,
) -> pd.DataFrame:
    """φ per group, its standalone value v({g}) and its share of v(all). Efficiency
    (Σφ = v(all)) is checked."""
    v = coalition_values(hub, groups, case_for=case_for)
    phi = shapley_values(list(groups), v)
    total = v[frozenset(groups)]
    if abs(sum(phi.values()) - total) > tol * max(1.0, abs(total)):
        raise AssertionError("Shapley values do not add up to v(all)")
    out = pd.DataFrame(
        {
            "group": list(groups),
            "phi": [phi[g] for g in groups],
            "standalone": [v[frozenset([g])] for g in groups],
        }
    )
    out["share_of_total"] = out["phi"] / total if total else float("nan")
    out["synergy"] = out["phi"] - out["standalone"]
    return out


def phi_to_licences(phi: Mapping[str, float], split: pd.DataFrame) -> pd.Series:
    """Group φ to licences by a split within each group (group, license, share; e.g.
    the reference case's production share over the whole horizon)."""
    s = split.groupby(["group", "license"], as_index=False)["share"].sum()
    s["share"] = s["share"] / s.groupby("group")["share"].transform("sum")
    s["phi"] = s["group"].map(phi).astype(float) * s["share"]
    return s.dropna(subset=["phi"]).groupby("license")["phi"].sum().rename("phi")


def interaction_2x2(
    off_ref: pd.Series, on_ref: pd.Series, off_new: pd.Series, on_new: pd.Series
) -> pd.DataFrame:
    """Per participant (index): the Froskelår effect under each policy, the policy
    effect with FL off and on, the interaction, and the average-of-both-orders split
    of the total change into a Froskelår part and a policy part."""
    idx = off_ref.index.union(on_ref.index).union(off_new.index).union(on_new.index)
    a, b, c, d = (s.reindex(idx, fill_value=0.0) for s in (off_ref, on_ref, off_new, on_new))
    out = pd.DataFrame(index=idx)
    out["fl_effect_ref"] = b - a
    out["fl_effect_new"] = d - c
    out["policy_effect_off"] = c - a
    out["policy_effect_on"] = d - b
    out["interaction"] = d - b - c + a
    out["fl_part"] = (out["fl_effect_ref"] + out["fl_effect_new"]) / 2
    out["policy_part"] = (out["policy_effect_off"] + out["policy_effect_on"]) / 2
    out["total"] = d - a
    return out.rename_axis(off_ref.index.name or "participant").reset_index()
