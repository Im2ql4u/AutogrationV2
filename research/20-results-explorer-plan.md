# Results Explorer: from the Yggdrasil Power BI to an Autogration results section

Status date: 2026-10-28. Plan only; no product code written yet.

## 0. Repository baseline (done)

| Repo | State after update | Notes |
| --- | --- | --- |
| `autogration` (V2 worktree) | `work/results-explorer` @ `017cf4c3` (= `origin/development`, 2026-10-27) | Created with `--no-track`: a bare `git push` cannot hit `development`. Untracked `intents/` kept. |
| `autogration_frontend` (V2 worktree) | `work/results-explorer` @ `8d70acb` (= `origin/development`) | Same, no upstream. |
| `C:\Users\aleksekk\autogration`, `...\autogration_frontend` | `development` fast-forwarded (351 / 143 commits) | Source clones, clean. |
| `C:\Users\aleksekk\autogration-infrastructure` | `main` fast-forwarded to `bde8416` | The copy inside `autogration_v2/` is an untracked snapshot, not a clone. |
| `goose`, `well-potential-tool` | `main`/`master` fast-forwarded | Read-only references. |

Branch policy: `main` = prod, `test` = test, `development` = dev. Work happens only on
`work/results-explorer`; PRs target `development`; nothing is pushed without explicit approval.

Relevant upstream work discovered while updating:

- `origin/feature/mcp-agents`: FastMCP server inside the backend (`modules/mcp/{server,tools,oauth}.py`)
  with tools such as `list_tasks`, `get_task`, `browse_model`, `start_simulation`, `list_presets`, `list_assets`.
  **No results tools yet** - this is where results tools attach.
- `origin/skills`: generated `.agents/skills/autogration-api/` and `autogration-results-duckdb/SKILL.md`
  (DuckDB httpfs over `GET /runs/{task_id}/results/parquet`; cases of one study share
  `assumption_group_id`; `run_number == assumption_case`).
- Result contract (long form, per task): `module, system, identifier, identifier_type, timestamp,
  run_number, property_name, value, unit`. Parquet is range-readable and cached server-side.
- Frontend: custom router, `Navbar` + `SidebarNav`, Tailwind/`@akerbp/react-component-library`,
  plain `fetch`, Vitest, `VITE_MOCK` mock mode, CSP enforcement just merged. No results page exists.

## 1. What the Power BI actually is

Source: `S:\YGGDRASIL\IPM\User\vlavol\YGG_PowerBI_share\Yggdrasil_NM_Results.pbix` (208 MB),
inspected read-only from a local temp copy (layout JSON + semantic model via `pbixray`).

### Data model (star schema over CSV folders)

- **Facts** (GAP network-model exports, one CSV per model version, `Folder.Files` appended):
  `Yggdrasil_GAP_results` (well x month, ~50 cols, the workhorse), `Yggdrasil_GAP_ALL_results`
  (adds potentials, velocities, PE5 stability, Turner), `Yggdrasil_GAP_Separators`,
  `Yggdrasil_GAP_InSituRates`, `VRR` (cumulative voidage), `NOAKA_PdQ_results`, `NOAKA_NM_joints_results`.
  `Yggdrasil_GAP_FlowAssurance` CSVs exist on the share but are **not loaded** in the model.
- **Dimensions**: `Cases` (Case_ID, name, description, mgmt name, split-factor set), `Wells`
  (Field > Group > Segment > Well hierarchy, license, project/ADP levels, type, drilled, Frigg_Oil),
  `DateTable` (Excel-serial `DateNum`, days in month), `Separators`, `Licenses` (Aker BP WI),
  `SplitFactors` / `SplitFactor_Sets` / `SplitFactor_Values`, `Slots*`.
- **Logic**: 69 calculated columns on `Yggdrasil_GAP_results` (SSF -> MSS sales conversion,
  NGL yield, 40 MJ GCV normalisation, BOE, monthly volumes, GOR/WCT) and ~100 DAX measures:
  rate-weighted averages (GOR, WCT, SG, API, salinity), calendar-day vs stream-day rates (uptime),
  production efficiency, producer/injector counts, PoP/CoP dates, first-6/12-month volumes,
  net-to-Aker-BP via license WI, and A-minus-B incrementals (`Cases_Incr_A/B`).

### Report (64 pages, 871 visuals)

360 slicers (about 6 identical slicers repeated on every page), 156 line charts, 35 stacked areas,
33 tables, 20 scatter, waterfalls, pivots, KPI cards. Pages cluster into:

| Cluster | PBI pages |
| --- | --- |
| Overview / volumes | Dashboard, Summary, Recoverable, RatesVolumes, ProdVolumes, DG3_YE26, Stat |
| Profiles | Stacked Rates, Tech Profiles, Calendar Days Profiles, Tech+WHT, Stacked Wells, Prod Share, Termsheet, Rate Potentials, In-situ Rates, Mass Rates |
| Case comparison | Compare, Compare Cases (+Cal Days), Compare Profiles, Compare Wells, Cumulatives, Incremental, INCR Sales, Waterfall 1-3, Produced per Well, Well Waterfall |
| Wells / schedule | NEW WELL Names, Wells, Drilling Schedule, Well Review App, TypeCurves (oil/gas), VLP Ranges |
| Fluids / sales factors | WCT, GOR, WGR, OilSG, GasSG, Max_H2S, Frigg Oil, Split Factors (+Compare), Capacity ADJ |
| Health / stability | Well Stability (single, compare), PE Analysis, Voidage, SRU |
| Facilities | Separators |
| Export | Export, Export_TC, FMRA, PI Export (+INC) |

### Lessons to carry over (and traps to fix)

1. The value is in the **semantic layer** (conversions, weighted ratios, calendar vs stream day,
   incrementals), not in the 64 pages. Port the measures, not the pixels.
2. Slicer repetition shows users want one **global filter context** (case(s), hierarchy, period, units).
3. Never average ratios; always weight (GOR, WCT, SG). Encode this in the measure type.
4. GAP writes `3.4e+35` as "no value" (seen in separator files) - must become null with a health flag.
5. Hard-coded defaults (`Selected_CaseB` falls back to Case 539), placeholder measures
   (`MonthlyGaslift = 1`), duplicate pages - evidence of no versioning/tests.
6. Identity is `Case_ID` + file name (`BD5_v183`), not a model fingerprint. Autogration has
   `task_id`, `assumption_group_id`, `run_number`, model revision - strictly better lineage.
7. Entity master data (well hierarchy, license, split factors) is engineer-owned reference data
   that Autogration does not have today. It must become a versioned **reference pack**.

## 2. Target architecture

One contract, three consumers:

```text
                      +-----------------------------+
 Autogration API ---> |  autogration-results kernel |  <--- CSV folder (PBI share layout)
 (task parquet)       |  (pure Python package)      |  <--- example data pack
                      |  contract | reference pack  |
                      |  derived  | measures        |
                      |  health   | view specs      |
                      |  render (Plotly JSON)       |
                      |  export (csv/xlsx/png/zip)  |
                      +--------------+--------------+
            +------------------------+-------------------------+
            v                        v                         v
   Engineer workbench        Autogration backend         MCP agent tools
   (detached, local)         /api/v1/results/*           (feature/mcp-agents)
   Streamlit viewer          + React /results section    read-only + view specs
```

Key decision: **dashboards are data (declarative view specs), measures are Python/SQL,
rendering is Plotly figure JSON produced by the kernel.** The engineer, the web app and the agent
all produce and consume the same YAML/JSON spec, so work done detached attaches with no rewrite.

### 2.1 Kernel package `autogration-results`

Pure Python, no FastAPI/Azure imports; DuckDB + PyArrow (+ Polars optional), Pydantic, Plotly,
XlsxWriter. `requires-python >=3.12` so the engineer can run it outside the Autogration 3.15 pin.

```text
autogration_results/
  contract.py      # canonical long-form ResultFrame + StudyManifest (study, cases, provenance)
  sources/
    autogration.py # list completed runs, group by assumption_group_id, read parquet (httpfs/HTTP)
    csv_folder.py  # adapter for the YGG_PowerBI_share layout (wide GAP CSV -> long form)
    fixture.py     # bundled example pack
  reference.py     # entity hierarchy, licenses/WI, split-factor sets, calendar, unit catalog
  derived.py       # ported calculated columns (SSF->MSS, NGL, GCV 40MJ, BOE, monthly volumes)
  measures/
    core.py        # measure types: sum, rate_weighted, ratio, calendar_rate, stream_rate,
                   # incremental(A,B), quantile(P10/P50/P90), first_n_months, first/last_date, count_if
    oilgas.py      # registry ported from the DAX (one golden test per measure)
  health.py        # sentinels, NaN/negatives, missing steps, failed cases, collapse/shut-in detection,
                   # constraint saturation, PE5/Turner/erosional flags
  views/
    spec.py        # Pydantic: Page -> Visual -> Query(measures, dims, filters, sort) + chart type
    render.py      # Query -> DuckDB SQL -> table -> Plotly figure JSON
  export.py        # CSV, XLSX (data + filters + provenance sheet), Parquet, PNG/SVG/PDF, report bundle zip
```

Canonical tables (DuckDB views): `fact_result` (long), `dim_case` (task/run/assumption values),
`dim_entity` (identifier -> type, field, group, segment, well, license, ...), `dim_calendar`,
`ref_factors`. Wide PBI-style frames are derived views, never the storage format.

### 2.2 View spec (the attach/detach contract)

```yaml
spec_version: 1
id: study-overview
title: Study overview
filters: [case, entity.field, entity.group, period, unit_system]
pages:
  - id: performance
    visuals:
      - kpi: {measure: sales_total_mmboe, compare_to: baseline_case}
      - chart: stacked_area
        measure: avg_sales_rate_boepd
        x: calendar.month
        color: entity.field
      - chart: line
        measure: oil_rate_sm3d
        x: calendar.month
        color: case
        band: {quantiles: [0.1, 0.5, 0.9]}
```

Specs are versioned and validated; a spec referencing an unknown measure fails CI, not at runtime.

### 2.3 Detached engineer workbench

New standalone uv project, e.g. `C:\Users\aleksekk\autogration_v2\results-workbench\` (own git repo,
later vendored as `autogration/shared/results` - the Autogration root is already a uv workspace
with `shared/*` members, so attaching is a one-line workspace change).

```text
results-workbench/
  src/autogration_results/   # kernel (above)
  dashboards/*.yaml          # homepages + engineer custom pages
  reference/                 # example reference pack (schema + anonymised sample)
  examples/                  # example data packs: Autogration fixture + synthetic GAP-like pack
  app/viewer.py              # Streamlit: pick data pack, edit YAML, live preview, export
  notebooks/                 # port/verify measures against PBI numbers
  tests/                     # golden measure tests, spec validation, export round trips
```

How the engineer works: point the viewer at either the share CSVs (local only), an exported
Autogration study bundle, or the example pack; edit `dashboards/*.yaml` or add a measure in
`measures/oilgas.py`; hand back via PR or a zip of specs. Real field data stays out of git;
only anonymised/synthetic packs are committed.

### 2.4 Autogration integration (after the kernel stabilises)

Backend `modules/results_explorer/` (read-only, user auth, existing parquet cache):

| Route | Purpose |
| --- | --- |
| `GET /results/studies` | completed runs grouped by `assumption_group_id`, newest first, status counts |
| `GET /results/studies/{id}/catalog` | variables, units, entities, cases, assumption axes |
| `GET /results/dashboards` / `{id}` | built-in + saved view specs |
| `POST /results/query` | spec query -> table (row-capped) |
| `POST /results/render` | spec -> Plotly figure JSON |
| `POST /results/export` | csv / xlsx / parquet / png / bundle |

Frontend `/results` section, Power BI-like navigation:

- left rail: study browser (auto-fetched completed studies, search, pin, recent);
- top tabs: homepages (Overview, Health, Compare, Uncertainty, Wells & Network, Facilities, Data);
- one global filter bar replacing per-page slicers; cross-filter and drill-through (case -> well -> step);
- visuals render kernel Plotly JSON (lazy-loaded route); tables with column picker and export menu;
- "Ask" side panel for the agent; every agent change is a visible, undoable spec diff.

Spike first: Plotly.js under the newly enforced CSP and bundle size; fallback is ECharts with the
same spec (only `render.py` changes).

### 2.5 Agent

Extend `feature/mcp-agents` with read-only results tools backed by the kernel:
`search_studies`, `get_study_catalog`, `query_results`, `compute_kpis`, `compare_cases`,
`run_health_checks`, `propose_view` (returns a validated spec), `save_view`, `export_view`.
Add `autogration-results-explorer` skill next to `autogration-results-duckdb`, with grounded examples.
The agent composes **specs, not code**: safe, reviewable, reproducible, exportable. Answers cite
task ids, `assumption_group_id`, run numbers and spec ids. No write tools to CDF or simulations.

## 3. Standard homepages

| Homepage | Question | Core content | PBI origin |
| --- | --- | --- | --- |
| Overview | How does this study perform? | KPI cards (sales MMBOE, cum oil/gas/water, plateau rate and length, end of life, well counts), stacked profile by field/group, net vs gross | Dashboard, Summary, RatesVolumes |
| Health | Did anything fail or collapse? | case status matrix, sentinel/NaN counts, sudden rate drops and shut-ins, constraint saturation, PE5/Turner/erosional flags, step runtime; each item drills to case/well/step | Well Stability, PE Analysis + new |
| Compare | Is A better than B, and why? | A/B picker (default: baseline vs best), delta KPIs, incremental profiles, waterfall by field/group/well, rank table of all cases | Compare*, Incremental, Waterfall* |
| Uncertainty | How wide is the outcome range, what drives it? | P10/P50/P90 fan, S-curve of KPI, tornado and scatter vs assumption axes | new (Autogration-native) |
| Wells & network | What is each well/group doing? | hierarchy explorer, tech profiles (rates, GOR, WCT, BHP/WHP/WHT, drawdown), PoP schedule, type curves | Tech Profiles, Wells, Drilling Schedule, TypeCurves |
| Facilities | Are separators/pipes within limits? | separator P/T and in/out rates, utilisation vs capacity, flow-assurance (velocity, regime, slugging) | Separators, FlowAssurance (unused today) |
| Data & export | Give me the numbers | pivot/table builder, unit system, CSV/XLSX/Parquet/PNG/bundle with provenance | Export, Export_TC, FMRA, PI Export |

## 4. Delivery phases

| Phase | Output | Exit check |
| --- | --- | --- |
| P0 Intake (now) | this plan; measure/page inventory exported from the PBIX | engineer confirms the 7 homepages and the top-20 measures |
| P1 Kernel + contract | contract, CSV-folder and Autogration adapters, reference pack schema, derived columns, top-20 measures | golden tests reproduce PBI values for 2 cases within rounding |
| P2 Detached workbench | specs, Plotly renderer, Streamlit viewer, exports, example packs | engineer edits a homepage spec and exports XLSX/PNG without help |
| P3 Health + Compare | health checks, incrementals, waterfalls, rank table | known-bad runs are flagged; A/B deltas match PBI Incremental page |
| P4 Attach to Autogration | `shared/results` workspace member, `/results/*` routes, React section on dev | runs on dev against real completed studies; nothing on test/prod |
| P5 Agent | MCP results tools + skill + eval questions | agent builds a correct Compare view from a natural-language request |
| P6 Uncertainty + saved views | fan/S-curve/tornado, per-user saved specs, sharing | engineer-approved; promote via normal dev -> test -> main flow |

## 5. Open questions for the engineer

1. Which 5-10 PBI pages are used weekly, and which are legacy?
2. Authoritative source of the well hierarchy, licenses and split-factor sets - and who owns updates?
3. Which "collapse" signals matter most (shut-in, non-convergence, constraint hit, rate cliff, stability flag)?
4. Default baseline for Compare (management case? latest approved?).
5. Required export formats for downstream tools (PI export layout, termsheet, FMRA)?
6. Units and conventions: SSF vs MSS default, BOE factor, 40 MJ basis, gross vs net.
7. Can an anonymised extract of 2-3 cases be committed as the example pack?
