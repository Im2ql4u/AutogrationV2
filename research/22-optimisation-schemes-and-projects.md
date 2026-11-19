# Optimisation Schemes and Projects in Autogration: Design for Alvheim

Status: approved for implementation 2026-11-18 (decisions below), after an internal
design review the same day. Builds on [21](21-alvheim-tie-in-study.md) (the study),
[20](20-results-explorer-plan.md) (results explorer) and the guardrails in
[06](06-ml-and-adaptive-studies.md). Issues referred to as M1, A2 and so on are in
[ISSUES.md](../ISSUES.md).

## Decisions (18 Nov 2026)

1. **A booking is an economic entitlement.** A company's oil or gas booking is its
   contracted right to earn from FPSO capacity. Water and liquid bookings are closer to
   platform balancing: they share out the FPSO water limit and are the operator's
   levers, not entitlements. Consequences:
   - booked oil and gas capacity is the settlement basis and what the booking ledger
     counts (scheme 4);
   - water and liquid bookings are balancing levers in schemes 1 and 3. Changing them
     moves no entitlement, but the value it moves between licences is still measured
     and settled;
   - the study asks whether **restructuring or reordering bookings when Froskelår
     opens** can leave every company better off (scheme 4), and Results shows it
     (section Results below).
2. **Transfers between licences are allowed.** They are measured and shown in Results:
   per licence and company, as a company matrix and over time.
3. **Settlement basis: booked capacity** (r_l, defined in scheme 2).
4. **Economics:** pre-tax, 8 %, valuation date 1 Jan 2027, and a flat placeholder deck
   (70 USD/bbl, 0.30 USD/Sm3 gas) until the commercial owner gives one. Every value
   output names its reference-data version, and a placeholder deck is labelled as such.
5. **The Froskelår-off baseline in Kristoffer's tuned model is ours to fix.** The
   layered switch (M1) holds FL1/FL2 at 0 through Mar 2031 so far, past the point where
   zero limits alone failed. It is the FL-off for every study until a model edit adds an
   `Active_events` row.
6. **Build all phases:** phase 1 in the toolkit now, phases 2 and 3 as Autogration PRs to
   `development`.

## What GAP Optimises Today

Per timestep, GAP maximises the weighted oil rate, Σ weightᵢ × oilᵢ. Each well's
weighting is GAP's well `weighting` property, which is 3.0 for NT1 in the registered
model. How GAP uses it in the objective is to be confirmed (M6). The limits it works
within:

- FPSO limits: water 36,018 Sm3/d, total gas 4,300 (4,700 after the gas upgrade) kSm3/d
  and oil 24,802 Sm3/d;
- per tie-back group limits, which are the bookings (`MaxQoil`, `MaxQTotGas`, `MaxQwat`,
  `MaxQliq`);
- per well limits: liquid, drawdown, and gas-lift minimum and maximum.

The RESOLVE workflow rewrites these inputs every step from DataObject tables, and the
weights come from `Weightings` / `Weightings2025` (M6).

So **the "nudge" has two parts**:

- **Hard booking caps.** A group can't exceed its booking, even when the FPSO has room.
- **Weights.** When a shared FPSO limit binds, capacity goes to the wells with the
  highest weighted oil per unit of the limiting phase. The weights are set per booking
  group (Tyrving 3.0, Volund wells 2.0, falling to 0.01 in the 2025 table), not by value.

A booking cap is an upper limit only. It does not protect a group's production when a
shared FPSO limit binds; the weights decide that.

| Fact from the runs | Consequence for design |
|---|---|
| The FPSO water limit binds in 92–100 % of steps in 2028–2034. Oil bookings bind in 0–20 % of months; Volund's water booking in 60 %. | After 2027 the question is **who gets the water capacity**. Weights and liquid bookings decide it, not oil bookings. |
| Oil per Sm3 of water ranges from 0.05 to 1.9 across wells. | Reallocating water capacity can be worth a lot, and also moves value between licences. |
| Lifting all bookings: +188 kSm3 in the booking period, ≈ 0 over life, +61 kSm3 discounted at 8 %. Volumes move between licences. | The value is timing plus redistribution. Objectives are NPV per licence, never total volume alone. |
| The per-step optimiser is myopic: it doesn't value deferral or depletion. | Life-cycle value and fairness need an outer layer around the simulation. |
| Runs are deterministic on one VM size. The response is not smooth: the M3 oscillation is a discontinuity, and M4 steps break group limits (by 14 % in a monthly run). | These are not noise. Runs that break limits are infeasible, not scored. Keep one VM size. Validate the fast grid at several policies, not just two. |

**On "a new optimiser for GAP".** We don't need to replace GAP's per-step optimiser: it
handles the physics and the hard limits. What's missing:

- the right per-step **inputs**: weights and booking policy;
- a **firm plus interruptible** booking rule, if bookings are to be softened without
  taking away the owners' protection (scheme 1c);
- an **outer loop** for life-cycle value and fairness;
- a **settlement** that makes a hub-optimal plan acceptable to every partner.

A per-step optimiser of our own is only needed if soft bookings must be penalised
exceedances (slack with a cost), which GAP's hard limits can't express. Decide after
scheme 1c.

## Gates Before Any Recommendation

The optimiser can only be as good as the model judging it. These gates are hard: no
commercial recommendation is made until they pass.

1. **Clean counterfactual (M1).** The FL-off baseline keeps FL1/FL2 at 0 to 2041.
   Otherwise, the model gets an `Active_events` switch. (18 Nov: 0 at all 57 steps to
   Mar 2031 with the layered switch; the run continues to 2041.)
2. **Feasibility per run (M4).** Every evaluation is checked automatically. A run that
   fails a check is **infeasible**: it is recorded but not scored. The checks:
   - the run completed with every step present;
   - no solver error in the logs;
   - no group more than 2 % above its applied limit at any step (`violations()`), with
     gas checked once lift gas is known (M5).
3. **Fidelity (A3).** MH is compared with monthly at four policies or more: BASE, LIFT,
   neutral weights, booking-period release. MH must agree on which runs are feasible
   and on how the cases rank. Otherwise searches run monthly.
4. **Oscillation (M3).** Either fixed in the model, or Oct 2030 – Apr 2031 is reported
   separately. Gains that come mostly from that window are not trusted.

## Shared Building Blocks

1. **Levers.** A named, bounded parameter mapped to model inputs. Kinds:
   - DataObject cells, with row ranges and period masks;
   - RESOLVE settings;
   - GAP properties, for models without an overriding workflow.

   A lever has a transform from its value θ to cell values, for example:
   - weights w(α) = 1 + α (w₀ − 1);
   - booking release cap(β) = B + β (L − B) per group and window;
   - liquid booking scale γ;
   - per-well `MaxGasInj`;
   - the FL open date (needs M1).
2. **Policy.** A scheme's family of cases, θ → simulate request, always relative to a
   project's baseline request.
3. **Evaluator.**
   - Submits requests and follows them by assumption group.
   - Runs the feasibility checks.
   - Reads results with GAP CumOil-consistent volumes (A1).
   - Rows the workflow reads by step index are remapped for MH (M2) until the model
     reads by date.
4. **Two ledgers.** Both are computed from volumes and pinned reference data (price
   deck, costs, tariffs, effective-dated ownership).
   - **Resource ledger (hub).** Value of the hydrocarbons and costs actually incurred:
     oil and gas revenue, variable opex, lift-gas and water handling, emissions where
     priced. Internal tariffs and transfers are left out, since they cancel. Physical
     optimisation uses this ledger.
   - **Participant ledger.** Cash flows per licence and company: tariffs paid and
     received, ownership, tax approximation, settlement. Fairness and settlement use
     this ledger.
   - **Reconciliation.** Summed over all participants, the participant ledger equals
     the resource ledger. This is checked for every case.
5. **Study record.**
   - Project, baseline, model registration and VM size, reference data version.
   - Every evaluation and attempt: θ, request digest, task ids, fidelity, feasibility,
     objectives.
   - Every proposal with its seed, and the stop reason.
   - Nothing changes silently, and any case can be reproduced from its request.

## Scheme 1: Soften Bookings

Two kinds of cases go under this name. They answer different questions, and only the
second keeps the bookings' protection.

### 1a, 1b. Allocation experiments (no model edit)

These measure **what the current rules cost**. They are not proposals, because they
take away protection the bookings give today.

- **1a Weights.** w(α) = 1 + α (w₀ − 1).
  - α = 1 is today.
  - α = 0 is neutral: GAP maximises plain oil, so water capacity goes to the best oil per
    water.
  - Value weights (wᵢ = resource-ledger unit value of well i's oil) are a screening
    variant. They are not exact: the value of a well also depends on its gas, water and
    lift gas, and on depletion.
  - Neutral or value weights can push a group **below its booking** when a shared limit
    binds. Each owner's shortfall against its booking is reported per period.
- **1b Released caps.** cap(β) = B + β (L − B) per group and window, where L is the FPSO
  limit of that phase.
  - Windows: the booking period (Jul 2026 – Sep 2027, monthly table rows 0–23) and the
    future (`Future_Bookings_*`, `Bookings_future`).
  - `m_lift_booking_period` (running) is β = 1 in the booking period and β = 0 later.

### 1c. Firm plus interruptible capacity (the actual soft booking)

The intended rule, per timestep:

1. Each group may use its booking first (**firm**).
2. Booked capacity a group doesn't use is lent to groups at their cap
   (**interruptible**), in proportion to their unmet demand, never more than they can
   produce.
3. The owner can **recall** it: a lender never ends up below what it produced under the
   firm rule alone.

**Exact form: a model block (needs the model owner).** Two GAP solves per step:

- the firm solve gives each group's rate q⁽¹⁾;
- the second solve adds the borrowed capacity to the recipients' caps and holds each
  lender to at least q⁽¹⁾. That needs group minimum rates, or weights that protect the
  lenders; whether GAP can express either is to be checked.

Parameters come from a DataObject (`Interruptible.Enabled`, `Interruptible.Margin`,
`Interruptible.Phases`), so Autogration can switch it per case. This roughly doubles
solve time.

**Prototype: an outer iteration of full runs (no model edit, approximate).**

- **Firm caps** B_g are never lowered.
- **Recipients** are groups at their cap in iteration k. Each gets a borrowed tranche
  b_g(t), sized from the previous run's spare capacity Σ_h max(0, B_h(t) − q_h(t)) per
  phase.
  - The tranche is limited by demand: no more than the group produced in the
    lift-all run minus B_g.
  - It is shared in proportion to unmet demand.
  - It is damped: b⁽ᵏ⁺¹⁾ = ½ b⁽ᵏ⁾ + ½ b̂.
- **Recall.** If a lender produces less at step t than in iteration 0 (the firm run),
  beyond the tolerance, the next iteration cuts the tranches at t by that shortfall.
- **Stop when:**
  - caps, rates and hub NPV change less than 1 %;
  - a cycle shows (iterate k ≈ k − 2);
  - or four iterations are done. Then the study reports "not converged" with the last
    feasible iterate.
- **Why it is only approximate:** a whole-run iteration also reacts to depletion
  changes, which the per-step rule doesn't see. It is for sizing the value, not for
  operating.

### Alvheim experiment (first study)

| Step | Cases | Fidelity | New runs |
|---|---|---|---|
| 0 Running now | 4 monthly single lifts, booking period only, FL-off baseline, probe | monthly / short | 7 |
| 1 Fidelity gate | MH BASE, LIFT, α = 0, booking-period release; monthly α = 0 (the other monthly ones exist) | MH + monthly | 4 + 1 |
| 2 Allocation grid | α ∈ {1, 0.5, 0} × β ∈ {0, 0.5, 1} plus value weights, minus the points in step 1 | MH | 7 |
| 3 Interruptible prototype | from the firm run, at most 4 iterations | MH | ≤ 4 (sequential) |
| 4 Confirm | the best 2–3 feasible points, paired with M BASE | monthly | 2–3 |

With 5–7 licences free (7 ran at once on 18 Nov), steps 1–3 take about 12–15 h of wall
time. Step 1's monthly run overlaps with step 2, and step 3 is sequential. Step 4 takes
about 7 h.

**Output.** For each case:

- the hub NPV change on the resource ledger;
- each licence's NPV change and its booking shortfall per period;
- a frontier of hub gain against the worst licence change;
- where each extra Sm3 came from (group, well, relieved limit).

## Scheme 2: Optimise the Total, Then Settle

### Step 1: hub plan

Maximise hub value on the resource ledger, over feasible runs only. Bookings remain the
**reference entitlement**, not constraints, unless decision 1 says they are firm. In
that case only scheme 1c policies are candidates.

Candidates come from scheme 1 or scheme 3. Let c* be the chosen plan and r the
reference (today's bookings and weights).

### Step 2: settlement (closed form)

On the participant ledger, Δ_l = V_l(c*) − V_l(r) per licence. The surplus is
G = Σ_l Δ_l. It must equal the resource-ledger change (checked) and be > 0; otherwise
c* is no improvement.

Settlement fixes each licence's **final award** a_l, with a_l ≥ 0 and Σ_l a_l = G. The
transfer licence l receives is t_l = a_l − Δ_l, negative when it pays. Then Σ_l t_l = 0
and every licence ends at Δ_l + t_l = a_l ≥ 0.

Rules for a_l:

| Rule | a_l | Meaning |
|---|---|---|
| Minimal transfer | G · Δ_l⁺ / Σ Δ⁺ | losers made whole; winners keep the rest pro rata to their gains |
| **Proportional (decided)** | G · r_l / Σ r, with r_l the booked capacity below | everyone gains in proportion to their entitlement |
| Equal | G / n | — |
| Shapley-based | G · φ_l⁺ / Σ φ⁺ | only if the players are licences and every coalition was run consistently (below) |

**Booked capacity r_l.** Oil and gas bookings only (decision 1), in Sm3 oe, discounted
like the cash flows:

r_l = Σ_t DF_t · days_t · Σ_g s_{l,g,t} · (B_{g,oil,t} + B_{g,gas,t} / 1000)

- s_{l,g,t} is licence l's part of group g's booking in period t: the licence's share of
  the group's production in the reference case, or an equal split over the group's
  licences when the group produced nothing.
- **The host** (licence 203) holds no booking; it owns the FPSO and gets what bookings
  leave. Its basis is that residual: Σ_t DF_t · days_t · (L_oil,t − Σ_g B_g,oil,t)⁺ plus
  gas likewise (`host_basis: residual`, the default; `none` leaves the host out).
- **Froskelår** has a basis only when a restructure gives it a booking (scheme 4, R3).
- Which bookings count: the case's own. A restructure changes the basis (scheme 4).

**Two settlements, kept apart.**

- **The tie-in** (FL off → FL on, today's bookings): licence 869 pays the tariffs and
  compensates displaced licences (`settlement.settle`). This is the tie-in agreement's
  "who pays whom".
- **A policy or restructure** (FL on, today's rules → FL on, the new ones): the surplus G
  is split by the rules above.
- With both, the 2×2 below shows the interaction separately.

- **Timing.** Transfers have a time profile (who is short when), not only a PV.
  Settlement can be in money, through tariff adjustments, or by capacity swaps in later
  periods.
- **Companies.** Each licence's transfer is spread over its effective-dated equity, per
  period, giving the company matrix (summing to zero). It is checked that **no
  company** ends below zero, not only no licence. Equity differences across licences
  can break that.
- **Tax.** Pre-tax numbers are indicative (decision 4).

### No transfers

Keep the contractual physical constraints unless explicitly waived. Maximise hub value
subject to, for every licence l and company k:

- ΔNPV_l ≥ −ε and ΔNPV_k ≥ −ε (effective-dated ownership);
- a downside limit per period: a cash shortfall against the reference no larger than
  agreed.

That is scheme 3 with constraints. The **price of no transfers**, V(c*) − V(c*₍no
transfer₎), is reported on its own.

### Attribution: which booking flexibility creates the gain (Shapley)

- **Players.** The 4 booking groups.
- **Value of a coalition.** v(S) is the resource-ledger change when the groups in S have
  their bookings released, with everything else at reference.
- **Runs.** All 16 coalitions on **one** grid, VM size, model registration and reference
  data.
  - Monthly: 6 exist or are running (∅, all, 4 singles), and 10 more take about two
    waves of 7 h.
  - Or all 16 at MH once it passes the fidelity gate.
- **What the result means.** Σ φ_g = v(all), the gain from releasing bookings. It
  attributes that gain to booking flexibility. It is not an allocation of an optimum
  that also changes weights or other levers.
- **Groups are not licences.** They span licences, so mapping φ to licences needs an
  agreed rule within each group. φ can be negative, so it is not used directly as a
  make-whole award.

### Froskelår and a policy change together: the 2×2

Run FL off and on, each under the reference policy and the new policy. Per licence,
report:

- the FL effect under each policy;
- the policy effect with FL off and with FL on;
- the **interaction** I = v(on, new) − v(on, ref) − v(off, new) + v(off, ref).

Any sequential settlement (FL first, then policy) gives the whole of I to whichever
comes second. So I is shown separately, or split by averaging both orders. Who pays for
the tie-in follows from the participant cash flows and the tie-in agreement; it is not
assumed. Licence 869 bears the cost of displacement but may share the host's tariff
gains.

## Scheme 3: Outer Optimiser Around Autogration

### Problem

Maximise hub value J(θ) on the resource ledger over a box Θ, over feasible runs only.
Optionally, add the scheme 2 no-transfer constraints. Each evaluation is one full
RESOLVE run.

The first Alvheim lever set (d = 6 with FL off, 8 with FL on):

- α (weights);
- 4 × β_g (booking-period release per group);
- γ (future liquid booking scale);
- with FL on: FL1/FL2 `MaxLiquidRate`.

### Algorithm

The response has discontinuities (M3) and infeasible regions (M4), and the budget is
tens of runs. A Gaussian-process surrogate in 6–8 dimensions isn't identifiable from
that. So the search goes in three stages:

1. **Screening.** A definitive screening design, 2d + 1 runs (13 or 17) at MH. It
   estimates main effects and curvature per lever. Keep the 2–3 levers that matter; fix
   the rest at their best screened value.
2. **Local search** on the active levers: a pattern search in the MADS style.
   - Each poll is 2k points (4–6), one licence wave.
   - The mesh shrinks after an unsuccessful poll and grows after a successful one.
   - Infeasible runs are observations with a barrier: they are never chosen, and they
     steer the search away.
   - The run is deterministic with a seed; it needs no numpy or scipy.
3. **Confirmation.** The best 1–3 feasible points run monthly, paired with M BASE on the
   same VM size.
   - Exact repeats of two points measure run-to-run variation (expected zero on one VM
     size).
   - Grid sensitivity comes from the fidelity gate, not from neighbouring points.

A surrogate (GP or BO) becomes worthwhile once a model has a few hundred feasible
evaluations across studies. That is later.

- **Stop rules.** Whichever comes first:
  - the mesh is below its minimum size;
  - the budget is used up;
  - two polls in a row bring no improvement above the confirmation threshold;
  - the wall-clock limit;
  - the user cancels.

  The stop reason is recorded.
- **Budget ledger for Alvheim.** MH ≈ 2.1 h and monthly ≈ 7 h on D4, so a monthly run
  is ≈ 3.3 MH-equivalents.

  | | d = 6 (FL off) | d = 8 (FL on) |
  |---|---|---|
  | Screening | 13 | 17 |
  | Local search (3 levers, 3 polls) | 18 | 18 |
  | Failed and retried attempts (≈ 10 %) | 3 | 4 |
  | Interruptible iterations (if included) | ≤ 4 | ≤ 4 |
  | Confirmation, 3 monthly | ≈ 10 MH-eq | ≈ 10 MH-eq |
  | **Total** | **≈ 44–48 MH-eq** | **≈ 49–53 MH-eq** |
  | Wall time at 5–7 licences | 6–7 waves ≈ 13–15 h search + 7 h (interruptible in parallel) | 7–8 waves ≈ 15–17 h search + 7 h |
  | D4 VM-hours | ≈ 92–101 | ≈ 103–111 |

  - Observations already on the same grid and VM size are reused (scheme 1 MH grid),
    not re-run.
  - Peak concurrent VMs equal the free licences (5–7), far below the 40–50 limit. The
    VM-hours above are the cost.
- **Guardrails** ([06](06-ml-and-adaptive-studies.md)):
  - the model registration, baseline and reference data version are pinned per study;
  - levers are bounded;
  - proposals are logged with their seed;
  - only full-physics runs are reported;
  - a human approves before a recommendation leaves the study.

## Scheme 4: Restructure Bookings When Froskelår Opens

**Question.** When Froskelår comes on stream, can the bookings be restructured or
reordered (who holds which FPSO capacity, and when) so that:

- every company ends at least as well off as before the tie-in;
- and the hub is better off than with the tie-in under today's bookings?

### How bookings act in the model

- A booking is an **upper cap** on its group's rates per phase and period. It reserves
  nothing.
- Capacity a group leaves unused is open to the unbooked wells: the host's (licence 203)
  and, with Froskelår on, FL1/FL2 (869), which have no booking.
- When an FPSO limit binds, the weights decide (M6).
- So Froskelår takes its capacity first from the host's residual and from unused
  bookings, and then, through the FPSO limits, from the wells the weights rank lowest.
  That is a hypothesis; the reference runs below test it.

### Reference runs

All monthly, D4, registration 01a1e49f.

| | Froskelår | Bookings | Run |
|---|---|---|---|
| S0 | off | today's | `froskelaar-fixed` baseline (layered switch) |
| S1 | on | today's | M BASE |
| S2 | on | lifted | M LIFT: each group's demand with no booking cap, an upper bound on what a restructure can give it |

### Restructuring families

Each family is a lever that writes DataObject cells. Water and liquid stay as in the
reference unless a case also uses the balancing levers of schemes 1 and 3; their value
effects are in the ledgers either way.

- **R1 Use it or lend it.**
  - Per period and phase (oil, gas), the capacity a group left unused in S1,
    u_g(t) = (B_g(t) − q_g(t))⁺, is re-booked to groups at their cap in S1.
  - It goes pro rata to their unmet demand (q_g^S2(t) − B_g(t))⁺, never more than that
    demand. A share λ ∈ [0, 1] of the unused capacity is lent (λ = 1 by default).
  - The envelope (total booked per period) is unchanged, and no lender's booking falls
    below what it used in S1.
  - The lender keeps a recall right in the contract. In the model, it is protected only
    as far as the weights protect it, which the run checks.
- **R2 Reorder: capacity swaps over time.**
  - Groups g and h swap capacity between periods: g gives Δ in t′ (where it has slack)
    and gets Δ′ in t (where it is capped); h does the reverse.
  - Each period's envelope is unchanged.
  - A swap is **value-neutral** when both sides' booked value balances:
    Δ′ · v_t · DF_t = Δ · v_t′ · DF_t′, with v the unit value of the phase.
  - Candidates are built greedily from S1 and S2 by surrogate gain (below); the best few
    are simulated.
- **R3 Froskelår booking.**
  - A cap on FL1/FL2 liquid (`Wells_constraints.MaxLiquidRate` rows 42, 43, the only
    FL-specific data lever), set to a fraction φ of their S2 rate.
  - It is constant over time without a model edit.
  - It protects the host and the groups from displacement at the cost of Froskelår
    rate, and gives 869 a settlement basis.
- **R4 Clean-sheet re-split.**
  - Per window (the booking period, then the future), the envelope is re-split across
    the groups pro rata to S2 demand, or greedily by unit value.
  - It is not Pareto on its own. With the settlement it is "total then settle" for
    bookings.

### Surrogate screening (no runs)

Before simulation, candidates are ranked by a per-group surrogate:

- q̂_g(t) = min(d_g(t), B′_g(t)), with demand d from S2;
- when Σ q̂ exceeds an FPSO limit, groups are scaled down in order of weight × unit
  value (the lowest first);
- unit values come from the resource ledger.

It is crude by design (no pressure interaction or depletion). It only picks 3–6
candidates per wave and never reports value. Its ranking error against the runs is
reported per wave.

### Evaluation of a candidate R

Each candidate is simulated with Froskelår on, on the same grid and VM size. Reported:

- **Physical:** produced minus booked per group and company under R's bookings;
  violations.
- **Booking ledger ("swap book"):** per company and period, the booked capacity given up
  and received (Sm3 oe and value), and the net.
- **Value** on the participant ledger per company: V_k(R) against S0 (before the tie-in)
  and S1 (the tie-in under today's bookings).
- **Everyone better off, in kind:**
  min_k (V_k(R) + T_k − V_k(S0)) ≥ 0, where T_k is the company's tie-in settlement
  (tariffs and compensation) and there is no other money. Bookings then replace cash.
- **Everyone better off, with money:** G_R = V(R) − V(S1) > 0, split by the proportional
  rule on R's booked capacity.
- **Frontier:** hub gain against the worst company change, with the Pareto set marked.

### Search

| Wave | Cases | Runs |
|---|---|---|
| 1 | R1 (λ = 1), R3 (φ = 0.5, 0.8), R4 pro rata | 4 |
| 2 | R2 swaps built from wave 1 (2–3), R1 + R3 combined | 3–4 |
| 3 | scheme 3 over λ, φ and the R4 blend, with the no-loss constraints | 10–20 |
| Confirm | the best 1–2, monthly | 1–2 |

Waves 1–3 run at MH if the fidelity gate passes, otherwise monthly.

## Results: Project Page and Visuals

The Results section in project mode shows the baseline and its cases. Value visuals
need reference data (ownership, prices, booking groups). Without it, the page shows the
physical visuals in Sm3.

1. **Booking map.**
   - A heatmap of booking group (rows) × month (columns), with small multiples per
     phase.
   - Baseline: the colour is utilisation (produced / booked), so it shows where bookings
     bind and where capacity lies idle.
   - A case: the change in booking as a diverging colour.
   - Hover: produced, booked and the difference.
2. **Produced minus booked per company.**
   - Diverging bars per company, with its groups under it, baseline and each case side
     by side, over a chosen window.
   - A line over time.
   - This is the plot asked for in the project brief.
3. **Capacity flows.**
   - A Sankey from lending to receiving groups and companies, in Sm3 oe or value.
   - For R2 swaps: a two-sided ribbon per period.
4. **Everyone better off?**
   - One dumbbell per company: value at S0 (before the tie-in), S1 (the tie-in, today's
     bookings), the case, and the case after settlement.
   - Green when at or above S0, red below. The hub total is on top.
5. **Frontier.** All cases as hub gain (x) against the worst company change (y), the
   Pareto set joined, the baseline at the origin. Clicking a point opens the case.
6. **Value waterfall.** From the S0 hub value: plus Froskelår, minus displacement per
   licence, plus the restructure gain, then the settlement transfers (zero sum) per
   company.
7. **Transfers.**
   - A company × company matrix: a chord diagram, with a table beside it.
   - Transfers over time: stacked bars per year, payments below zero and receipts above.
   - The settlement rule selector: minimal, proportional, equal, Shapley.
8. **Feasibility badges** on every case: complete, solver errors, violations over 2 %,
   inside the M3 window.

Data:

- the results parquet of each run;
- bookings from the tracked applied limits, or the DataObject tables;
- reference data.

In phase 2 the reference data is the Results reference upload, extended with licence
shares, prices and booking groups. In phase 3 the backend serves pinned reference sets.

## Optional Projects in Autogration

They are needed by all three schemes, and on their own by Results. Each Autogration
environment is its own deployment and database, so a project belongs to one
environment by construction.

### Data model

Migration 0023:

- **`projects`.**
  - Columns: id (uuidv7), asset, name, type, model_task_id (pins the registration),
    description, owner, created_at, archived_at.
  - Types:
    - `case_comparison` and `scenario_comparison` need every member on the pinned
      model;
    - `model_comparison` allows members on other registrations;
    - `optimisation`.
- **`project_members`.**
  - Columns: project_id, assumption_group_id, task_id (null for the whole group),
    label, role (`baseline`, `case`, `probe`), note, added_by, added_at.
  - Unique (project_id, label) and unique (project_id, assumption_group_id, task_id).
  - **Exactly one baseline:** a partial unique index on (project_id) where role =
    'baseline'.
  - VM size and grid come from the task, and compare flags members that differ (P7).
- **`project_roles`.** project_id, user, role (owner, editor, viewer).

### Access

- A project is visible to its role holders. **Every read** filters members to runs the
  reader may read on the asset, not only when a run is attached.
- Editors attach and detach runs and set the baseline; owners manage roles.

### API

- `POST/GET/PATCH /projects`, `GET /projects?asset=`.
- `POST /projects/{id}/members` attaches runs; `DELETE` detaches them.
- `StartSimulationRequest` gets optional `project_id` and `case_label`. A submit then
  attaches its group in the same transaction.
- `GET /projects/{id}/summary`: per member its status, VM size, grid, feasibility flags,
  and **what differs from the baseline**, a diff of assumption sets (changed cells
  grouped by table and row ranges, settings, schedule records). This replaces "case N"
  with meaning.

Contract (JSON; ids are uuidv7 strings, times ISO 8601):

```text
Project  {id, asset, name, type, model_task_id|null, description, owner, created_at,
          archived_at|null, my_role: owner|editor|viewer}
Member   {id, project_id, assumption_group_id, task_id|null, label, role: baseline|case|probe,
          note, added_by, added_at}

POST   /projects                         {asset, name, type, model_task_id?, description?} -> Project
GET    /projects?asset=&include_archived= -> {items: Project[]}
GET    /projects/{id}                    -> Project & {members: Member[], roles: [{user, role}]}
PATCH  /projects/{id}                    {name?, description?, archived?: bool} -> Project
POST   /projects/{id}/members            {assumption_group_id, task_id?, label, role, note?} -> Member
PATCH  /projects/{id}/members/{member}   {label?, role?, note?} -> Member  (role=baseline demotes the old one)
DELETE /projects/{id}/members/{member}   -> 204
PUT    /projects/{id}/roles/{user}       {role} -> {user, role};  DELETE -> 204
GET    /projects/{id}/summary            -> {project, baseline_member_id,
          members: [{member, tasks: [{task_id, status, vm_size, case_number, name}],
                     flags: {vm_size_differs, model_differs, unreadable_tasks: int},
                     diff: {dataobject_tables: [{object_alias, table_name, rows, baseline, case}],
                            resolve_settings: [...], module_settings: [...],
                            assumptions: [...], schedule_ops: [...]}}]}
POST   /models/{model_id}/simulate       + {project_id?, case_label?, case_role?: case|probe|baseline}
```

`rows` in a diff is a compact range string ("0-23,30") for consecutive cells that change
the same way, with a value summary (`baseline`/`case` as a single value or min–max).

### Frontend

- A Projects page per asset.
- The project page: a baseline chip, a members table (label, role, status, diff summary,
  VM size, flags), "add runs" from the runs list, set baseline.
- Results compare takes `project=<id>` and persists the baseline.
- StartSimulationModal gets an optional project and case label.

### Rules

Projects stay **optional**: runs outside projects work as today. A run can belong to
several projects.

## Optimisation Module in Autogration

### State machine and tables

`backend/modules/optimisation/` (migrations 0024–0026).

- **`optimisation_studies`.**
  - Columns: id, project_id, scheme (`soften_bookings`, `total_then_settle`, `outer`,
    `restructure_bookings`), spec jsonb (levers, policy, objective, constraints,
    algorithm, budget, fidelity, VM size, pinned model and reference set), state,
    stop_reason, owner, lease_until, lease_holder, timestamps.
  - State: draft → running → confirming → done, cancelled or failed.
- **`optimisation_evaluations`.**
  - Columns: id, study_id, wave, θ jsonb, fidelity, state, feasibility jsonb, objectives
    jsonb, timestamps.
  - State: proposed → submitting → submitted → completed or failed → scored or
    infeasible.
- **`optimisation_attempts`.**
  - Columns: id, evaluation_id, attempt number, idempotency key, assumption_group_id,
    status, error, VM-hours.
- **`optimisation_log`.** Append-only proposals, decisions and state changes.
- **`reference_sets`.**
  - Columns: asset, kind (ownership, prices, costs, tariffs), version, payload jsonb,
    valid_from, created_by, readers.
  - Commercial data: readable by named readers only.

### Driver

`optimisation_driver` in `BACKGROUND_WORK`. It claims studies with a row **lease** and a
heartbeat, so one stuck or slow study never blocks the others.

**Per study, per tick:**

1. **Sync** attempts from tasks.
2. **Score** completed ones in a worker with a timeout: feasibility checks first, then
   both ledgers from the results parquet with the pinned reference set.
3. **Propose and submit** when the budget and slots allow:
   - Proposals and attempts are written in one transaction before submitting (an
     outbox).
   - The submit uses the attempt's idempotency key. After a crash, the outbox is
     replayed with the same key, so the platform returns the same group instead of
     starting new runs.

**Attempts and keys:**

- Key `opt:{study}:{evaluation}:{attempt}`.
- Transport retries reuse the key.
- A **new attempt** gets a new key. Only infrastructure failures (no licence, VM lost)
  get one, at most once.
- Model failures are infeasible results, not retried.
- Every attempt counts against the budget in VM-hours.

**Slots.** Before a wave, the driver counts all unfinished tasks on the deployment,
manual ones included. It takes at most the study's concurrency (default 5) and stays
within `max_vms` and the free licences. Manual runs are never blocked; the driver yields
to them.

**Cancel.** Proposing stops, queued tasks are cancelled where the platform supports it,
and running tasks finish. They are recorded, but not scored unless the user asks.

**Algorithms** are pure functions (history, spec, seed) → θ list, so they are
reproducible and unit-testable. The submit body of `start_simulation` becomes a service
function used by both the route and the driver.

### Identity and audit

- Each run records `requested_by` (the study owner) and `executed_by` (the
  optimisation service principal).
- Before every wave, the driver checks that the owner still has contributor rights on
  the asset and read access to the pinned reference set. If not, the study pauses.
- Evaluations, objectives, logs and settlement endpoints are filtered like the
  reference set: users without access see the physical results only (rates and
  volumes), not values.

### Schemes as presets

Each scheme is a spec template:

- `soften_bookings`: the allocation grid plus the interruptible prototype (or the model
  block once it exists);
- `total_then_settle`: hub-plan candidates, a settlement report with rule selector,
  optional Shapley coalitions and the 2×2;
- `outer`: screening, then pattern search, then confirmation;
- `restructure_bookings`: the scheme 4 waves (R1–R4 candidates from the reference runs,
  surrogate ranking, then scheme 3 over their parameters with no-loss constraints), with
  the booking ledger and both "everyone better off" checks.

### Economics

The toolkit's `economics` and `settlement` are ported to the optimisation module
(`backend/modules/optimisation/economics.py`, polars), with the two ledgers and the
reconciliation check. They stay out of `shared/`: a change there redeploys the node
client on merge, and only the backend needs them.

### API

- `POST /projects/{id}/optimisations` (the spec is checked against the model like
  simulate, with a run, wall-time and VM-hour estimate);
- `GET /optimisations/{id}`;
- `POST /optimisations/{id}/cancel`;
- `POST /optimisations/{id}/confirm`;
- `GET /optimisations/{id}/settlement?evaluation=…&rule=…`.

The MCP manifest and API skill docs are regenerated.

### Frontend: the project's Optimise tab

A wizard:

1. scheme;
2. levers (preset, bounds editable);
3. objective and reference set;
4. constraints;
5. budget and fidelity, with the estimate;
6. review.

A live view:

- evaluations with feasibility;
- objective by wave;
- the frontier;
- the best θ, with "confirm monthly";
- settlement: licence Δ, awards, transfers over time, company matrix, rule selector.

## Phases

| Phase | Where | Content | Done when |
|---|---|---|---|
| 0 | test runs | Gates 1–2 checked on the running runs; monthly single lifts; booking-period release; probe (M5, M6) | runs complete; ISSUES.md updated |
| 1 | toolkit | Feasibility checks per run; lever transforms; `tiein optimise` (grid, screening, pattern search, interruptible prototype); both ledgers and the closed-form settlement; booking restructuring (scheme 4); notebook 04 (frontier, settlement, Shapley, 2×2, booking map, swap book); MH remap | the Alvheim study steps 1–4 and scheme 4 waves 1–2 done; frontier and settlement ready for review |
| 2 | Autogration PRs | Optional projects: tables, roles, API, submit-time attach, diff summary, Results project page with the visuals above | merged to test; Alvheim projects attached |
| 3 | Autogration PRs | Optimisation module: state machines, leased driver, attempts, presets, shared economics, reference sets with readers, Optimise tab | the phase 1 Alvheim study re-run server-side gives the same result |
| 4 | model owner | M1 switch, date-based lookup (M2), oscillation fix (M3), violations (M4), interruptible block | a new registration passes the gates; fidelity re-validated |

**Tests:**

- **Phase 1.** Lever transforms. Settlement identities: Σ t = 0, every a_l ≥ 0, the two
  ledgers reconcile. Pattern-search determinism under a seed. Convergence and cycle
  detection on synthetic responses.
- **Phase 2.** API, repository and permission tests as in `tests/backend` (exactly one
  baseline; members filtered by read access), plus vitest for the project page.
- **Phase 3.** The driver against a fake task store: crash between outbox and submit,
  a replay with the same key, a retry with a new key, budget and stop rules, a lease
  takeover, and cancel. Then an end-to-end on dev with a small model.

## Risks

- **The model judges every plan.** The gates come first. Results inside the oscillation
  window, or from runs that break limits, are not trusted.
- **Weights may encode something contractual (M6).** Changing them may not be ours to
  decide. Allocation experiments are analysis, not proposals.
- **Softening can be mis-sold.** Only scheme 1c keeps the owners' protection. Every
  report shows each owner's booking shortfall next to the hub gain.
- **Myopic inner, life-cycle outer.** Per-step weights can't express deferral. Only the
  outer loop and NPV objectives value timing.
- **Throughput.** 5–7 licences and 2–7 h runs limit a study to tens of evaluations. Keep
  the active levers to 2–3 and reuse runs across schemes.
- **Confidentiality.** Reference data, licence values and settlements are behind roles.
  The repo keeps totals only.

## Open Questions

1. What do the `Weightings` tables represent contractually, and who set them?
2. A booking is an economic entitlement (decided). Can it be lent and recalled, and on
   what notice? This decides whether R1 needs a recall clause or a model block (1c).
3. Who signs off a hub-optimal plan or a restructure, and in what forum?
4. Settle in money, tariff or capacity? Scheme 4 tests capacity (in kind); the basis for
   money is booked capacity (decided).
5. Which baseline is canonical: today's weights and bookings, or the contracted
   bookings with neutral weights?
6. Can GAP hold a group at a minimum rate (needed for the exact interruptible block)?
