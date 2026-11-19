# Work log – Alvheim Froskelår tie-in and bookings

Newest first. Run ids are on **test** unless marked; full ids are in the toolkit's
`data/projects/*/runs.json` and in [ISSUES.md](../ISSUES.md).

## 19 Nov 2026

- **PR review comments fixed.**
  - AkerBP/autogration#1101 (optional projects): all 6 Copilot comments fixed with tests and
    answered. HEAD `6c49d3b7`; 1563 backend tests pass. Marked ready, Copilot review
    re-requested. One comment was declined with a reason: the cursor value "a" already
    returns 422, and a test now pins that.
  - AkerBP/autogration_frontend#165 (Results project mode): all 5 comments fixed in
    `c0dd0d0`:
    - the view is keyed by project, so reference data doesn't leak between projects;
    - values that round to zero are neutral grey;
    - a bounds-checked hover hit-test;
    - keyboard-operable company selection;
    - runs without results keep their status badges.
  - Also on #165, Sm3 oe is the default value basis without prices (`bb0fa0f`). 365 tests,
    typecheck and lint pass. Marked ready, Copilot review re-requested.
- **Froskelår switch as a preset.** Presets store only `assumptions`, so the switch's 10
  DataObject cells can't be saved with it (P9). Presets now carry `dataobject_tables` in
  AkerBP/autogration#1102 (backend: migration 0023, API, simulate with a preset applies its
  table edits) and AkerBP/autogration_frontend#166 (save/load on the simulate page). Both
  are ready for review with Copilot's review requested; backend CI passes. Merge order:
  #1101 also adds migration 0023, so whichever merges second renumbers to 0024. Deploy the
  backend first. No preset has been saved on any deployment.
- **Settlement by booked capacity (T12).** Study scores now record each run's booked
  capacity r_l, and `tiein optimise report` settles by proportional (the decided rule,
  default), minimal and equal. Comparisons against the Froskelår-off baseline are marked
  as the tie-in and not split by these rules. The watcher was restarted at 10:11 so wave
  1's scores carry the basis. 222 toolkit tests pass.
- **Relative value (T9).** `value_basis: oe` (default): value in Sm3 oil equivalent,
  pre-tax, discounted 8 % to 1 Jan 2027; prices optional. The toolkit has 220 tests.
- **Run sharing (T10).** Studies in one project reuse identical runs instead of starting
  copies. It saved 6 MH runs today.
- **Optimisation wave 1 started, 09:17.**
  - settle-w1 submitted e001 (MH base, task `01a1f2e2-1afb-76a6-9667-d3d67809cd75`) and e002
    (MH reference, FL off, task `01a1f2e2-2085-7430-8bb8-13384b841d8f`).
  - restructure-w1, soften-w1 and outer-w1 share both runs.
  - One watcher steps all four every 15 min and logs to
    `data/projects/froskelaar-fixed/studies/watch.log`.
- **Handoff.** This folder; ISSUES.md updated (T9–T12, P5, P9, 19 Nov runs); toolkit README
  has an optimisation section.

## 18 Nov 2026

- **Your fixed model's 31 runs re-checked.** Findings A1–A7 and M1–M7. Errata went at the
  top of REPORT.md, compare.md and comparison.md.
- **Decisions** (recorded in research/22):
  - a booking is an economic entitlement;
  - transfers are allowed and shown;
  - settlement is proportional to booked capacity;
  - placeholder economics;
  - the FL-off fix is ours;
  - build all phases.
- **Runs, all completed and analysed by 21:30:**
  - `booking-release`: four monthly single lifts and a booking-period-only release
    (groups c532f78f, 82cc6dfa, f4167826, 9110322b, 6a552c6e);
  - `froskelaar-fixed` baseline, FL off (`01a1edfd-73d5-76d9-8f5b-d5f7c8533dfc`, group
    51d747e6);
  - two probes on weights and lift gas (948cc9da, a226f4e2).
- **Toolkit.**
  - Projects are optional, imported runs are allowed, and environments are named.
  - Submits are idempotent.
  - Bookings report with violations.
  - Row-range cell edits.
  - Then phase 1: levers, feasibility checks, ledgers and settlement, booking
    restructuring (R1/R3/R4), the MH grid with remapped cells, the study driver,
    `tiein optimise`, and `export-reference` for the Results page.
- **Design.** [research/22](../research/22-optimisation-schemes-and-projects.md): four
  selectable schemes (total then settle, soften bookings, restructure bookings, an outer
  loop), optional projects in Autogration, the Results visuals, and phases 0–4.
- **Draft PRs opened:** AkerBP/autogration#1101 and AkerBP/autogration_frontend#165.

## 17 Nov 2026

- Fixed booking model registered on test as `01a1e49f…` ("ALV_NM_BC_Oct2026 updated
  Bookings"). 31 runs, and the handoff files REPORT.md, compare.md and comparison.md.
- Platform fixes on test: #1094 (no per-task model copy), #1095 (licence requeue),
  #1096/#1098 (Idempotency-Key), #1084 (ISO schedule dates, `GAP.` tracked variables),
  #1085 (step dating).

## 12–15 Nov 2026

- AkerBP/autogration#1076 (archive names with brackets) and #1077 (fetch missing files
  before validation, cancellation-aware waits), #1079, and AkerBP/autogration_frontend#138
  (Results section, four Copilot review rounds). All merged on 15 Nov.
- Toolkit started: access, registration, models, projects with an on/off switch,
  notebooks 00–03.
