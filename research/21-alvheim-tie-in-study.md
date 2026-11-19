# Alvheim Tie-in Study: Production, Value, Settlement and Optimisation

Status date: 2026-11-10

## Scope

A new reservoir is to be connected to the Alvheim hub. The study must:

1. simulate the hub with and without it in Autogration (RESOLVE/GAP);
2. show how production changes across wells;
3. value the change per licence and per company, and answer "who should pay whom";
4. optimise well rates for financial gain, judged both by total hub value and by
   company value; and
5. use physics, historical production, PVT and ownership data for exploratory data
   science.

This note records what is verified, what is assumed, the proposed method, the
environment built for it ([studies/alvheim-tiein](../studies/alvheim-tiein/README.md)),
and the questions to bring to stakeholders. Statements follow the discipline in the
[research README](README.md): **Fact** (traced to source or data), **Public** (public
record), **Regulation**, or **Hypothesis** (paired with a test).

## Main Finding

The simulation half is possible with the current product. The financial half does not
exist anywhere in the workspace and has been started as a study package outside
Autogration. The scientifically decisive choices are the counterfactual design (same
model, only the tie-in switched) and splitting the impact into channels that contracts
treat differently. The commercial decisive input, contract terms, must come from people,
not data.

## Verified Facts

### Autogration

- **Fact.** `POST /api/v1/models/{model_id}/simulate` takes `assumptions`, a `preset` or a
  prebuilt `compute_set`. Every combination of `replace` values and setting sweeps becomes
  a case, which runs as one `petex_compute` task. All tasks share an
  `assumption_group_id`, and `GET /tasks?assumption_group_id=` reports progress in
  `status_counts`. The default case limit is 1000 and the default VM limit is 10
  (`apps/backend/backend/modules/models/routes.py`, `compute_set.py`, `.env.sample`).
- **Fact.** An assumption set can edit properties, add equipment (`new_nodes`), change
  connections (`topologies`), add schedule events, sweep RESOLVE and module (optimiser)
  settings, and record any OpenServer variable at each solver step (`tracked_variables`,
  read back via `GET /tasks/{id}/step-results`) (`shared/models/models/assumptions.py`).
- **Fact.** Optimiser objective direction, controls, constraints and bounds are
  reachable through module settings. There is no economics abstraction: no prices,
  phase values, ownership or revenue objective in any contract model.
- **Fact.** Results are long-form rows (module, system, identifier, identifier_type,
  timestamp, case number, property, value, unit) covering rates, `Avg*Rate`,
  cumulatives, GOR, WCT and pressures. Units follow the model's own unit system and are
  not normalised (`apps/backend/EXPORT_FORMAT.md`).
- **Fact.** Scripts authenticate with the same Entra identity as the web app.
  `GET /users/me/api-access` returns the API base URL and token scope. The Azure CLI's
  public client is allowed by default, so an `az` or azure-identity token for scope
  `api://<app-id>/access_as_user` works without a separate account
  (`modules/users/api_access.py`, `core/settings.py`).
- **Fact.** The frontend and results-workbench can already compare cases per well and
  group wells by licence and working interest. Sales factors are a declared placeholder.
- **Fact.** Merging to Autogration's `development` branch deploys. Changes to
  `shared/models`, auth or DB schema need approval (`autogration/AGENTS.md`). Study
  logic therefore starts outside the product.

### Alvheim area (public, Sodir FactPages, fetched 2026-11-10)

| Field | Owner | Licensees |
|---|---|---|
| Alvheim | PL 203 | Aker BP 80, ConocoPhillips 20 |
| Vilje | PL 036 D | Aker BP 75.757, ORLEN 24.243 |
| Volund | PL 150 | Aker BP 100 |
| Bøyla | PL 340 | Aker BP 80, Concedo 20 |
| Skogul | PL 460 | Aker BP 65, ORLEN 35 |
| Tyrving | Tyrving unit | Aker BP 61.19, Petoro 26.86, ORLEN 11.95 |

- **Public.** First saleable production: Alvheim 2008-06, Vilje 2008-08, Volund 2009-09,
  Bøyla 2015-01, Skogul 2020-03, Tyrving 2024-09. Gas leaves via SAGE to the UK and oil
  by shuttle tanker. Boa straddles the UK border.
- **Public.** Equinor is not a current licensee in these fields. Petoro (the State's
  direct financial interest) is, via Tyrving, so a state party sits on one side of some
  settlements.
- **Public.** Froskelår (24/9-14 S, PL 869: Aker BP 80, Concedo 20, "production likely
  but unclarified") forms one cross-border accumulation with Losgann on the UK side. In
  2026 Aker BP agreed to buy Apache's operated interest in the UK portion and described
  the accumulation as an Alvheim-area tie-back opportunity. A cross-border development
  would add unitisation and two fiscal regimes.
- **Public.** Kjøttkake (35/10-15 S, now Lyra) lies in block 35/10, the northern North
  Sea. It is **not** an Alvheim candidate.

### Regulation

- **Regulation.** The Regulations relating to the use of facilities by others
  (FOR-2005-12-20-1625) frame tie-in terms: tariffs cover the owner's costs plus a
  reasonable profit, and "compensation for loss and/or postponement of production shall
  be determined on the basis of the profit which could have been achieved on the lost
  and/or postponed production". Disputes can go to the Ministry of Energy. The
  with/without simulation measures exactly the lost and postponed production this
  refers to. <https://www.sodir.no/en/regulations/regulations/facilities-use-by-others/>

### Data access

- **Fact.** Goose reaches CDF time series through Enlight tag mappings, offers governed
  analysis, and needs Entra app roles. Its skills state that Alvheim has limited rate
  tags and no reliable export tag. MPFM or test-separator rates are trustworthy;
  allocated `ec_*` series are daily/monthly reporting numbers only; DOF/PETEX-derived
  rates are not measurements.
- **Fact.** well-potential-tool reads CDF EC/OFM well histories (field code `ALV`) with
  interactive Entra login.
- **Fact.** WhitsonPVT has an external API, but access must be provisioned
  ([12](12-whitsonpvt-integration-and-pvt-engine.md)).
- **Fact.** Sodir FactPages CSV exports need no account. Licensee and ownership history
  and monthly field production are downloadable.

## Method

### Counterfactual design

| Arm | Content | Purpose |
|---|---|---|
| A: without | Registered model, tie-in off | Counterfactual |
| B: with | Same model, tie-in on | Total impact B − A |
| C: uncapped | Tie-in on, FPSO gas/water/liquid limits relaxed | Hydraulic interference C − A; capacity displacement B − C |
| D… | Start date, routing, rate caps, gas lift | Design alternatives |

A and B run as two values of one `replace` assumption in one simulation. Both cases then
share the registered model, settings and VM image, so differences come only from the
tie-in.

The tie-in itself (MBAL tank, PROSPER wells, GAP pipes and the connection) is best
built in PETEX by the responsible engineer and registered with an on/off switch.
`new_nodes` can add equipment, but it does not build validated reservoir and well
models.

### Value channels

| Channel | Who is affected | Usual settlement |
|---|---|---|
| New field's own production | New licence | Own revenue |
| Capacity displacement (FPSO limits bind) | Host and other tie-ins | Compensation for lost/postponed production |
| Hydraulic back-pressure (shared flowlines, manifolds, risers) | Wells sharing routing | Same, often disputed |
| Shared cost, longer hub life | Host owners | Tariff and cost sharing |
| Commingled quality, allocation | All | Quality bank, allocation agreement |

**Deferred versus lost.** Compare undiscounted and discounted changes per licence. A
near-zero undiscounted change with a negative PV means deferral. Both negative means
loss within the horizon. The simulation must run to cessation, otherwise deferral past
the horizon looks like loss.

### Settlement (first model, for discussion)

1. Value per well and period: volumes × price deck − variable costs, discounted
   mid-period. Tax optional as a flat approximation.
2. Change per licence between B and A.
3. The paying licence(s) compensate each other licence's PV loss. Gains are not clawed
   back unless chosen. Tariffs are charged on the change in the payer's volumes.
4. Licence flows are spread over payer and payee company shares into a
   company-to-company matrix and net positions. These are transfers, so they sum to
   zero.

Implemented in `alvheim_tiein.settlement`. Open choices are listed in the question log.

### Optimisation

**Model levers (confirmed in the registered model, 2026-11-13).** Gas-lift choke,
production choke dP control and calculated pressure drop are adjustable (study owner):

| Lever | Where in the model | Current setting |
|---|---|---|
| Gas-lift choke / injection rate | `Wells_constraints` `MinGasInj`/`MaxGasInj` (1000Sm3/d) → GAP well `MinGinj`/`MaxGinj` each timestep; the workflow sets `AlqControl` (CALCULATED, FIXEDVALUE or no gas lift) | optimiser between the limits (FL1: 38-120; NT1 fixed at 80) |
| Production choke dP control | the workflow sets GAP well `DPControl` to `CALCULATED` every timestep, so a fixed `DPControlValue` is overwritten | `CALCULATED`; fixed dP needs a workflow change in the model |
| Calculated pressure drop | as above: the optimiser chooses the choke dP within `Wells_constraints` `MaxLiquidRate` (Sm3/d) and `MaxDrawdown` (bar) | `CALCULATED` |
| Well priority (weighting) | `Weightings` and `Weightings2025` DataObjects → GAP well `weighting`, each timestep (`Active_events` "Weightings" = 1) | per booking group (Tyrving 3.0/2.5, Volund 2.0; the 2025 table has 1.5 for most and 0.01 for Volund). Which table applies when is being probed (M6 in [ISSUES](../ISSUES.md)); wells not listed keep the GAP default |
| Tie-back capacity (booking) | `Bookings_*`, `Future_Bookings_*`, `Bookings_future` DataObjects → GAP `GROUP.MaxQoil/MaxQTotGas/MaxQwat/MaxQliq` | monthly to 2027-09, then flat |
| FPSO capacity | `Capacities`, `Gas_upgrade` DataObjects | gas 4300 → 4700 1000Sm3/d (Gas Upgrade), water 36018, oil 24802 Sm3/d |

The RESOLVE workflow rewrites well settings every timestep (gas-lift limits, maximum
liquid and drawdown from `Wells_constraints`; PI and abandonment water cut from
`Wells_data`; `DPControl`, `AlqControl`), so in this model the levers are DataObject
cells, changed per case with `dataobject_tables`; GAP property changes on those wells
are overwritten. `tiein project levers` lists each booked well's cells with their rows.
Autogration reads and writes the cells in metric units. FL1/FL2 have no booking and no
`Weightings` row. The workflow also opens FL1/FL2 on 2030-01-01, which undoes WELL_OFF
schedule events. Zero `MaxLiquidRate` and gas lift alone stopped working from Sep 2030.
The fixed-model baseline therefore also sets PI and abandonment water cut near zero
(rows 42, 43). On 18 Nov FL1/FL2 were 0 at every step to Mar 2031, the window where the
old switch failed; the run continues to 2041 (M1).

The four optimisation schemes (soften bookings, optimise the total then settle, outer
optimiser, restructure bookings when Froskelår opens), and how they become selectable
in Autogration, are designed in [22](22-optimisation-schemes-and-projects.md).

**Decisions, 18 Nov 2026** (details in 22):

- A booking is an economic entitlement of the licences in a tie-back group. Water and
  liquid bookings are balancing levers for the FPSO, not entitlements.
- Transfers between licences are allowed, and are measured and shown in Results.
- The surplus of a policy change is split in proportion to booked capacity (oil and
  gas, Sm3 oe, discounted); the host's basis is the FPSO capacity the bookings leave.
- Economics are placeholders until a planning deck arrives: pre-tax, 8 %, valuation
  1 Jan 2027, 70 USD/bbl and 0.30 USD/Sm3 gas.
- The Froskelår-off switch is ours: layered assumption changes on the fixed model (M1).
- Scheme 4 asks whether reordering or restructuring the bookings when Froskelår opens
  can leave every company better off, in kind or after transfers. Its families are
  use-it-or-lend-it, value-neutral swaps over time, a Froskelår booking, and a
  clean-sheet re-split; candidates are screened with a capacity surrogate and then run.

- **Within each timestep (RESOLVE/GAP optimiser).** First check which objective, control
  and constraint tags the registered Alvheim model exposes (`tiein settings`). If
  per-phase or per-well weights are settable, weighting by unit margin makes the
  optimiser maximise value rather than oil. This is myopic: it does not value deferral.
- **Over field life (outer loop).** Decision variables are per-well rate caps or chokes
  by period (fixed dP vs calculated), gas-lift allocation (injection limits per well),
  weightings, bookings, and the tie-in start date. Each evaluation is a full
  RESOLVE run, so the loop is:
  - small designed batches, up to 10 VMs in parallel;
  - a surrogate or Bayesian optimiser to propose the next batch;
  - full-physics confirmation of the winners, within the guardrails of
    [06](06-ml-and-adaptive-studies.md).
- **Objectives.** Both total hub value and each company's value (settlement included)
  are reported per case. `price_of_conflict` gives what the hub loses if one company's
  preferred case is chosen.
- **Governance.** Aker BP operates all these licences. An operating plan has to be
  defensible to every partner, so the hub-optimal plan with transparent settlement is
  the candidate for action. Company-optimal results are analysis, not a proposal.
- **Fair division.** Grouping licences into at most about 5 players gives 2^5 = 32
  coalition runs (each subset of groups producing). Shapley values then split the hub's
  joint value by marginal contribution. That is a principled reference beyond the
  regulatory minimum (`settlement.shapley_values`).

### Data science track (ordered by decision value)

1. **Past tie-ins as natural experiments.**
   - *Hypothesis:* start-ups of Skogul (2020-03) and Tyrving (2024-09) raised wellhead
     and manifold pressure and cut rates of neighbouring wells on shared routing.
   - *Test:* event study on WHP, PCV and MPFM tags in CDF around those dates, compared
     with what the RESOLVE model predicts for the same events.
   - *Value:* it shows whether the model's interference, and so the compensation, can be
     trusted.
2. **Historical capacity utilisation.**
   - *Hypothesis:* displacement dominates only if the FPSO often runs at its gas, water
     or liquid limit.
   - *Test:* time at limit from facility tags.
3. **Model versus history per well.** Residuals from past Autogration runs (`GET /runs/`)
   against measured rates, using the trusted-source rules above.
4. **Interaction matrix.** How each well's rate responds to the others (∂qᵢ/∂qⱼ), from
   choke-perturbation sweeps, compared with responses to historical shut-ins.
5. **Fluids.** PVT and quality clustering across fields, for commingling, export
   quality and quality-bank exposure (needs WhitsonPVT or report access).
6. **Ownership history.** Equity-weighted production by company from Sodir data
   (notebook 02).
7. **Surrogates.** Fast approximations of the RESOLVE response, to steer the optimiser
   only; final numbers always come from full runs.

## Environment Built

[studies/alvheim-tiein](../studies/alvheim-tiein/README.md) is a `uv` project that
depends on results-workbench. It contains:

- **`tiein` CLI**: init, access, models, browse, settings; `project new/list/show/use/
  check/levers`; submit (project cases only, run-count limits), status --watch, steps,
  fetch, bookings, export-workbench, sodir, demo.
- **Client**: an Entra token via azure-identity using the Azure CLI client, an encrypted
  token cache in the user profile, cursor paging, group progress, step results, and
  verified streaming of bundles.
- **Projects** (2026-11-13; optional since 2026-11-18): a project in
  `data/projects/<slug>/` groups runs compared against one baseline.
  - Type: `case_comparison` (a switch for the new reservoir) or `scenario_comparison`
    (no switch).
  - It also records the environment, model and booking groups.
  - Cases build on each other (`based_on`), and runs made elsewhere attach as
    `imported` cases.
  - One-off runs need no project (`tiein run`).
  - A run log ties every case to its tasks, revisions and request digest.
  - Submissions are idempotent and capped at 40 runs (configurable, never above 50) per
    submission and at once.
- **Bookings**: booked (applied limits when tracked, else the model's booking tables) vs
  produced per booking group, split per company by production-weighted licence shares;
  change against the baseline; the wells behind each group.
- **Economics**: strict unit conversion, licence shares that can change over time, an
  as-of price deck, mid-period discounting, and tariffs.
- **Settlement**: compare, decompose, compensation, change in tariffs, company matrix,
  objective table, price of conflict, Shapley values.
- **Notebooks** (kernel `alvheim-tiein`, the study's `.venv`):
  - 00: projects, access and monitoring;
  - 01: a case against the baseline and settlement, with a demo toggle;
  - 02: public Sodir data;
  - 03: bookings: baseline satisfaction, produced minus booked per company, change when
    the reservoir comes on, wells behind each group.
- **VS Code tasks**: Study: check access / list projects / submit case (dry run first) /
  status (watch) / fetch results and bookings / results viewer / tests.
- **Confidentiality**: all study data lives in git-ignored `data/`.

Verification: 29 unit and integration tests pass, and notebooks 01 and 02 run to
completion. The demo settlement nets to zero across companies. The exported folder
loads in results-workbench, and its volumes match the study's own calculation. With
projects and bookings (2026-11-13): 56 tests; notebooks 01 (demo project) and 03 (a
synthetic copy of the Froskelår project with the model's real booking tables and group
membership) run to completion.

### Project workflow (case comparison with bookings)

1. **Baseline**: the model with the new reservoir off. Check per booking group and month
   whether production meets the booking.
2. **Tuned baseline** (`based_on: baseline`): where bookings are not met, adjust each
   well's gas-lift injection and production choke dP until they are.
3. **Tie-in** (`based_on` the tuned baseline, switch on): how the system evolves.
4. **Compare**: produced minus booked per group and company, baseline vs tie-in, and
   whether the bookings should change. The shortfall volumes feed the settlement.

## Plan

| Phase | Outcome | Depends on |
|---|---|---|
| 0 Access and plumbing | `tiein access` works; one existing Alvheim run pulled and viewed | Web-app access, `.env` |
| 1 With/without, single deterministic case | Per-well deltas, binding constraints, displacement vs back-pressure | Model with tie-in switch |
| 2 Economics and settlement | Licence and company values, settlement matrix, price sensitivity | Price deck, agreement terms |
| 3 Optimisation | Value-weighted optimiser, then outer-loop strategy | Optimiser tags, phase 1 |
| 4 Data science | Interference event study, utilisation, model vs history, Shapley | CDF/Goose access |

Phase 4 items 1, 2 and 6 can start before the model exists.

## Question Log (for the stakeholder presentation)

### Scope and commercial

1. Which reservoir is the tie-in (Froskelår/Losgann or another), and which licence and
   partners own it? If cross-border, which unitisation and fiscal treatment applies?
2. What does "booking" mean here? **Answered 18 Nov:** a licence's contractual
   entitlement to FPSO capacity for its tie-back group, i.e. an economic entitlement
   (Scheme 4 in [22](22-optimisation-schemes-and-projects.md)). Water bookings are closer
   to platform balancing.
3. Which agreements govern Alvheim tie-ins today (processing/TPA agreements, allocation
   agreement, quality bank, cost sharing)? Are their tariff and priority rules
   available to the study?
4. When the FPSO is constrained, who is curtailed first by agreement: host first,
   pro-rata, or by value? The simulated priority must match.
5. Is compensation pre-tax or after-tax, on PV or nominal, and are gains to others
   (e.g. a longer hub life) netted against losses?
6. Whose objective decides the operating plan: hub value with settlement, or something
   else? Who signs off a company-level view?

### Model and engineering

7. Is there a registered Alvheim RESOLVE model, and who owns it? Can the tie-in be added
   with a reliable on/off switch?
8. Which constraints bind today (gas, water, liquid, gas lift, risers), and which tags
   or properties represent them in the model?
9. Does the simulation run to cessation of production? Is cessation itself an output?
10. Which PVT model represents the new fluid, and does commingling need compositional
    treatment?

### Economics and planning

11. Which price deck, currency, discount rate and cost basis are approved for this
    study, and with which uncertainty ranges?
12. Should CO₂ cost, power and water handling be included explicitly?

### Access and data

13. Autogration web-app access and environment (dev/test/prod) for the study; the token
    scope and tenant for `.env`.
14. CDF/Goose app roles for Alvheim well tags (WHP, PCV, MPFM, allocation); known gaps
    in rate tags.
15. WhitsonPVT API access for the relevant fluids.

## Risks

- **Model calibration.** Settlement numbers inherit the model's interference behaviour.
  Phase 4 item 1 is the check.
- **Horizon truncation** makes deferral look like loss.
- **Allocation and measurement uncertainty** at Alvheim (few reliable rate tags).
- **Confidentiality.** Prices, terms and forecasts must stay in `data/`. The repository
  has a GitHub remote.
