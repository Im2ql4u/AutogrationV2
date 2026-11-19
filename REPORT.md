# Alvheim – fixed booking model on TEST: results so far

> **Errata (2026-11-18, Aleksander; details in [ISSUES.md](ISSUES.md)).**
> - **Volumes ignore downtime (A1).** They integrate the solver's instantaneous rate × days, but uptime is 0.54–0.98. GAP's own CumOil gives M BASE 20.655 MSm3 full life (not 22.095) and 3.094 in the booking period (not 3.248). The lift-all gain is +0.188 MSm3 (not +0.194). Relative statements hold.
> - **The single-lift table (quarterly) is distorted (A2).** Every coarse BASE's first step breaks the Tyrving booking (see below). With Tyrving lifted, most of the FPSO gain shows up in host wells, not Tyrving. Monthly single lifts were submitted on 2026-11-18; "almost all from Tyrving" waits for them (A5).
> - **"No gain over full life" is about total volume only (A4).** Lifting bookings moves oil between licences and brings it forward, worth about +61 kSm3 discounted at 8 %. So the settlement question stays, even with a total change of ≈ 0.
> - **Screening grid (A3).** Q overstates the booking gain by about a third. Screen with MH (monthly to Oct 2027, then 6-monthly; check it on this model first) and confirm with monthly.
> - **More constraint violations (M4).** Monthly M BASE also breaks the Boyla+Frosk liquid booking by 14 % in Oct 2030, Dec 2030 and Mar 2031, inside the oscillation window.

Model: `01a1e49f…` "ALV_NM_BC_Oct2026 updated Bookings" (copy of `S:\YGGDRASIL\IPM\User\kridun\ALV_NM_BookingFix_1`).
Detailed tables: [compare.md](runs/compare.md). Raw per-case trajectories: [fixed_compare.json](runs/fixed_compare.json).

## In plain words

- **The booking fix works on the platform.** The oil and water bookings are applied in the right months (Jul 2026–Sep 2027). The gas and liquid bookings now stay active all the way to 2041. In the old model they disappeared after Oct 2027.
- **Removing all tie-in bookings gives about 6 % more Alvheim oil during the booking period.** That is +0.19 MSm3 (≈1.2 million bbl, ≈425 Sm3/d on average) from Jul 2026 to Sep 2027, based on the monthly reference runs.
- **Almost all of that comes from Tyrving.** Lifting only Tyrving's booking gives about +0.16 MSm3 (+5 %). Boyla+Frosk (+0.035), Volund (+0.017) and Vilje+Skogul (+0.010) matter little.
- **Over the full life to 2041 there is no gain: monthly BASE 22.095 vs LIFT 22.089 MSm3 (≈0).** The +0.19 MSm3 in the booking period is oil produced *earlier*, not *extra* oil. The value of lifting bookings is therefore earlier production (timing/NPV), not more reserves. The quarterly grid's full-life figure (+0.26, +1.2 %) overstates this. Treat the per-tie-in full-life Q numbers below as indicative only. Vilje+Skogul alone comes out slightly negative, because it pushes out other production.
- **For screening booking options, quarterly steps (Q) are good enough.** Total oil is within about 1 % of monthly. Q does overstate the gain from lifting bookings by about a third, so the best candidates should be confirmed with monthly runs. Half-year and yearly grids are 2–5 % off and overstate the gain by 50–60 %.

## Booking period (Jul 2026 – Sep 2027), monthly reference

| | BASE | LIFT all | Δ |
|---|---|---|---|
| Alvheim (FPSO) oil, MSm3 | 3.248 | 3.442 | **+0.194 (+6.0 %)** |
| of which Tyrving | | | +0.157 |
| Volund | | | +0.037 |
| Vilje+Skogul | | | +0.024 |
| Boyla+Frosk | | | +0.008 |
| Host wells | | | −0.032 |

Lifting one tie-in's bookings at a time (quarterly grid, vs Q BASE):

| Lifted | Booking period Δ oil | Full life to 2041 Δ oil |
|---|---|---|
| Tyrving | **+0.160 (+5.0 %)** | **+0.266 (+1.2 %)** |
| Boyla+Frosk | +0.035 (+1.1 %) | +0.016 (+0.1 %) |
| Volund | +0.017 (+0.5 %) | −0.010 (to 2036 only; still running) |
| Vilje+Skogul | +0.010 (+0.3 %) | −0.103 (−0.5 %) |
| All four | +0.261 (+8.1 %) | +0.262 (+1.2 %) |

Monthly reference, full life to 2041: BASE 22.095, LIFT all 22.089 MSm3, so Δ ≈ −0.006 (0 %). The early gain is fully given back later. The quarterly full-life column above overstates the gain, so confirm candidates with monthly runs.

## Time step grid: accuracy vs speed (D2ads_v5, the cheapest VM)

| Grid | Steps | Run time | Total oil vs monthly | Booking-period lift gain (monthly = 0.194) |
|---|---|---|---|---|
| Monthly (M, D4) | 174 | ~8–9 h (estimate) | – | 0.194 |
| Quarterly (Q) | 63 | 3.2–3.9 h | −0.7 % / +0.8 % | 0.261 |
| Half-year (H) | 37 | 1.7–2.3 h | +0.2 % / +2.5 % | 0.294 |
| Quarterly→yearly (QY) | 25 | 1.0–1.5 h | +2.4 % / +5.0 % | 0.261 |
| Yearly (Y) | 23 | 0.9–1.7 h | +2.5 % / +3.9 % | 0.313 |

The two "Total oil" figures are for BASE / LIFT, compared through 2033–34, the horizon the monthly runs have reached so far.

- All coarse grids use event-aligned bookings and uptime. Step k reads the booking and uptime values averaged over the months it covers. Without this, the workflow reads the wrong rows: it looks them up by step index, and events force extra steps.
- **Late steps are much slower than in the old model.** On D2, a quarterly step in 2032–33 takes 5–18 min, compared with ~1 min in 2027–28. The likely cause is that the gas and liquid bookings now constrain GAP all the way to 2041.

## Model observation to share with the Alvheim team

Every coarse-grid BASE run's first step (Jul–Aug 2026, a 2-month step) has GAP produce **Tyrving 4141 Sm3/d against a booking of 1836**. That is even more than the run with no bookings (2580), while the host wells drop to 2347. It is deterministic. The monthly run respects the booking (1859 against 1860). It looks like a GAP solve that does not honour the booking in that state. It only affects that one step; the FPSO total is plausible.

## Platform findings (TEST)

1. **Mass failures when many tasks start together.** For each task, the backend copies the full 8.4 GB model, and the VM waits at most 30 min for that copy. 10 of my first 14 tasks failed with "Assumption set … not available within 1800s"; the other session hit the same and similar errors. Submitting ≤2 tasks every 15 min worked with no failures. Possible fixes: reference the parent's archive instead of copying it, throttle the copies, or make the wait scale with the copy.
2. Another task failed with "No OpenServer license available" instead of waiting in the queue.
3. `POST /tasks/{id}/restart` returned 502 for this model size and did not restart the task (the copy appears to run inside the request).
4. `POST /models/{id}/simulate` returned 504 but still created the task, so blind retries can create duplicates.
5. Setup takes only 3–4 min when the platform is quiet. The 12–25 min "OPENFILE" seen in the old benchmark is mostly waiting for the backend copy.

## Notes on the old benchmark (other session, old registration `01a1e43c…`)

- The coarse grids there read misaligned bookings and uptime, because of the step-index lookup described above.
- In the old model, bookings vanish after Oct 2027 (bug 2).
- So those Q/QH/QY/H vs REF accuracy comparisons are not representative. Runs are deterministic, and DEBUG_FLAG does not change speed.

## Pending / how to update

The monthly M BASE and M LIFT runs (~halfway, at 2033) and Q LIFT Volund (at 2036) are still running on TEST. When they finish, run
`python compare.py` in `files\alvtest` to refresh `runs\compare.md` with full-life monthly numbers.
