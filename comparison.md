# Alvheim ALV_NM_BC_Oct2026: fast-run calibration (TEST env)

> **Errata (2026-11-18; see [ISSUES.md](ISSUES.md), A3).** These runs are not among the runs on the fixed model `01a1e49f…`. That model's REF is monthly on D4, not D8, and its booking-period gain is +188 kSm3 by CumOil, not +89. So this calibration is probably from another registration (an earlier one, or the old model whose bookings stopped after Oct 2027). The grid mechanics below (remap, oscillation, VM size) still hold. The accuracy numbers and the MH recommendation need one MH BASE/LIFT pair on `01a1e49f…` before use.

Scenario pair: BASE vs LIFT (all bookings = 99999). Truth: monthly REF, 174 steps, Jul 2026 to Jan 2041.
Accuracy below is FPSO oil (uptime-weighted cumulative) vs REF. Gain = LIFT - BASE.

## Result

| grid | VM | steps | solve time | BASE cum error (Oct27 / 2030 / 2035 / 2041) | gain kSm3 (Oct27 / 2030 / 2035 / 2041) |
|---|---|---|---|---|---|
| **REF** monthly | D8 | 174 | 5.3 h | 0 / 0 / 0 / 0 | **+89 / +54 / +34 / +15** |
| **MH** monthly to Oct 2027, then 6 months | D4 | 45 | **1.7 h** | -0.2 / +2.4 / +1.8 / +1.1 % | +96 / +52 / +49 / -1 |
| MY monthly to Oct 2027, then 12 months | D4 | 32 | 1.2 h | -0.2 / +4.9 / +4.3 / +2.0 % | +96 / +53 / -148 / -198 |
| QY 3 months to Oct 2027, then 12 months | D4 | 25 | 1.0 h | +3.3 / +5.1 / +4.7 / +2.7 % | +33 / +22 / -12 / -215 |
| Y 12 months | D4 | 23 | 0.7 to 1.4 h | +4.4 / +6.1 / +5.2 / +2.6 % | +67 / +69 / -202 / -43 |

Add about 3 to 7 min of setup per run when the env is quiet. Under load this rises to 25 to 30 min (see platform notes).

**Recommendation for development and comparison: MH, DEBUG_FLAG=0, D4.**
- About 2 h per case on a VM at half the D8 price. That is roughly 1/6 to 1/7 of the REF compute cost.
- Cumulative oil is within 2.5 %.
- The gain is within about ±15 kSm3 of REF over the whole horizon. REF itself wobbles about ±45 kSm3 month to month.
- For a quick look at the booking effect only, MY, or a monthly run stopped at Jan 2030, is exact to 2030.

## Why these grids

- The booking effect lives in Jul 2026 to Oct 2027 (REF gain peaks at +89 kSm3, then gives back to +15 kSm3 by 2041 through earlier depletion).
  - Coarse steps in that window average the booking caps and dilute them: QY gain is +33 vs +89.
  - So that window must stay monthly. It is cheap: about 30 min of solve time.
- The expensive part is 2030 to 2034, at up to 250 s per monthly step. Coarse steps there save most of the time.
- Coarse tails must not be too coarse. The model has a period-2 optimiser oscillation in Oct 2030 to Apr 2031:
  - Volund shut in with FL1/FL2 DPC set to 0, or Volund open with FL wells choked. FPSO oil swings ±1500 Sm3/d month to month.
  - Monthly steps average it out. A 12-month step holds one phase for a year, which gives up to ±550 kSm3 of gain error (MY, Y). A 6-month step keeps it near the noise level.
- Cause: the RESOLVE workflow step "dp Control Mode" sets `GAP.MOD[{PROD}].WELL[{w}].DPControl = "CALCULATED"`, so GAP re-optimises the chokes at every step and the solution flips. This can't be turned off through the API.
  - Fixing it in a model copy, for example with hysteresis or fixed DPControl for FL1/FL2/Volund in that period, would likely make 12-month tails usable (about 1.2 h runs). It might also speed up the solver.

## Mechanics the remap relies on

- RESOLVE forces a step at each workflow well-opening date and restarts the fixed step from there. Confirmed dates: 2026-09/10, 2027-05/06/07, 2028-08/10, 2029-01/02/04, 2030-01. `stepseq.py` predicts every observed step sequence.
- The workflow reads `Uptime_base.Uptime[k]` and `Bookings_*[k]` by step index, not by date. Coarse grids must remap those rows to step averages over each step's span (`stepseq.remap_cells`). Otherwise the uptime and bookings land on the wrong dates.
- DEBUG_FLAG=0 gives bit-identical results and about 10 % less solve time.
- VM size: D4 runs about 1.1x D8 time at half the price. D2 runs about 2x D8 time at a quarter of the price.
  - D4 results differ slightly from D8 and D2 (Apr 2027 BASE 6409 vs 6596 Sm3/d; about 0.2 % cumulative). D8 and D2 agree with each other, so this is optimiser sensitivity to CPU type.
  - **Compare scenarios only on the same VM size.**

## Platform notes (TEST env)

- **OpenServer licences, not VMs, cap parallelism.** About 5 concurrent sessions were available. Extra tasks wait 17 min, then fail with "No OpenServer license available". In practice, submit 3 to 5 cases at a time.
- **Per-task archive copy.** For every task the backend copies all 8.4 GB of the parent model into the task's archive (`prepare_tasks/petex.py`, `_archive_petex_task_files`). The VM waits for that before it starts.
  - Quiet env: 3 to 7 min. 12 to 24 tasks at once: more than 30 min, so tasks fail with "Assumption set ... not available within 1800s".
  - The copies keep running after a cancel.
  - The archive mount also throws `[Errno 22]` partial reads under load, which fall back to Nasuni.
  - Referencing the parent's files instead of copying them would remove most of the setup time and the concurrency failures.

## Files (this folder)
- `build_wave2.py`: case builder. GRIDS include MH, MY, MQ and others. Use `--submit --only A,B --tag X`.
- `stepseq.py`: step-sequence model and event-aware remap.
- `analyze.py`, `final_table.py`: comparison tools.
- `status.py`, `health.py`, `timing.py`: monitoring.
- `groups.json`: assumption-group ids. `runs/`: step results, timings and REF well extracts (`wells_*.json`).
