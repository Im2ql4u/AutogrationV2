# Alvheim: Froskelår tie-in, bookings and optimisation – handoff, 19 Nov 2026

From Aleksander, for Kristoffer and the agents reviewing with him. Read in this order:

1. this file – where things stand and what to review;
2. [OPEN_QUESTIONS.md](OPEN_QUESTIONS.md) – everything still undecided;
3. [WORKLOG.md](WORKLOG.md) – what was done, day by day, with run and PR ids;
4. [ISSUES.md](../ISSUES.md) – the issue log (model M, analysis A, toolkit T, platform P);
5. [research/22](../research/22-optimisation-schemes-and-projects.md) – the design: schemes,
   projects in Autogration, phases.

Everything runs on **test**, against your fixed model **`01a1e49f-9b62-77a6-b13c-3d3911c90efc`**
("ALV_NM_BC_Oct2026 updated Bookings", copy of `S:\YGGDRASIL\IPM\User\kridun\ALV_NM_BookingFix_1`).
Licence and company figures are kept out of git (`studies/alvheim-tiein/data/`); the documents
here have totals only.

## Where we are

| Phase (research/22) | Content | Status |
|---|---|---|
| 0 – test runs | Check your runs, monthly single lifts, booking-period release, probes | **done** – errata in REPORT.md, compare.md and comparison.md; findings A1–A7, M1–M7 |
| 1 – toolkit | Feasibility checks, levers, `tiein optimise`, ledgers, settlement, booking restructuring, MH grid | **built; studies running** – wave 1 started 19 Nov 09:17 |
| 2 – Autogration PRs | Optional projects, Results project page with booking, settlement and frontier visuals | **in review** – #1101 and #165 ready |
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

## Autogration PRs to review

| PR | Branch → `development` | What | Status |
|---|---|---|---|
| AkerBP/autogration#1101 | `feature/optional-projects` | Optional projects: tables and migration 0023, roles, API, attach at submit, diff summary, idempotent attach | ready; 6 Copilot comments fixed and answered; 1563 backend tests pass |
| AkerBP/autogration_frontend#165 | `feature/results-projects` | Results project mode: baseline plus cases, bookings vs produced, settlement, transfers, frontier, 8 SVG visuals; Sm3 oe default when no prices are uploaded | ready; 5 Copilot comments fixed and answered; 365 tests, typecheck and lint pass |
| AkerBP/autogration#1102 + AkerBP/autogration_frontend#166 | `feature/preset-dataobject-tables` | Presets also store DataObject table edits, so the Froskelår switch can be one selectable preset (P9); simulate with a preset applies its table edits | ready; Copilot review requested; backend 1431 tests and CI pass, frontend 273 tests. Migration 0023 clashes with #1101: the second to merge renumbers to 0024. Deploy the backend first |
| merged 15 Nov | – | #1076 (archive names with brackets), #1077 (fetch missing files before validation), #1079, frontend #138 (Results section) | merged |

Where an agent should look hardest:

- **#1101**: the migration (projects, members, `project_member_id` on the idempotency
  claim), "exactly one baseline per project", members filtered by read access, and that
  submitting without a project behaves exactly as before.
- **#165**: the economics and settlement engine and its tests, that reference data stays
  in the browser (local storage per project), and the unit on every chart. There are no
  DOM tests (Vitest runs without jsdom), so keyboard and hover behaviour need a manual
  look.
- **Presets** (#1102, #166): that existing presets (assumptions only) still load and
  apply unchanged. Note the behaviour change: loading an assumptions-only preset on the
  simulate page now also clears the current schedule events and table edits.

## The Froskelår on/off switch

- **Today (toolkit).** A project's `switch` block holds the WELL_OFF schedules for FL1
  (`RESOLVE.MODULE[0].MOD[0].EQUIP[754]`) and FL2 (`EQUIP[764]`) plus five table changes
  on rows 42–43 (`Wells_data` PI and Abandonment_WC; `Wells_constraints` MaxLiquidRate,
  MinGasInj, MaxGasInj). Every "off" request gets them. Verified on the baseline above.
- **In the app, next.** Once the presets PRs are on test, the same content is saved as the
  preset "Froskelår off" on `01a1e49f…`, so anyone can switch Froskelår off from the
  simulate page. Nothing is saved before the PRs are merged.
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

## How to reproduce or follow

From `studies/alvheim-tiein`, with `.env` pointing at test (see the toolkit README):

```powershell
uv run tiein project show --project froskelaar-fixed       # cases, runs, web compare link
uv run tiein optimise status settle-w1 --project froskelaar-fixed
uv run tiein optimise step settle-w1 restructure-w1 soften-w1 outer-w1 --project froskelaar-fixed --watch 900
uv run tiein optimise report settle-w1 --project froskelaar-fixed --rule minimal
uv run tiein bookings --project froskelaar-fixed            # booked vs produced, violations.csv
uv run pytest -q                                            # 220 tests
```

The VS Code tasks **Study: optimise watch (all studies)** and **Study: optimise watch log**
do the same. The toolkit README has a section on optimisation studies.
