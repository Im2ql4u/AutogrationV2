# Alvheim: Froskelår tie-in, bookings and optimisation – handoff, 19 Nov 2026

From Aleksander, for Kristoffer and the agents reviewing with him. Read in this order:

1. this file – where things stand and what to review;
2. [OPEN_QUESTIONS.md](OPEN_QUESTIONS.md) – everything still undecided;
3. [WORKLOG.md](WORKLOG.md) – what was done, day by day, with run and PR ids;
4. [ISSUES.md](../ISSUES.md) – the issue log (model M, analysis A, toolkit T, platform P);
5. [research/22](../research/22-optimisation-schemes-and-projects.md) – the design: schemes,
   projects in Autogration (dropped 19 Nov, see below), phases.

Everything runs on **test**, against your fixed model **`01a1e49f-9b62-77a6-b13c-3d3911c90efc`**
("ALV_NM_BC_Oct2026 updated Bookings", copy of `S:\YGGDRASIL\IPM\User\kridun\ALV_NM_BookingFix_1`).
Licence and company figures are kept out of git (`studies/alvheim-tiein/data/`); the documents
here have totals only.

## Where we are

| Phase (research/22) | Content | Status |
|---|---|---|
| 0 – test runs | Check your runs, monthly single lifts, booking-period release, probes | **done** – errata in REPORT.md, compare.md and comparison.md; findings A1–A7, M1–M7 |
| 1 – toolkit | Feasibility checks, levers, `tiein optimise`, ledgers, settlement, booking restructuring, MH grid | **built; studies running** – wave 1 started 19 Nov 09:17 |
| 2 – Autogration PRs | ~~Optional projects~~ (dropped 19 Nov). Now: a Results run picker (pick runs across simulations, deliberate baseline, change baseline and runs in view inside Results), the unit fix, then the booking, settlement and frontier visuals on top of the picker | **in progress** – #1101 closed; picker and unit fix on branches, not yet PRs |
| 3 – Autogration PRs | Optimisation module inside Autogration: server-side study driver (state machines, leased driver, attempts), scheme presets, shared economics, pinned reference sets, an Optimise tab | not started; done when the phase 1 study re-run server-side gives the same answer |
| 4 – model | A real Froskelår switch (M1), date-based lookup (M2), oscillation fix (M3), limit violations (M4) | open – needs RESOLVE/IPM |

## What has happened since your fixed model

- **Your 31 test runs were re-checked.** Volumes in the handoff files ignore downtime and
  are 5–7 % high (A1); the quarterly single lifts are distorted by a first-step Tyrving
  violation (A2); the Q grid overstates the booking gain by about a third (A3). Errata
  are at the top of each file. The relative conclusions hold.
- **Monthly single lifts and a booking-period-only release** (18 Nov). Each lifted group
  gains, but the host wells lose more while the FPSO water limit binds (2028–2034).
  Releasing only Jul 2026 – Sep 2027 beats releasing for good: +164 vs +161 kSm3 oil in
  the booking period, and +62 vs −12 kSm3 over field life (A7).
- **A clean "without Froskelår" baseline** (task `01a1edfd-73d5-76d9-8f5b-d5f7c8533dfc`).
  WELL_OFF alone fails because the workflow reopens FL1/FL2 in 2030, so the baseline also
  sets PI 0.01, abandonment WC 0.01, and zero liquid and gas lift for rows 42–43 (M1).
  FL1/FL2 produce nothing at all 175 steps. Froskelår against this baseline: FL +2.54
  MSm3 oil, the other wells −0.17 MSm3 over life.
- **Probes** of the optimiser weights and lift gas (M5, M6): `Weightings` applies at every
  step to Dec 2031, and `Weightings2025` does not appear to be used. None of 22 candidate
  lift-gas result names returns a value.
- **The toolkit** (`studies/alvheim-tiein`, CLI `tiein`) got optional projects, several
  environments, idempotent submits, a bookings report, booking restructuring, an MH
  (monthly, then half-yearly) grid with remapped cells, and the optimisation driver.
- **Relative value.** There are no commercial inputs yet, so value is in Sm3 oil
  equivalent (oil + gas/1000), pre-tax, discounted at 8 % to 1 Jan 2027. Every comparison
  is relative: each case against the baseline, and each case against its bookings. Money
  comes back by setting `value_basis: price` and adding a price deck (T9).
- **Four optimisation studies started** on 19 Nov (below).

## Changed on 19 Nov afternoon: no projects

- **Projects are dropped.** Autogration already links runs that are submitted together (one
  simulation, one `assumption_group_id`), and your `feature/linked-assumptions` branch
  lets one simulation hold exactly the cases wanted. So AkerBP/autogration#1101 is closed,
  and AkerBP/autogration_frontend#165 will be replaced (below).
- **Results run picker** (`feature/results-run-picker` off `development`, frontend). Filters
  like the Tasks page (asset, registered model, status, created by, time). Simulations
  expand to their runs. Runs are picked with "+", a click, shift-click for a range, a
  simulation's checkbox, or select all. Running or queued runs can be picked only when the
  status filter includes them. One run is marked as the baseline on purpose; Compare
  stays disabled until it is. Inside a comparison, the baseline and the runs in view can be
  changed, and "Edit runs" reopens the picker. #165's booking, settlement and frontier
  visuals move onto this selection afterwards.
- **Unit bug** (P10). GAP writes gas rates as `1000Sm3/d`, but the Results page and the
  results workbench only knew `Sm3/d`, so gas rates were 1000× too low there. The toolkit's
  own reader was right, so the study numbers are not affected. Fixed on
  `fix/results-units` (frontend) and in `results-workbench` (this repo); neither is
  pushed yet.
- **Presets PRs** AkerBP/autogration#1102 and AkerBP/autogration_frontend#166 are back to
  draft. Your linked-assumptions presets store the whole spec, including
  `dataobject_tables`, and both add a migration 0023, so ours are probably superseded.
- **Linked assumptions tested offline on Alvheim** (next section).

## Linked assumptions on Alvheim (`feature/linked-assumptions`, tested offline)

The branch isn't on test yet (`/simulate/preview` returns 404), so its case builder
(`build_compute_set`, `preview_simulation`) was run locally against the fixed model's tree
(`GET /models/01a1e49f…/tree`). The toolkit's new `alvheim_tiein.linked.combine` turns
several single-run requests into one request with one link, `case`, whose options are the
requests. Every item that differs goes on the link, with the options it applies in;
items shared by all go in every case.

| Request set | Cases | Linked items | Result |
|---|---|---|---|
| Project cases (FL off / on / on + lift) | 3 | 12 (2 WELL_OFF schedules, 10 cells) | all 3 identical to the single requests |
| restructure-w1 wave (base, ref, R1, R4, R3 ×2) | 6 | 252 of 279 cells, plus resolve settings and a schedule op | all 6 identical (cell order aside) |
| soften-w1 wave (α, β grid) | 10 | 232 | all 10 identical (cell order aside) |
| Matrix: Froskelår off/on × 5 booking schemes, `exclude_cases` drops off × 4 | 6 of 10 | 2 links | preview lists the right 6; every built case equals its single run |

So a whole optimiser wave, or "Froskelår off/on × schemes", can go in as one linked
simulation, and Results can then compare its cases directly. One limitation was found
(P12): `_conflicts` runs before `exclude_cases` is applied. Two items on different links
that write the same cell are rejected, even when every combination where both apply is
excluded. Example: the R3 schemes cap FL1/FL2's `MaxLiquidRate`, and Froskelår off zeroes
it. The only combinations where both apply are off × R3, and those are excluded, yet the
request is rejected. Workaround: one link with an option per wanted case (what `combine`
does).

## Autogration PRs to review

| PR | Branch → `development` | What | Status |
|---|---|---|---|
| AkerBP/autogration#1101 | `feature/optional-projects` | Optional projects | **closed** 19 Nov: projects dropped |
| AkerBP/autogration_frontend#165 | `feature/results-projects` | Results project mode with booking, settlement and frontier visuals | open, to be replaced by the run picker plus these visuals; Copilot's round-2 comments (3) not fixed |
| AkerBP/autogration#1102 + AkerBP/autogration_frontend#166 | `feature/preset-dataobject-tables` | Presets also store DataObject table edits | **draft**: probably superseded by linked-assumptions presets. #166 has both round-2 Copilot fixes pushed (`2efc4ba`) |
| frontend, not yet a PR | `feature/results-run-picker` | Results run picker (above) | being built |
| frontend, not yet a PR | `fix/results-units` | `1000Sm3/d` and other multiplier units on the Results page (P10) | done locally (`8078e56`, 329 tests); not pushed |
| merged 15 Nov | – | #1076 (archive names with brackets), #1077 (fetch missing files before validation), #1079, frontend #138 (Results section) | merged |

Where an agent should look hardest:

- **Run picker** (once it is a PR): the selection rules (shift-range, a simulation's runs,
  select all only over runs the status filter allows), that the baseline is never
  implicit, and that old `compare~…` links still open. Its logic is in pure, tested
  helpers. There are no DOM tests (Vitest runs without jsdom), so clicks and keyboard
  need a manual look.
- **Unit fix**: `toSi` reads a leading multiplier (`1000`, `1E3`, `e3`, `10^3`) and
  falls back to a case-insensitive match. Since case is ignored, `mW` would read as `MW`.
  No Alvheim unit is affected, but it is a trade-off.

## The Froskelår on/off switch

- **Today (toolkit).** A project's `switch` block holds the WELL_OFF schedules for FL1
  (`RESOLVE.MODULE[0].MOD[0].EQUIP[754]`) and FL2 (`EQUIP[764]`) plus five table changes
  on rows 42–43 (`Wells_data` PI and Abandonment_WC; `Wells_constraints` MaxLiquidRate,
  MinGasInj, MaxGasInj). Every "off" request gets them. Verified on the baseline above.
- **In the app, next.** With linked assumptions this is a link "Froskelår" with options
  off and on: the two WELL_OFF schedules and the ten cells apply in "off". Saved as a
  preset (presets store links on that branch), anyone can switch Froskelår off from the
  simulate page, and any sweep crosses with it. Nothing is saved before the branch is
  on test.
- **In the model, the real fix.** An `Active_events` row "Froskelår" with Open_FL1 and
  Open_FL2 conditional on it (as for BY1), so one switch closes Froskelår without the
  layered workaround. This is a RESOLVE workflow edit in IPM, which can't be run here. As
  contributors on test we can register the edited model ourselves (`tiein register` or
  the app); the edit itself is the open part.

## Optimisation studies (wave 1, project `froskelaar-fixed`, test)

All four search on the MH grid and confirm the best candidates monthly. They share two MH
runs: e001 (base: Froskelår on, today's bookings and weights) and e002 (reference:
Froskelår off). Objective: PV in Sm3 oe, scored against the baseline.

| Study | Scheme | Levers / candidates | Budget (runs) |
|---|---|---|---|
| settle-w1 | total then settle | α (weights → neutral), β (release bookings); candidates: neutral weights, release, both | 8 |
| soften-w1 | soften bookings | α and β on a 3 × 3 grid over the booking period | 14 |
| restructure-w1 | restructure bookings | R1 lend unused capacity, R4 pro rata, R3 cap Froskelår at 50 % or 80 % of its peak | 10 |
| outer-w1 | outer loop | pattern search on α, β and γ (liquid scale 0.8–1.2 per group) | 30, at most 72 h |

At most 6 runs per wave per study, so the whole set stays well under the 40-run cap.
Comparing e001 with your monthly M BASE (`01a1e4fc…`) also tells whether MH is accurate
enough on this model (A3).

**Timing.** MH runs take about 2 h, so the first candidate waves start late morning on
19 Nov. Monthly confirmations take 6–7 h each.

**Status, 19 Nov afternoon.** e001 and e002 are scored: base 22.33 M and reference
(Froskelår off) 20.01 M Sm3 oe. The first candidate waves were still running at the
last check (restructure-w1: 4 of 10 runs; soften-w1: 7 of 14; outer-w1: 7 of 30). Each
study runs one simulation per candidate today. Once linked assumptions are on test, a
wave can go in as one linked simulation (above).

## How to reproduce or follow

From `studies/alvheim-tiein`, with `.env` pointing at test (see the toolkit README):

```powershell
uv run tiein project show --project froskelaar-fixed       # cases, runs, web compare link
uv run tiein optimise status settle-w1 --project froskelaar-fixed
uv run tiein optimise step settle-w1 restructure-w1 soften-w1 outer-w1 --project froskelaar-fixed --watch 900
uv run tiein optimise report settle-w1 --project froskelaar-fixed --rule minimal
uv run tiein bookings --project froskelaar-fixed            # booked vs produced, violations.csv
uv run pytest -q                                            # 231 tests
```

The VS Code tasks **Study: optimise watch (all studies)** and **Study: optimise watch log**
do the same. The toolkit README has a section on optimisation studies.
