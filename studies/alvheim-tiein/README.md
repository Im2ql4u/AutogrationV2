# Alvheim tie-in study

Tooling to run Autogration simulations of the Alvheim hub with and without a new
reservoir, compare production well by well, value it per licence and company, and settle
who pays whom. The reasoning, open questions and analysis plan are in
[research/21-alvheim-tie-in-study.md](../../research/21-alvheim-tie-in-study.md).

## Try it now (no access needed)

```powershell
cd studies/alvheim-tiein
uv sync
uv run tiein demo      # data/demo: the `demo` project, synthetic results + fictional economics
```

Then open, with the kernel **alvheim-tiein (study .venv)** (this folder's `.venv`):

- [01_with_without_settlement.ipynb](notebooks/01_with_without_settlement.ipynb) with
  `DEMO = True`: the whole method (per-well deltas, deferral vs loss, settlement matrix,
  hub vs company objectives) on synthetic data.
- [02_public_data_sodir.ipynb](notebooks/02_public_data_sodir.ipynb): current licensees
  and production history of the Alvheim-area fields from public Sodir FactPages.

## Connect to Autogration

1. Make sure you can open the Autogration web app (Aker BP Entra sign-in). The API uses
   the same identity; there is no separate API account.
2. Running needs the **contributor** role where roles exist (test and dev today; the
   change is on its way to production). Every Aker BP user starts as a reader. Ask a
   contributor to add you on the web app's *Access* page, or run
   `uv run tiein request-access` (posts a request to the admins' Teams channel).
3. In that signed-in browser open `<web app>/api/v1/users/me/api-access`. It shows the
   API `base_url` and `token_scope`.
4. `copy .env.example .env` and set `AUTOGRATION_API_URL`, `AUTOGRATION_API_SCOPE` and
   `AZURE_TENANT_ID`. The default `browser` sign-in opens a login window once and caches
   the token encrypted in your user profile; `device-code` works without a local browser.
   As a stop-gap, paste a token from `<web app>/api/v1/users/me/token` into
   `AUTOGRATION_TOKEN` (it expires).
5. `uv run tiein access` prints your user, role and the assets you can see.

PETEX itself only runs on Autogration's Azure VMs; a local backend can't run cases.

## Projects

A **project** groups runs that are compared against one **baseline**. Projects are
optional: `tiein run REQUEST.yaml --name <name>` starts a one-off run (logged in
`data/adhoc`), and `status`/`fetch`/`steps` without a current project (or with `--adhoc`)
work on those.

A project has:

- a type:
  - `case_comparison`: about a new reservoir, with its wells as the "switch";
  - `scenario_comparison`: cases differ only by their changes, no switch;
- the **environment** its runs live in (named in `.env`; model ids and runs only exist
  there);
- the registered model, the booking groups, one **baseline** case and the cases compared
  with it.

Runs made elsewhere (by a colleague, in the web app) are attached as `imported` cases
with `tiein project add-run <task or group id> --case <name>`. They are never resubmitted.

```
data/projects/<slug>/
  project.yaml   definition: environment, switch, bookings, limits, cases (edit this)
  runs.json      run log: each case's request (or import source), revisions and tasks
  results/ steps/ bookings/ workbench/   downloads and analysis output
```

A case is one simulate request and can build on another case (`based_on`), inheriting
its changes: for example a tuned baseline (gas-lift and choke dP per well, see `tiein
project levers`) and the tie-in on top of it.

- **Case comparison.** Each case sets the switch `on` or `off`. The baseline must be one
  run with the reservoir off: its wells get WELL_OFF events from the forecast start, plus
  the `off_changes` the model can't undo.
- **Table cells.** They can take a row range and one value:
  `{object_alias: Bookings_oil, table_name: Tyrving, rows: "0-23", value: 99999}`.
- **Run limits.** `tiein submit` counts the runs a request starts (sweeps multiply) and
  refuses more than the project's limits: 40 per submission and 40 of your unfinished
  runs at once by default, never more than 50. Submissions carry an Idempotency-Key, so
  a retried request never starts the runs twice.
- **Web link.** `tiein project show` prints a link that opens the project's runs in the
  web app's compare view, baseline first.

## Run a project

```powershell
uv run tiein init                         # data/reference templates + data/projects
uv run tiein register --s-drive "S:\ASSET\...\model.rsl" --name "<name>" --asset Alvheim --wait
uv run tiein models --asset Alvheim       # registered models (model_id = registration task id)
uv run tiein project new froskelaar-tie-in --name "Alvheim Froskelaar tie-in" --model <model_id> `
    --env test --switch-label Froskelaar --switch-wells FL1,FL2 --user-licenses 869 --use
uv run tiein project new booking-release --name "Alvheim booking release" --model <model_id> `
    --type scenario_comparison --env test --import-baseline <task_id>   # baseline run made elsewhere
uv run tiein project add-run <task_id> --case m_lift_all              # attach another existing run
uv run tiein project show                 # environment, switch, booking groups, cases, status, web link
uv run tiein project levers               # gas-lift and choke dP settings of the booked wells
# edit data/projects/<slug>/project.yaml (cases) and data/reference/*
uv run tiein project check                # against the model: wells, booking groups, cells
uv run tiein submit all --dry-run         # requests and run counts
uv run tiein submit all                   # or one case: `tiein submit tie_in`
uv run tiein status --watch 60
uv run tiein task <task_id> --logs        # failure, missing files and latest log lines
uv run tiein steps baseline               # tracked variables while it runs
uv run tiein fetch                        # results and tracked steps of completed runs
uv run tiein bookings                     # booked vs produced per group and company -> bookings/
uv run tiein export-workbench             # folder for the results viewer
```

Commands use the current project (`tiein project use <slug>`) or `--project <slug>`. VS
Code tasks (**Study: ...**) wrap the common commands, including **Study: results viewer**
(results-workbench Streamlit app).

Notebooks (kernel **alvheim-tiein (study .venv)**):

- [00_access_and_monitoring.ipynb](notebooks/00_access_and_monitoring.ipynb): projects,
  run status and tracked variables while runs go.
- [01_with_without_settlement.ipynb](notebooks/01_with_without_settlement.ipynb): a case
  against the baseline, value per licence and company, who pays whom.
- [03_project_bookings.ipynb](notebooks/03_project_bookings.ipynb): are the bookings met
  in the baseline; produced minus booked per group and company; how that changes when
  the reservoir comes on; the wells behind each group.

The notebooks are generated by `notebooks/_build_notebooks.py`; edit that and rerun it.

## Bookings

The model limits each tie-back group's rates (Boyla+Frosk, Volund, Vilje+Skogul,
Tyrving) to its booked FPSO capacity: monthly oil, gas and water to September 2027,
then gas and liquid. `tiein bookings` compares each group's production with that,
using the limits the model applied when the run tracked them (`bookings.track_applied`)
and the booking tables otherwise. Per company, a group's booking is split by its wells'
licence shares, weighted by what each well produced. The new reservoir has no booking
and appears as an unbooked group. Group membership comes from the model's GAP groups.

The booking tables are read as the workflow reads them, by step index:

- monthly rows to the last booked month;
- then `Future_Bookings` row k;
- then the flat `Bookings_future`.

On any other grid than the model's monthly one, they land on the wrong dates (see
[ISSUES.md](../../ISSUES.md), M2).

Two things to keep in mind when reading the report:

- **Gas.** Gas bookings limit total gas, lift gas included. Until
  `bookings.lift_gas_property` names GAP's lift-gas rate, gas is compared as formation
  gas only (`basis` column).
- **Violations.** Steps where a group produced more than 2 % above its applied limit,
  so GAP did not honour it, are listed in `violations.csv`. Treat those steps as
  suspect.

## Optimisation studies

A study searches over a few levers on top of a project's base case and scores every run
against the reference cases. The schemes come from
[research/22](../../research/22-optimisation-schemes-and-projects.md):

| Scheme | What it changes |
|---|---|
| `total_then_settle` | GAP optimises the hub total (neutral weights, bookings released), then the licences settle |
| `soften_bookings` | partly releases bookings and partly neutralises the weights, on a small grid |
| `restructure_bookings` | booking plans: lend unused capacity (R1), pro-rata (R4), cap Froskelår (R3) |
| `outer` | pattern search over weights, release and liquid scale around Autogration |

```powershell
uv run tiein optimise new settle-w1 --scheme total_then_settle   # writes study.yaml from a template
uv run tiein optimise plans restructure-w1 --s2 tie_in_lift      # booking plans (restructure only)
uv run tiein optimise check settle-w1                            # builds every kind of request
uv run tiein optimise step settle-w1 --dry-run                   # next wave: new and shared runs
uv run tiein optimise step settle-w1 soften-w1 --watch 900       # follow, score, submit until done
uv run tiein optimise status settle-w1                           # evaluations so far (offline)
uv run tiein optimise report settle-w1                            # tables, frontier, settlement
uv run tiein optimise cancel settle-w1
```

- **Settlement.** `report` writes `settlement.csv`: for the best plan against the base
  case and each reference case, the change Δ per licence and, under each rule, the
  award and transfer (positive received). `proportional` (decided, the default) splits
  the surplus by booked capacity r_l: discounted Sm3 oe of oil + gas bookings, split
  over a group's licences by production, with licence 203 holding the unbooked FPSO
  capacity. Policy schemes use the comparator's bookings; `restructure_bookings` uses
  the plan's own. `--rule minimal` (losers made whole) or `equal` prints the others.
- **Value basis.** With `value_basis: oe` in `economics.yaml` (the default), value is
  oil-equivalent volume: oil Sm3 + gas Sm3 / `gas_sm3_per_sm3oe` (1000), discounted, with
  costs and tariffs in Sm3 oe too. No prices are needed, and every comparison is
  relative: case against baseline, and each case against its bookings. Set
  `value_basis: price` and add `prices.csv` for money.
- **Shared runs.** Studies in the same project that need an identical request (the same
  base and baseline runs, say) use the run another study already started. The dry run
  shows them under "shares", they don't count against the budget, and `cancel` leaves
  them running.
- **Watching.** `step --watch` rides out gateway errors and expired tokens. To keep a
  log, set `PYTHONUNBUFFERED=1` and redirect the output; the VS Code tasks **Study:
  optimise watch (all studies)** and **Study: optimise watch log** do this.

## Reference data (`data/reference`)

| File | Content |
|---|---|
| `entities.csv` | `identifier, identifier_type, field, license` for every producing well |
| `licence_shares.csv` | `license, company, share (fraction), valid_from, valid_to`; `tiein sodir` writes public shares for the area to start from |
| `prices.csv` | `date, oil_price_per_bbl, gas_price_per_sm3`, step-wise from each date; needed only with `value_basis: price` |
| `economics.yaml` | `value_basis` (`oe` or `price`), currency, valuation date, discount rate, unit costs, tax approximation, tariffs |

Wells missing from `entities.csv`, shares that don't sum to 1, units without a
conversion and price decks starting after the first period are errors, not warnings.

## Conventions

- Volumes are calendar-day `Avg*Rate` × days until the next timestep, as in
  results-workbench. `volume_convention_check` compares this with cumulative series;
  check it on the first real run.
- Discounting is mid-period from `valuation_date`. `tax_rate` is a flat approximation.
- Settlement is a first model to discuss, not contract terms: the paying licences
  compensate other licences' PV losses and pay the change in tariffs; flows are spread
  over both sides' company shares at the valuation date.

## Data and confidentiality

Everything study-specific (projects, run logs, prices, contract terms, downloaded runs)
is in `data/`, which is git-ignored because this repository has a GitHub remote. Only
code, templates and the fictional demo inputs are tracked.

## Checks

```powershell
uv run pytest -q
uv run ruff check .
```
