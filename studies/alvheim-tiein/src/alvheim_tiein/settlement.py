"""Compare cases and settle who pays whom.

The settlement follows the structure of the Norwegian regulations on use of facilities
by others: the user (the new tie-in) pays the owners a tariff, and compensates loss or
postponement of their production at the profit that production would have earned. The
rules here are a transparent first model to discuss, not contract terms:

- ``compensation_flows``: each non-user licence whose value falls between the
  counterfactual and the tie-in case is paid its loss by the user licence(s). Gains are
  not clawed back unless ``symmetric=True``.
- ``tariff_change``: per-unit tariffs from ``economics.yaml`` on the change in the payer
  licences' volumes between the two cases.
- ``company_matrix``: licence-to-licence flows spread over both sides' company shares.

Tariffs and compensation are transfers: they cancel in total hub value, so the hub
objective is unchanged by settlement while company objectives are not.
"""

from __future__ import annotations

import datetime as dt
import itertools
import math
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass

import pandas as pd

from alvheim_tiein.economics import Reference, shares_at, split_to_companies

DEFAULT_VALUES = ("oil_sm3", "gas_sm3", "water_sm3", "oe_sm3", "cash_flow", "pv")


def totals(
    valued: pd.DataFrame,
    by: Sequence[str],
    *,
    case_col: str = "case_name",
    values: Sequence[str] = DEFAULT_VALUES,
) -> pd.DataFrame:
    return valued.groupby([case_col, *by], dropna=False)[list(values)].sum().reset_index()


def compare(
    valued: pd.DataFrame,
    base: str,
    alt: str,
    by: Sequence[str] = ("license",),
    *,
    case_col: str = "case_name",
    values: Sequence[str] = DEFAULT_VALUES,
) -> pd.DataFrame:
    """``alt - base`` per group, with both sides shown."""
    t = totals(valued[valued[case_col].isin([base, alt])], by, case_col=case_col, values=values)
    wide = t.pivot_table(
        index=list(by), columns=case_col, values=list(values), aggfunc="sum", fill_value=0.0
    )
    out = pd.DataFrame(index=wide.index)
    for v in values:
        b = wide.get((v, base), 0.0)
        a = wide.get((v, alt), 0.0)
        out[f"base_{v}"], out[f"alt_{v}"], out[f"delta_{v}"] = b, a, a - b
    return out.reset_index()


def decompose(
    valued: pd.DataFrame,
    without: str,
    with_: str,
    uncapped: str,
    by: Sequence[str] = ("license",),
    *,
    value: str = "pv",
    case_col: str = "case_name",
) -> pd.DataFrame:
    """Split the tie-in's impact on each group into hydraulic interference
    (``uncapped - without``: back-pressure with facility limits removed) and capacity
    displacement (``with - uncapped``: what the facility limits take away)."""
    t = totals(valued, by, case_col=case_col, values=[value])
    wide = t.pivot_table(
        index=list(by), columns=case_col, values=value, aggfunc="sum", fill_value=0.0
    )
    for case in (without, with_, uncapped):
        if case not in wide:
            raise KeyError(f"case {case!r} not in results")
    out = pd.DataFrame(
        {
            "total": wide[with_] - wide[without],
            "interference": wide[uncapped] - wide[without],
            "displacement": wide[with_] - wide[uncapped],
        }
    )
    return out.reset_index()


def compensation_flows(
    valued: pd.DataFrame,
    base: str,
    alt: str,
    user_licenses: Iterable[str],
    *,
    value: str = "pv",
    symmetric: bool = False,
    case_col: str = "case_name",
) -> pd.DataFrame:
    """Licence-level compensation from the user licence(s) to affected licences.

    With several user licences, each pays in proportion to its incremental oil
    equivalent."""
    users = list(user_licenses)
    d = compare(valued, base, alt, ("license",), case_col=case_col, values=[value, "oe_sm3"])
    unknown = set(users) - set(d["license"])
    if unknown:
        raise KeyError(f"user licence(s) not in results: {sorted(unknown)}")
    gains = d.set_index("license").loc[users, "delta_oe_sm3"].clip(lower=0.0)
    weights = gains / gains.sum() if gains.sum() > 0 else pd.Series(1.0 / len(users), index=users)
    affected = d[~d["license"].isin(users)]
    due = -affected.set_index("license")[f"delta_{value}"]
    if not symmetric:
        due = due[due > 0]
    rows = [
        {"payer_license": u, "payee_license": lic, "kind": "compensation", "amount": amount * w}
        for lic, amount in due.items()
        for u, w in weights.items()
        if amount != 0
    ]
    return pd.DataFrame(rows, columns=["payer_license", "payee_license", "kind", "amount"])


def tariff_flows(
    valued: pd.DataFrame,
    case: str,
    ref: Reference,
    *,
    discounted: bool = True,
    case_col: str = "case_name",
) -> pd.DataFrame:
    """Tariffs due in one case on the payer licences' volumes."""
    df = valued[valued[case_col] == case]
    rows = []
    for t in ref.economics.tariffs:
        part = df[df["license"] == t.payer_license]
        weight = part["discount_factor"] if discounted else 1.0
        amount = float((part[t.basis] * t.rate * weight).sum())
        rows.append(
            {
                "payer_license": t.payer_license,
                "payee_license": t.payee_license,
                "kind": "tariff",
                "amount": amount,
            }
        )
    return pd.DataFrame(rows, columns=["payer_license", "payee_license", "kind", "amount"])


def tariff_change(
    valued: pd.DataFrame, base: str, alt: str, ref: Reference, *, case_col: str = "case_name"
) -> pd.DataFrame:
    """Tariffs in ``alt`` minus those already due in ``base``: a brand-new licence pays
    its full tariff, an existing payer only pays on its extra volume."""
    keys = ["payer_license", "payee_license", "kind"]
    a = tariff_flows(valued, alt, ref, case_col=case_col).groupby(keys)["amount"].sum()
    b = tariff_flows(valued, base, ref, case_col=case_col).groupby(keys)["amount"].sum()
    return a.sub(b, fill_value=0.0).rename("amount").reset_index()


def company_matrix(flows: pd.DataFrame, shares: pd.DataFrame, as_of: dt.date) -> pd.DataFrame:
    """Payer company (rows) x payee company (columns). The diagonal is money a company
    pays itself through different licences; it nets out."""
    s = shares_at(shares, as_of)
    pay = flows.merge(
        s.rename(columns={"license": "payer_license", "company": "payer", "share": "ps"}),
        on="payer_license",
    )
    pay = pay.merge(
        s.rename(columns={"license": "payee_license", "company": "payee", "share": "rs"}),
        on="payee_license",
    )
    pay["amount"] = pay["amount"] * pay["ps"] * pay["rs"]
    companies = sorted(s["company"].unique())
    return pay.pivot_table(
        index="payer", columns="payee", values="amount", aggfunc="sum", fill_value=0.0
    ).reindex(index=companies, columns=companies, fill_value=0.0)


def net_positions(matrix: pd.DataFrame) -> pd.Series:
    """Received minus paid per company (positive = receives)."""
    return (matrix.sum(axis=0) - matrix.sum(axis=1)).rename("net_received")


@dataclass
class Settlement:
    licence_flows: pd.DataFrame
    company_matrix: pd.DataFrame
    net: pd.Series


def settle(
    valued: pd.DataFrame,
    ref: Reference,
    base: str,
    alt: str,
    user_licenses: Iterable[str],
    *,
    symmetric: bool = False,
    include_tariffs: bool = True,
    case_col: str = "case_name",
) -> Settlement:
    flows = compensation_flows(
        valued, base, alt, user_licenses, symmetric=symmetric, case_col=case_col
    )
    if include_tariffs and ref.economics.tariffs:
        flows = pd.concat(
            [flows, tariff_change(valued, base, alt, ref, case_col=case_col)], ignore_index=True
        )
    matrix = company_matrix(flows, ref.shares, ref.economics.valuation_date)
    return Settlement(flows, matrix, net_positions(matrix))


def objective_table(
    valued: pd.DataFrame,
    ref: Reference,
    *,
    transfers: Mapping[str, pd.Series] | None = None,
    case_col: str = "case_name",
) -> pd.DataFrame:
    """Per case: total hub NPV and each company's NPV (plus settlement transfers, if
    given per case as ``net_positions``), with the rank of each case under each
    objective."""
    hub = valued.groupby(case_col)["pv"].sum().rename("hub")
    by_company = split_to_companies(valued, ref.shares, value_cols=("pv",))
    comp = by_company.pivot_table(
        index=case_col, columns="company", values="pv", aggfunc="sum", fill_value=0.0
    )
    if transfers:
        for case, net in transfers.items():
            if case in comp.index:
                comp.loc[case] = comp.loc[case].add(net.reindex(comp.columns, fill_value=0.0))
    table = pd.concat([hub, comp], axis=1)
    for col in list(table.columns):
        table[f"rank_{col}"] = table[col].rank(ascending=False, method="min").astype(int)
    return table


def price_of_conflict(table: pd.DataFrame, company: str) -> dict[str, object]:
    """What the hub loses if the case best for ``company`` is chosen over the hub-best."""
    hub_best = table["hub"].idxmax()
    company_best = table[company].idxmax()
    return {
        "hub_best_case": hub_best,
        "company_best_case": company_best,
        "hub_value_lost": float(table.at[hub_best, "hub"] - table.at[company_best, "hub"]),
        "company_value_gained": float(
            table.at[company_best, company] - table.at[hub_best, company]
        ),
    }


def shapley_values(
    players: Sequence[str],
    value: Callable[[frozenset[str]], float] | Mapping[frozenset[str], float],
) -> dict[str, float]:
    """Exact Shapley values: each player's average marginal contribution over all join
    orders. ``value`` gives the worth of every coalition (e.g. hub NPV with only those
    licence groups producing); the empty coalition should be worth 0 or the hub's
    no-production value."""
    n = len(players)
    if n > 12:
        raise ValueError("exact Shapley values need 2^n coalitions; group players to 12 or fewer")
    v = value if callable(value) else (lambda s: value[s])
    cache: dict[frozenset[str], float] = {}

    def worth(s: frozenset[str]) -> float:
        if s not in cache:
            cache[s] = float(v(s))
        return cache[s]

    phi = dict.fromkeys(players, 0.0)
    for i in players:
        others = [p for p in players if p != i]
        for k in range(n):
            weight = math.factorial(k) * math.factorial(n - k - 1) / math.factorial(n)
            for subset in itertools.combinations(others, k):
                s = frozenset(subset)
                phi[i] += weight * (worth(s | {i}) - worth(s))
    return phi


# ------------------------------------------------------------ total then settle
# research/22 scheme 2: the surplus G of a chosen plan over the reference is split by a
# rule into awards a_l >= 0 (sum G); licence l receives t_l = a_l - delta_l.
AWARD_RULES = ("minimal", "proportional", "equal", "shapley")


def surplus(
    values: pd.DataFrame, reference: str, case: str, *, by: str = "license", value: str = "pv"
) -> pd.Series:
    """``Δ_l = V_l(case) - V_l(reference)`` from a participant ledger (case, ``by``,
    ``value`` columns, e.g. :func:`alvheim_tiein.ledgers.participant_ledger`)."""
    t = values[values["case"].isin([reference, case])]
    wide = t.pivot_table(index=by, columns="case", values=value, aggfunc="sum", fill_value=0.0)
    for c in (reference, case):
        if c not in wide:
            raise KeyError(f"case {c!r} not in the ledger")
    return (wide[case] - wide[reference]).rename("delta")


def awards(
    delta: pd.Series,
    rule: str,
    *,
    basis: pd.Series | None = None,
    phi: pd.Series | None = None,
) -> pd.Series:
    """Final award per licence under ``rule``; every award >= 0 and they sum to G.

    - ``minimal``: G Δ⁺ / ΣΔ⁺ (losers made whole, winners keep the rest pro rata);
    - ``proportional``: G r / Σr with ``basis`` r (booked capacity, decision 3);
    - ``equal``: G / n;
    - ``shapley``: G φ⁺ / Σφ⁺ (licence-level ``phi`` from a consistent coalition set)."""
    g = float(delta.sum())
    if g <= 0:
        raise ValueError(f"surplus G = {g:,.0f} is not positive: the plan is no improvement")
    idx = delta.index
    if rule == "minimal":
        w = delta.clip(lower=0.0)
    elif rule == "proportional":
        if basis is None:
            raise ValueError("the proportional rule needs the booked capacity basis")
        w = basis.reindex(idx, fill_value=0.0).clip(lower=0.0)
    elif rule == "equal":
        w = pd.Series(1.0, index=idx)
    elif rule == "shapley":
        if phi is None:
            raise ValueError("the shapley rule needs licence-level Shapley values")
        w = phi.reindex(idx, fill_value=0.0).clip(lower=0.0)
    else:
        raise ValueError(f"unknown rule {rule!r}; use one of {AWARD_RULES}")
    if float(w.sum()) <= 0:
        raise ValueError(f"rule {rule!r}: the weights sum to zero")
    return (g * w / float(w.sum())).rename("award")


def transfers(delta: pd.Series, award: pd.Series) -> pd.Series:
    """``t = a - Δ``: positive received, negative paid. Sums to zero."""
    return (award.reindex(delta.index, fill_value=0.0) - delta).rename("transfer")


def transfer_profile(
    delta_by_period: pd.DataFrame, award: pd.Series, *, value: str = "delta"
) -> pd.DataFrame:
    """Transfers over time: ``t_{l,t} = a_l G_t / G - Δ_{l,t}``, zero-sum in every
    period and summing to ``t_l`` per licence. ``delta_by_period`` has license, period
    and ``value``."""
    d = delta_by_period
    g_t = d.groupby("period")[value].sum()
    g = float(g_t.sum())
    out = d[["license", "period"]].copy()
    out["award"] = d["license"].map(award).fillna(0.0) * d["period"].map(g_t) / g
    out["delta"] = d[value].to_numpy()
    out["pv"] = out["award"] - out["delta"]
    return out.reset_index(drop=True)


def delta_by_period(
    ledger: pd.DataFrame, reference: str, case: str, *, value: str = "pv"
) -> pd.DataFrame:
    """``Δ_{l,t}`` per licence and period between two cases of a participant ledger."""
    t = ledger[ledger["case"].isin([reference, case])]
    wide = t.pivot_table(
        index=["license", "period"], columns="case", values=value, aggfunc="sum", fill_value=0.0
    )
    for c in (reference, case):
        if c not in wide:
            wide[c] = 0.0
    return (wide[case] - wide[reference]).rename("delta").reset_index()


def pairwise_flows(transfer: pd.Series, *, kind: str = "settlement") -> pd.DataFrame:
    """Payer to payee licence flows for a zero-sum transfer vector: each payer pays
    each payee in proportion to what the payee receives."""
    pay = (-transfer).clip(lower=0.0)
    get = transfer.clip(lower=0.0)
    total = float(get.sum())
    rows = [
        {"payer_license": p, "payee_license": r, "kind": kind, "amount": a * b / total}
        for p, a in pay.items()
        if a > 0
        for r, b in get.items()
        if b > 0
    ]
    return pd.DataFrame(rows, columns=["payer_license", "payee_license", "kind", "amount"])


def company_profile(
    licence_rows: pd.DataFrame, shares: pd.DataFrame, *, value: str = "pv"
) -> pd.DataFrame:
    """Licence rows (license, period, ``value``) spread over the equity valid in each
    period, summed per company and period."""
    df = licence_rows.merge(shares, on="license", how="inner")
    active = (df["valid_from"] <= df["period"]) & (
        df["valid_to"].isna() | (df["valid_to"] > df["period"])
    )
    df = df[active]
    out = (df[value] * df["share"]).groupby([df["company"], df["period"]]).sum()
    return out.rename(value).reset_index()


def company_matrix_by_period(profile: pd.DataFrame, shares: pd.DataFrame) -> pd.DataFrame:
    """Per period: payer company, payee company and amount, from a transfer profile
    (license, period, pv). Each period's matrix nets to that period's transfers."""
    parts = []
    for period, g in profile.groupby("period"):
        flows = pairwise_flows(g.set_index("license")["pv"])
        if flows.empty:
            continue
        m = company_matrix(flows, shares, pd.Timestamp(period).date())
        long = m.stack().rename("amount").reset_index()
        long.columns = ["payer", "payee", "amount"]
        parts.append(long[long["amount"] != 0].assign(period=period))
    if not parts:
        return pd.DataFrame(columns=["period", "payer", "payee", "amount"])
    return pd.concat(parts, ignore_index=True)[["period", "payer", "payee", "amount"]]


def company_no_loss(
    delta_rows: pd.DataFrame,
    profile: pd.DataFrame,
    shares: pd.DataFrame,
    *,
    eps: float = 0.0,
) -> pd.DataFrame:
    """Per company: its change, its transfers and the final position; ``ok`` where
    it ends at or above ``-eps``. Licences can all gain while a company loses, because
    equity differs across licences."""
    d = company_profile(delta_rows.rename(columns={"delta": "pv"}), shares)
    t = company_profile(profile, shares)
    out = pd.concat(
        [
            d.groupby("company")["pv"].sum().rename("delta"),
            t.groupby("company")["pv"].sum().rename("transfer"),
        ],
        axis=1,
    ).fillna(0.0)
    out["final"] = out["delta"] + out["transfer"]
    out["ok"] = out["final"] >= -eps
    return out.rename_axis("company").reset_index()


def price_of_no_transfers(
    table: pd.DataFrame, reference: str, *, companies: Sequence[str], eps: float = 0.0
) -> dict[str, object]:
    """Hub value given up by choosing the best case in which no company loses against
    ``reference`` (no transfers needed) over the hub-best case. ``table`` from
    :func:`objective_table`."""
    gains = table[list(companies)].sub(table.loc[reference, list(companies)], axis=1)
    ok = (gains >= -eps).all(axis=1)
    best = table["hub"].idxmax()
    best_nt = table.loc[ok, "hub"].idxmax() if ok.any() else None
    return {
        "best_case": best,
        "best_no_transfer_case": best_nt,
        "price_of_no_transfers": (
            float(table.at[best, "hub"] - table.at[best_nt, "hub"]) if best_nt else float("nan")
        ),
        "no_transfer_cases": [str(c) for c in table.index[ok]],
    }


def in_kind_check(
    case_values: pd.Series,
    before_values: pd.Series,
    tie_in_transfers: pd.Series | None = None,
    *,
    eps: float = 0.0,
) -> pd.DataFrame:
    """Everyone better off in kind: ``V_k(R) + T_k - V_k(S0) >= 0`` per company, with
    ``T_k`` the tie-in settlement (tariffs and compensation) and no other money."""
    idx = case_values.index.union(before_values.index)
    t = tie_in_transfers if tie_in_transfers is not None else pd.Series(dtype=float)
    out = pd.DataFrame(
        {
            "value_case": case_values.reindex(idx, fill_value=0.0),
            "tie_in_transfer": t.reindex(idx, fill_value=0.0),
            "value_before": before_values.reindex(idx, fill_value=0.0),
        }
    )
    out["margin"] = out["value_case"] + out["tie_in_transfer"] - out["value_before"]
    out["ok"] = out["margin"] >= -eps
    return out.rename_axis("company").reset_index()
