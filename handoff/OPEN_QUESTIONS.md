# Open questions – Alvheim Froskelår tie-in and bookings (19 Nov 2026)

One list, in rough order of how much they hold up the study. Each has the context, why it
matters, and where it is tracked. IDs refer to [ISSUES.md](../ISSUES.md) and
[research/22](../research/22-optimisation-schemes-and-projects.md).

1. **A real Froskelår switch in the model.** Should the RESOLVE workflow get an
   `Active_events` row "Froskelår" with Open_FL1/Open_FL2 conditional on it (as for BY1)?
   Today "off" layers WELL_OFF with PI 0.01, abandonment WC 0.01 and zero liquid and gas
   lift on rows 42–43, because the workflow reopens the wells in 2030. It works, but it is
   a workaround that every baseline must copy exactly. (M1, P9)
2. **Date-based lookups.** The workflow reads `Uptime_base` and `Bookings_*` by step index.
   Any grid other than monthly (MH, quarterly) reads the wrong rows unless the cells are
   remapped. Can the workflow look rows up by date instead? (M2)
3. **The Oct 2030 – Apr 2031 oscillation.** Volund shuts with Froskelår choked, or the
   reverse, month to month (±1500 Sm3/d FPSO oil), because `DPControl = CALCULATED` is set
   every step. Hysteresis, or a fixed DPControl for FL1/FL2/Volund in that window? Results
   inside the window are not trusted until this is settled. (M3)
4. **GAP breaking group limits.** The first step of every coarse BASE puts Tyrving oil at
   4141 against 1836 booked; monthly M BASE puts Boyla+Frosk liquid 14 % above its booking
   in three months inside the oscillation window. Is this the optimiser's constraint
   tolerance (`CONSTRAINT_TOL` 0.005, `STOP_ON_TARGET_OR_OPTIMISER_ERROR` 0), and can it
   be tightened? (M4)
5. **The lift-gas result name.** Gas bookings cap total gas, lift gas included, but results
   have formation gas only. 22 candidate property names under `SolverResults[0]` return
   nothing. What is GAP's lift-gas rate called, so it can be tracked and added to
   `EquipmentResults`? (M5, P2)
6. **What the optimiser weights mean.** `Weightings` (NT1 3.0, Volund 2.0, …) applies at
   every step to Dec 2031; `Weightings2025` (Tyrving and Boyla+Frosk 1.5, Volund 0.01) is
   never used, and TI1 has 2.5 without a row in either table. What do the weights
   represent contractually, who set them, and is `Weightings2025` meant to be used? This
   is the "nudge" the soften and total-then-settle schemes change. (M6)
7. **Booking rows.** `Bookings_*` have 24 rows from 30 Jun 2026 22:00 UTC, and the last row
   repeats Aug/Sep 2027. Intended? (M7)
8. **Lending booked capacity.** A booking is an economic entitlement. Can unused capacity
   be lent to another group and recalled, and on what notice? This decides whether the
   lend plan (R1) needs a recall clause or a model block that keeps the owner's priority.
   (research/22 Q2)
9. **Settlement rule.** The gain G of a plan over the reference is split into awards, and
   each licence receives its award minus its own change. Four rules are implemented:
   minimal (losers made whole, winners share the rest pro rata to their gains),
   proportional to booked capacity (decided 18 Nov as the basis), equal, and Shapley
   (needs coalition runs). `tiein optimise report` offers minimal and equal so far. Is
   booked capacity still the rule once Froskelår, which has no booking, joins? And is the
   settlement in money, tariff or capacity? (research/22 Q4)
10. **The canonical baseline.** Today's weights and bookings, or the contracted bookings
    with neutral weights? Every delta depends on it. (research/22 Q5)
11. **Restructuring bookings when Froskelår opens.** If a restructure (lend, pro rata, a
    Froskelår cap) beats today's bookings for every licence, who signs off, and in what
    forum? (research/22 Q3)
12. **An interruptible block.** Can GAP hold a group at a minimum rate? The exact
    interruptible-capacity scheme needs it. (research/22 Q6)
13. **Relative value until prices exist.** Value is Sm3 oil equivalent (gas/1000), pre-tax,
    discounted 8 % to 1 Jan 2027. This weights oil and gas by volume, not price. Is that
    good enough to rank schemes, or should a gas/oil value ratio be agreed? When will a
    price deck and tax treatment be available? (T9)
14. **Downtime in volumes.** Handoff volumes multiply instantaneous rates by days and are
    5–7 % high; GAP's `CumOil` includes uptime. Use `CumOil`-based volumes from here on?
    (A1)
15. **MH accuracy on this model.** The studies search on MH and confirm monthly. e001
    against monthly M BASE will show the error; what error is acceptable for screening?
    (A3)
16. **Licence shares.** The study uses public Sodir shares. Confirm them, or replace them
    with commercial ones, including the split for Froskelår's licence.
17. **The FPSO water limit.** It binds 2028–2034, and that is where tie-back water
    displaces host wells. Is water capacity (or its allocation) in scope as a lever, or
    fixed? (A7)
18. **Presets with schedules.** The presets change stores DataObject table edits. Should
    presets also carry schedule assumptions (WELL_OFF), so the switch is fully one preset
    in the app? (P9)
19. **Where the optimiser lives.** The studies run from the toolkit around Autogration.
    Phase 3 moves the driver into Autogration (leased driver, Optimise tab). Is that
    wanted, and should it wait for the phase 1 results? (research/22 phases)
