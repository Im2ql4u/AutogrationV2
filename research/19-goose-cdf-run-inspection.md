# Goose, CDF, and Autogration Run Inspection

Status date: 2026-10-13

## Scope

This note covers the first requested direction only: inspect Aker BP Goose for
CDF retrieval, AI/tool coupling, and visualization patterns; compare those
patterns with Autogration's current result export; and exercise one existing
simulation result locally. Power BI model inspection and write-side run tagging
remain follow-up work.

Goose was fetched into the workspace at revision `3faf39a0808b6e531449a30080dba0c5e714e12a`
from <https://github.com/AkerBP/goose>.

## Main Finding

Goose is a strong reference architecture for a governed engineering assistant,
but it does not currently provide Autogration simulation-run discovery.
Its CDF tools retrieve known operational time-series external IDs. Autogration
needs a small read-only run catalog adapter before Goose-style agents can answer
questions such as "was this pipe or scenario studied before?"

The useful Goose pattern is:

```text
User question
  -> agent selects an authorized tool
  -> source policy and user-context CDF authentication
  -> bounded retrieval into a dataset_ref
  -> server-side SQL/profile or sandboxed Python
  -> governed plot/artifact with lineage
  -> answer citing source IDs and references
```

The unsafe alternative is to give an LLM an unrestricted Cognite client and ask
it to discover, load, and interpret arbitrary resources directly.

## What Goose Actually Provides

### CDF authentication

`services/query-engine/src/query_engine/cdf/auth.py` creates the Cognite client.
Local development uses cached interactive Microsoft Entra authentication.
Production and Kubernetes exchange a verified user bearer token through
on-behalf-of authentication. CDF therefore still enforces the user's own access;
Goose does not elevate it.

### CDF retrieval

`retrieve_cdf_time_series` supports:

- one or up to 20 time-series external IDs;
- metadata and latest values;
- bounded raw datapoint windows;
- CDF aggregates with a declared granularity;
- at most 10 preview rows visible to the model; and
- materialization of complete retrieved datapoints as a governed `dataset_ref`.

It does not expose a general CDF asset, file, relationship, data-model, or
Autogration ensemble search tool. Goose normally uses Enlight to translate
natural-language equipment descriptions into operational time-series external
IDs. That is useful for live signals but does not establish simulation-run
identity.

### Agent and analysis coupling

The default agent registers governed MCP tools rather than embedding source SDK
calls in prompts. The normal analysis flow is:

```text
session_start
  -> retrieve_cdf_time_series(..., session_ref=...)
  -> dataset_ref
  -> dataset_query / dataset_profile / dataset_summarize
  -> python_execute / plot_custom
  -> artifact_ref and lineage
```

The complete dataset stays behind a reference. Tiny previews are explicitly
prohibited as evidence for totals, distributions, or conclusions. Python runs
inside a restricted environment, and exports are checked against lineage and
policy.

### Visualization

Goose has two distinct visualization surfaces:

- governed agent plots use sandboxed Matplotlib and produce PNG artifacts;
- the React chat client includes Plotly rendering for supported payloads.

The governed sandbox explicitly rejects Plotly imports. Interactive engineering
plots should therefore live in a trusted frontend, notebook, or dedicated MCP
App. Agent-generated plots can remain static and governed unless an interactive
MCP App contract is implemented.

## What Autogration Already Exports

Autogration has enough identifiers to build a first run browser without changing
the simulator path.

Ensemble assets contain:

- `asset`;
- `creator`;
- `num_realizations`;
- `assumption_group_id`;
- `resource_type = Ensemble simulation`; and
- `source = Autogration`.

Every exported result time series contains:

- `task_id`;
- `realization`;
- `system_type`;
- `object_type`, `object`, and `label`;
- `parameter` and unit;
- `asset` and `ensemble`; and
- source/resource provenance.

Autogration also uploads result/config files and stores the CDF ensemble ID back
on the task. Its read-only API can list runs and return JSON or Parquet results.

## Demonstrated Simulation Fetch

[The executable notebook](19-autogration-run-inspection.ipynb) tries the local
completed-run API first, then explicitly falls back to the checked-in exported
RESOLVE result fixture when the stack is unavailable.

The validated fixture result contains:

- one task, realization, production system, and equipment object;
- 18 result series;
- 882 monthly datapoints from 2025-01-01 through 2029-01-01;
- no null values, duplicate series/timestamp pairs, missing identities, or
  missing units;
- oil rate declining from 4,999.9 to 126.663 Sm3/day;
- water cut rising from 0 to 90.799%; and
- cumulative oil reaching 2.046 MSm3.

The notebook includes a full-series summary and a Plotly.js selector with hover,
zoom, range selection, units, task ID, realization, and CDF-shaped series ID.
It uses an existing simulation result, not generated sample data.

A live run could not be fetched in this session: PostgreSQL was not listening,
and the shell has no Docker command. CDF authentication and current CDF contents
were therefore not claimed or tested.

## Required Autogration Adapter

Add read-only, governed tools in this order:

1. `search_autogration_runs`: filter ensemble assets by asset, date, creator,
   assumption group, run status/type, model, case, scenario, and free text.
2. `get_autogration_run`: return compact run metadata, task provenance,
   assumptions, available result variables, files, and CDF links.
3. `materialize_autogration_results`: select variables and bounded windows, then
   return a long-form `dataset_ref` compatible with Goose analysis tools.
4. `compare_autogration_runs`: align selected compatible series and calculate
   reviewed KPIs/differences without moving full datasets into model context.

The agent should cite task IDs, ensemble IDs, realization IDs, series external
IDs, and result/file references in every answer. It should separate observed
results from interpretation and state when units, model versions, or scenarios
are not comparable.

## Metadata Gaps Before Similar-Run Search

Current CDF metadata is sufficient for exact task/ensemble lookup but not for
reliable semantic reuse. Add a versioned run manifest before automated tagging:

- `study_id` and `study_revision`;
- controlled `run_type` such as forecast, sensitivity, scenario, validation,
  troubleshooting, optimization, or decision support;
- decision question/objective;
- model family, immutable model revision, and model fingerprint;
- engine and engine version;
- canonical input/assumption fingerprint;
- named case and scenario IDs;
- affected assets, wells, pipes, and facilities using stable identifiers;
- start, finish, status, quality state, and failure taxonomy;
- output/KPI contract version; and
- classification source, confidence, reviewer, and timestamp.

Do not infer exact equivalence from shared tags. Exact result reuse requires the
complete compatible fingerprint. Similarity is advisory evidence and must show
which fields matched and differed.

## Power BI Intake

When the Power BI setup arrives, inspect it before designing a replacement UI:

1. Obtain an approved `.pbip`, `.pbit`, semantic-model export, or documented API
   view; do not reverse engineer protected credentials.
2. Inventory source queries and Power Query transformations.
3. Extract tables, keys, relationships, date tables, hierarchies, measures,
   calculation groups, units, and row-level security.
4. Record report filters, drill-through paths, bookmarks, and the questions each
   page answers.
5. Reconcile every Power BI run/case/scenario concept to Autogration task and CDF
   identifiers.
6. Validate important measures against raw exported series before reusing their
   interpretation in an agent.

The first deliverable should be a concept and measure map, not another dashboard.
It will reveal whether Power BI already contains the missing run taxonomy or
only presentation labels.

## Recommended Sequence

1. Restore the local services or obtain approved read-only CDF access and fetch
   one current ensemble end to end.
2. Inspect the Power BI semantic model and reconcile identifiers/measures.
3. Implement the read-only run catalog and result materialization tools.
4. Add standardized summary, forecast, comparison, sensitivity, quality, and
   provenance views.
5. Add agent skills with grounded examples and evaluation questions.
6. Only then inventory historical runs, propose tags/links, review them with
   engineers, and generate dry-run CDF write payloads before any mutation.
