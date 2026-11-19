"""Scheme 4: restructure bookings when Froskelår opens (research/22).

Bookings are caps on each group's rates per phase and period. Reference runs:

- **S0**: Froskelår off, today's bookings;
- **S1**: Froskelår on, today's bookings (M BASE): bookings ``B``, production ``q1``;
- **S2**: Froskelår on, bookings lifted (M LIFT): each group's demand ``d``, an upper
  bound on what a restructure can give it.

Families (each a booking plan: group, period, phase, booked_sm3d, written to the model
by :func:`alvheim_tiein.levers.booking_plan_cells`):

- **R1** use it or lend it (:func:`r1_lend`);
- **R2** value-neutral capacity swaps over time (:func:`r2_swaps`);
- **R3** a Froskelår liquid cap (:func:`r3_fl_caps`, per-well cells);
- **R4** clean-sheet re-split of the envelope per window (:func:`r4_resplit`).

Candidates are ranked before any run by a crude surrogate (:func:`surrogate`); it only
picks what to simulate and never reports value. The swap book (:func:`swap_book`)
shows, per company and period, the booked capacity given up and received.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from alvheim_tiein.bookings import MONTHLY_TABLES, booking_cells
from alvheim_tiein.economics import Reference, unit_prices
from alvheim_tiein.ledgers import discount_factors, split_for_periods

PHASES = ("oil", "gas")
PLAN_COLUMNS = ["group", "period", "phase", "booked_sm3d"]
KEYS = ["group", "period", "phase"]


def _norm(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    out["period"] = pd.to_datetime(out["period"]).astype("datetime64[ns]")
    return out


# ---------------------------------------------------------------------- state
def booking_state(
    booked: pd.DataFrame,
    produced: pd.DataFrame,
    demand: pd.DataFrame,
    *,
    phases: Sequence[str] = PHASES,
    tol: float = 0.01,
) -> pd.DataFrame:
    """Per group, period and phase (booked phases only): booking ``B``, S1 production
    ``q1``, S2 demand ``d``, and

    - ``unused`` = (B - q1)⁺ for groups below their cap in S1 (what R1 can lend);
    - ``unmet`` = (d - B)⁺ (what a group would add without its cap);
    - ``slack`` = (B - max(q1, d))⁺ (capacity unused even when uncapped: what R2 can
      give without a loss);
    - ``at_cap``: S1 production within ``tol`` of the booking.

    ``booked`` has booked_sm3d; ``produced`` and ``demand`` have produced_sm3d."""
    b = _norm(booked)[[*KEYS, "booked_sm3d"]].rename(columns={"booked_sm3d": "booked"})
    b = b[b["phase"].isin(phases)].dropna(subset=["booked"])
    q = _norm(produced)[[*KEYS, "produced_sm3d"]].rename(columns={"produced_sm3d": "q1"})
    d = _norm(demand)[[*KEYS, "produced_sm3d"]].rename(columns={"produced_sm3d": "demand"})
    s = b.merge(q, on=KEYS, how="left").merge(d, on=KEYS, how="left")
    s[["q1", "demand"]] = s[["q1", "demand"]].fillna(0.0)
    s["at_cap"] = s["q1"] >= (1 - tol) * s["booked"]
    s["unused"] = np.where(s["at_cap"], 0.0, (s["booked"] - s["q1"]).clip(lower=0.0))
    s["unmet"] = (s["demand"] - s["booked"]).clip(lower=0.0)
    s["slack"] = (s["booked"] - np.maximum(s["q1"], s["demand"])).clip(lower=0.0)
    return s.sort_values(KEYS).reset_index(drop=True)


def from_satisfaction(
    satisfaction: pd.DataFrame, s1: str, s2: str, *, case_col: str = "case_name", **kw: object
) -> pd.DataFrame:
    """:func:`booking_state` from :meth:`BookingReport.satisfaction` of a project with
    the S1 and S2 cases."""
    a = satisfaction[satisfaction[case_col] == s1]
    b = satisfaction[satisfaction[case_col] == s2]
    if a.empty or b.empty:
        raise KeyError(f"cases {s1!r} and {s2!r} must both have results")
    return booking_state(a, a, b, **kw)  # type: ignore[arg-type]


def plan_of(state: pd.DataFrame, column: str = "booked") -> pd.DataFrame:
    return state[KEYS].assign(booked_sm3d=state[column].to_numpy())[PLAN_COLUMNS]


def booking_windows(tables: Mapping[str, object], periods: Sequence[pd.Timestamp]) -> pd.Series:
    """``booking`` for steps that read the monthly tables, ``future`` for the rest."""
    cells = booking_cells(tables, periods)  # type: ignore[arg-type]
    monthly = cells["object_alias"].isin(set(MONTHLY_TABLES.values()))
    per = cells.assign(monthly=monthly).groupby("period")["monthly"].any()
    return per.map({True: "booking", False: "future"}).rename("window")


# ------------------------------------------------------------------- R1 lend
def r1_lend(state: pd.DataFrame, lam: float = 1.0) -> pd.DataFrame:
    """Use it or lend it: per period and phase, a share ``lam`` of the capacity groups
    left unused in S1 goes to groups at their cap, pro rata to their unmet demand and
    never more than it. The envelope is unchanged and no lender falls below what it
    used."""
    if not 0.0 <= lam <= 1.0:
        raise ValueError("lam must be in [0, 1]")
    s = state.copy()
    s["need"] = np.where(s["at_cap"], s["unmet"], 0.0)
    g = s.groupby(["period", "phase"])
    pool = lam * g["unused"].transform("sum")
    need = g["need"].transform("sum")
    unused = g["unused"].transform("sum")
    lent = np.minimum(pool, need)
    s["received"] = np.where(need > 0, s["need"] * lent / need.where(need > 0, 1.0), 0.0)
    s["given"] = np.where(unused > 0, s["unused"] * lent / unused.where(unused > 0, 1.0), 0.0)
    s["new"] = s["booked"] + s["received"] - s["given"]
    return plan_of(s, "new")


# ------------------------------------------------------------------ R2 swaps
@dataclass
class Swap:
    phase: str
    receiver: str
    """Gets ``amount_in`` in ``period_in`` from ``giver`` ..."""
    giver: str
    """... and gives ``amount_out`` back in ``period_out``."""
    period_in: pd.Timestamp
    amount_in: float
    period_out: pd.Timestamp
    amount_out: float
    value_each_way: float
    gain: float

    def as_dict(self) -> dict[str, object]:
        return dict(self.__dict__)


@dataclass
class SwapResult:
    plan: pd.DataFrame
    swaps: list[Swap] = field(default_factory=list)

    def table(self) -> pd.DataFrame:
        return pd.DataFrame([s.as_dict() for s in self.swaps])


def r2_swaps(
    state: pd.DataFrame,
    worth: pd.DataFrame,
    *,
    max_swaps: int = 20,
    min_gain: float = 0.0,
) -> SwapResult:
    """Greedy value-neutral capacity swaps over time.

    Group g gets Δ' in t (where it is capped) from h, and gives Δ in t' (where it has
    slack) to h, with Δ' w_t = Δ w_t' (``worth`` w: value of 1 Sm3/d over the period,
    :func:`unit_values`). Each period's envelope is unchanged. Under the surrogate the
    gain is the value both sides add, 2 Δ' w_t. The best swap is applied and the state
    updated until no swap gains more than ``min_gain`` or ``max_swaps`` is reached."""
    s = state.merge(worth[["period", "phase", "worth"]], on=["period", "phase"], how="left")
    if s["worth"].isna().any():
        raise ValueError("no unit value for some periods; extend the price deck")
    idx = ["phase", "period"]
    booked = s.pivot_table(index=idx, columns="group", values="booked", aggfunc="first")
    slack = s.pivot_table(index=idx, columns="group", values="slack", aggfunc="first")
    unmet = s.pivot_table(index=idx, columns="group", values="unmet", aggfunc="first")
    slack, unmet = slack.reindex_like(booked).fillna(0.0), unmet.reindex_like(booked).fillna(0.0)
    w = s.groupby(idx)["worth"].first().reindex(booked.index)
    groups = list(booked.columns)
    swaps: list[Swap] = []
    for _ in range(max_swaps):
        best: tuple[float, str, str, str, pd.Timestamp, pd.Timestamp] | None = None
        for phase in booked.index.get_level_values("phase").unique():
            sl, un, wv = slack.loc[phase], unmet.loc[phase], w.loc[phase].to_numpy()
            for g in groups:
                for h in groups:
                    if g == h:
                        continue
                    a = np.minimum(sl[h].to_numpy(), un[g].to_numpy()) * wv
                    c = np.minimum(sl[g].to_numpy(), un[h].to_numpy()) * wv
                    t_in, t_out = int(np.argmax(a)), int(np.argmax(c))
                    value = float(min(a[t_in], c[t_out]))
                    if value > 0 and (best is None or value > best[0]):
                        best = (value, str(phase), g, h, sl.index[t_in], sl.index[t_out])
        if best is None or 2 * best[0] <= min_gain:
            break
        value, phase, g, h, p_in, p_out = best
        d_in = value / float(w.loc[(phase, p_in)])
        d_out = value / float(w.loc[(phase, p_out)])
        booked.loc[(phase, p_in), g] += d_in
        booked.loc[(phase, p_in), h] -= d_in
        booked.loc[(phase, p_out), g] -= d_out
        booked.loc[(phase, p_out), h] += d_out
        unmet.loc[(phase, p_in), g] -= d_in
        slack.loc[(phase, p_in), h] -= d_in
        slack.loc[(phase, p_out), g] -= d_out
        unmet.loc[(phase, p_out), h] -= d_out
        swaps.append(Swap(phase, g, h, p_in, d_in, p_out, d_out, value, 2 * value))
    plan = (
        booked.stack()
        .rename("booked_sm3d")
        .dropna()
        .reset_index()[PLAN_COLUMNS]
        .sort_values(KEYS)
        .reset_index(drop=True)
    )
    return SwapResult(plan, swaps)


# ---------------------------------------------------------------- R3 FL caps
def r3_fl_caps(
    well_rates: pd.DataFrame,
    phi: float,
    *,
    wells: Sequence[str] = ("FL1", "FL2"),
    phase: str = "liquid",
) -> dict[str, float]:
    """``MaxLiquidRate`` per Froskelår well: ``phi`` times its peak S2 rate (one value:
    the cap is constant over time without a model edit). ``well_rates`` has
    identifier, phase and rate_sm3d (S2 only)."""
    r = well_rates[(well_rates["phase"] == phase) & well_rates["identifier"].isin(wells)]
    peak = r.groupby("identifier")["rate_sm3d"].max()
    missing = sorted(set(wells) - set(peak.index))
    if missing:
        raise KeyError(f"no S2 {phase} rate for {missing}")
    return {w: float(phi * peak[w]) for w in wells}


# --------------------------------------------------------------- R4 re-split
def r4_resplit(
    state: pd.DataFrame,
    *,
    windows: pd.Series | None = None,
    mode: str = "pro_rata",
    priority: Mapping[str, float] | None = None,
    per_period: bool = False,
) -> pd.DataFrame:
    """Re-split each period's envelope E_t = Σ_g B_g(t) across the groups.

    - ``pro_rata``: by S2 demand, with one share per window (``windows``: period ->
      label, e.g. :func:`booking_windows`) or per period;
    - ``value``: per period, groups' demand is filled in ``priority`` order (highest
      first) until E_t is used; what is left goes pro rata to today's bookings."""
    s = state.copy()
    s["window"] = s["period"].map(windows) if windows is not None else "all"
    s["envelope"] = s.groupby(["period", "phase"])["booked"].transform("sum")
    if mode == "pro_rata":
        key = ["period", "phase"] if per_period else ["window", "phase"]
        dem = s.groupby([*key, "group"])["demand"].transform("sum")
        tot = s.groupby(key)["demand"].transform("sum")
        share = (
            (dem / tot.where(tot > 0))
            .fillna(s["booked"] / s["envelope"].where(s["envelope"] > 0))
            .fillna(0.0)
        )
        s["new"] = share * s["envelope"]
        # Renormalise: groups missing in some periods would otherwise break the envelope.
        tot_new = s.groupby(["period", "phase"])["new"].transform("sum")
        s["new"] = (s["new"] * s["envelope"] / tot_new.where(tot_new > 0)).fillna(s["booked"])
    elif mode == "value":
        prio = priority or {}
        parts = []
        for _, g in s.groupby(["period", "phase"]):
            g = g.assign(p=g["group"].map(prio).fillna(0.0)).sort_values("p", ascending=False)
            left = float(g["envelope"].iloc[0])
            filled = []
            for d in g["demand"]:
                take = min(float(d), left)
                filled.append(take)
                left -= take
            g = g.assign(new=filled)
            if left > 0:
                b = g["booked"].sum()
                g["new"] += left * (g["booked"] / b if b > 0 else 1.0 / len(g))
            parts.append(g)
        s = pd.concat(parts).sort_values(KEYS)
    else:
        raise ValueError("mode is pro_rata or value")
    return plan_of(s.reset_index(drop=True), "new")


# ------------------------------------------------------------------ surrogate
def unit_values(ref: Reference, calendar: pd.DataFrame) -> pd.DataFrame:
    """Per period and phase: value per Sm3 after variable opex and tax, and ``worth``,
    the value of 1 Sm3/d held over the period (× days × discount factor). ``calendar``
    has period and days (and optionally discount_factor)."""
    econ = ref.economics
    cal = _norm(
        calendar[
            ["period", "days", *(["discount_factor"] if "discount_factor" in calendar else [])]
        ].drop_duplicates("period")
    ).sort_values("period")
    if "discount_factor" not in cal:
        cal["discount_factor"] = discount_factors(cal["period"], cal["days"], econ)
    prices = _norm(unit_prices(ref, cal["period"]))
    df = cal.merge(prices, on="period", how="left")
    oil = df["oil"] - econ.opex_per_sm3oe
    gas = df["gas"] - econ.opex_per_sm3oe / econ.gas_sm3_per_sm3oe
    rows = []
    for phase, unit in (("oil", oil), ("gas", gas)):
        v = unit * (1.0 - econ.tax_rate)
        rows.append(
            df[["period", "days", "discount_factor"]].assign(
                phase=phase, unit_value=v, worth=v * df["days"] * df["discount_factor"]
            )
        )
    return pd.concat(rows, ignore_index=True)


def surrogate(
    plan: pd.DataFrame,
    demand: pd.DataFrame,
    *,
    limits: Mapping[str, float] | None = None,
    other: pd.DataFrame | None = None,
    priority: Mapping[str, float] | None = None,
) -> pd.DataFrame:
    """q̂_g(t) = min(d_g(t), B'_g(t)); where Σ q̂ exceeds an FPSO limit (less fixed
    ``other`` demand: period, phase, other_sm3d), groups are cut lowest ``priority``
    first (equal priority: pro rata). Crude by design: no pressure interaction or
    depletion."""
    p = _norm(plan)[PLAN_COLUMNS]
    d = _norm(demand)[[*KEYS, "produced_sm3d"]].rename(columns={"produced_sm3d": "demand"})
    s = d.merge(p, on=KEYS, how="left")
    s["q_hat"] = np.where(
        s["booked_sm3d"].notna(), np.minimum(s["demand"], s["booked_sm3d"]), s["demand"]
    )
    if limits:
        s["limit"] = s["phase"].map(limits)
        if other is not None and not other.empty:
            o = _norm(other)[["period", "phase", "other_sm3d"]]
            s = s.merge(o, on=["period", "phase"], how="left")
            s["limit"] = s["limit"] - s["other_sm3d"].fillna(0.0)
        s["prio"] = s["group"].map(priority or {}).fillna(0.0)
        out = []
        for _, g in s.groupby(["period", "phase"]):
            lim = g["limit"].iloc[0]
            excess = float(g["q_hat"].sum() - lim) if pd.notna(lim) else 0.0
            if excess > 0:
                q = g["q_hat"].to_numpy(dtype=float).copy()
                for level in sorted(g["prio"].unique()):
                    m = (g["prio"] == level).to_numpy()
                    tot = q[m].sum()
                    cut = min(excess, tot)
                    if tot > 0:
                        q[m] *= (tot - cut) / tot
                    excess -= cut
                    if excess <= 0:
                        break
                g = g.assign(q_hat=q)
            out.append(g)
        s = pd.concat(out)
    return s[[*KEYS, "q_hat"]].sort_values(KEYS).reset_index(drop=True)


def surrogate_value(q_hat: pd.DataFrame, worth: pd.DataFrame) -> float:
    v = q_hat.merge(_norm(worth)[["period", "phase", "worth"]], on=["period", "phase"])
    return float((v["q_hat"] * v["worth"]).sum())


def rank_candidates(
    candidates: Mapping[str, pd.DataFrame],
    reference: pd.DataFrame,
    demand: pd.DataFrame,
    worth: pd.DataFrame,
    **surrogate_kw: object,
) -> pd.DataFrame:
    """Surrogate value of each candidate plan and its gain over ``reference`` (S1's
    bookings), best first."""
    base = surrogate_value(surrogate(reference, demand, **surrogate_kw), worth)  # type: ignore[arg-type]
    rows = []
    for name, plan in candidates.items():
        v = surrogate_value(surrogate(plan, demand, **surrogate_kw), worth)  # type: ignore[arg-type]
        moved = _moved(reference, plan)
        rows.append(
            {
                "candidate": name,
                "surrogate_value": v,
                "surrogate_gain": v - base,
                "moved_sm3d_days": moved,
            }
        )
    out = pd.DataFrame(rows).sort_values("surrogate_gain", ascending=False)
    return out.assign(rank=range(1, len(out) + 1)).reset_index(drop=True)


def _moved(old: pd.DataFrame, new: pd.DataFrame) -> float:
    m = _norm(old).merge(_norm(new), on=KEYS, suffixes=("_old", "_new"))
    return float((m["booked_sm3d_new"] - m["booked_sm3d_old"]).abs().sum() / 2)


def check_plan(old: pd.DataFrame, new: pd.DataFrame, *, tol: float = 1e-6) -> list[str]:
    """Problems with a plan: a changed envelope or a negative booking."""
    m = _norm(old).merge(_norm(new), on=KEYS, suffixes=("_old", "_new"))
    env = m.groupby(["period", "phase"])[["booked_sm3d_old", "booked_sm3d_new"]].sum()
    out = []
    diff = (env["booked_sm3d_new"] - env["booked_sm3d_old"]).abs()
    bad = diff[diff > tol * env["booked_sm3d_old"].abs().clip(lower=1.0)]
    if not bad.empty:
        out.append(f"envelope changed in {len(bad)} period/phase(s)")
    if (m["booked_sm3d_new"] < -tol).any():
        out.append("negative booking")
    return out


# ------------------------------------------------------------------ swap book
def swap_book(
    old: pd.DataFrame,
    new: pd.DataFrame,
    split: pd.DataFrame,
    shares: pd.DataFrame,
    worth: pd.DataFrame,
    *,
    gas_sm3_per_sm3oe: float = 1000.0,
) -> pd.DataFrame:
    """Per company and period: booked capacity given up and received, in Sm3 oe and
    value (``worth``), and the net. Groups go to licences by ``split``
    (:func:`alvheim_tiein.ledgers.group_licence_split`), licences to companies by the
    equity valid in the period."""
    m = _norm(old).merge(_norm(new), on=KEYS, suffixes=("_old", "_new"))
    m["change"] = m["booked_sm3d_new"] - m["booked_sm3d_old"]
    m = m[m["change"].abs() > 0].merge(
        _norm(worth)[["period", "phase", "days", "worth"]], on=["period", "phase"], how="left"
    )
    if m.empty:
        return pd.DataFrame(
            columns=[
                "company",
                "period",
                "given_sm3oe",
                "received_sm3oe",
                "given_value",
                "received_value",
                "net_sm3oe",
                "net_value",
            ]
        )
    oe = np.where(m["phase"] == "gas", 1.0 / gas_sm3_per_sm3oe, 1.0)
    m["sm3oe"] = m["change"] * m["days"] * oe
    m["value"] = m["change"] * m["worth"]
    s = split_for_periods(split, m["period"].unique())
    s["period"] = pd.to_datetime(s["period"]).astype("datetime64[ns]")
    lic = m.merge(s, on=["group", "period"])
    lic = lic.merge(shares, on="license")
    active = (lic["valid_from"] <= lic["period"]) & (
        lic["valid_to"].isna() | (lic["valid_to"] > lic["period"])
    )
    lic = lic[active].copy()
    w = lic["share_x"] * lic["share_y"]
    lic["sm3oe"] = lic["sm3oe"] * w
    lic["value"] = lic["value"] * w
    lic["given_sm3oe"] = (-lic["sm3oe"]).clip(lower=0.0)
    lic["received_sm3oe"] = lic["sm3oe"].clip(lower=0.0)
    lic["given_value"] = (-lic["value"]).clip(lower=0.0)
    lic["received_value"] = lic["value"].clip(lower=0.0)
    cols = ["given_sm3oe", "received_sm3oe", "given_value", "received_value"]
    out = lic.groupby(["company", "period"], as_index=False)[cols].sum()
    out["net_sm3oe"] = out["received_sm3oe"] - out["given_sm3oe"]
    out["net_value"] = out["received_value"] - out["given_value"]
    return out


def group_priority(tables: Mapping[str, object], *, alias: str = "Weightings") -> dict[str, float]:
    """Mean weight of each booking group's wells (the ``Booking`` column of the weight
    table): the order in which the surrogate cuts groups when an FPSO limit binds."""
    cols: dict[str, list[object]] = {}
    for t in tables.get("tables") or []:  # type: ignore[union-attr]
        if t["object_alias"] == alias:
            cols[t["table_name"]] = list(t.get("values") or [])
    if not {"Booking", "Weight"} <= set(cols):
        return {}
    df = pd.DataFrame({"group": cols["Booking"], "weight": cols["Weight"]})
    df["weight"] = pd.to_numeric(df["weight"], errors="coerce")
    df = df.dropna()
    df = df[df["group"].astype(str).str.len() > 0]
    return {str(k): float(v) for k, v in df.groupby("group")["weight"].mean().items()}
