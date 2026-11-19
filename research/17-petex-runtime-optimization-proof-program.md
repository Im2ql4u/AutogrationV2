# PETEX Runtime Optimization Proof Program

Status: proposed investigation and product-integration design, 2026-09-10.
No simulation, benchmark, PETEX-setting change, or product implementation has
been executed under this plan. It explains how to establish viable runtime
improvements before using them in ordinary Autogration studies.

## Purpose

Runtime optimization should be the first focused technical program beneath the
long-term Autogration north star. It is valuable immediately, creates the
observability and validation machinery required by later multifidelity work,
and can reveal whether the best investment is in PETEX configuration, model
formulation, task lifecycle, PVT, study design, infrastructure, or a different
physics representation.

The objective is not to reproduce a marketing speedup. It is:

> Reduce time-to-trusted-result for representative Autogration studies while
> preserving their declared physical, operational, and decision contract.

This has three distinct performance outcomes:

1. **Latency:** one case or one study finishes sooner.
2. **Throughput:** more accepted cases finish per unit of wall time, licence,
   or compute capacity.
3. **Useful computation:** fewer calculations are required to reach the same
   accepted engineering conclusion.

These must not be collapsed into one speedup number. Ten parallel cases can
improve throughput without making a case faster. A faster approximate PVT model
can reduce latency while changing the result. A better study design can reduce
the case count while leaving each case unchanged.

## Current Evidence And Its Limits

### Verified Autogration facts

The reviewed execution path establishes that:

- the frontend expands assumptions into a Cartesian `ComputeSet`;
- the backend creates one PETEX compute task per `AssumptionSet`;
- the node client downloads the model and data, applies allowlisted OpenServer
  settings and model changes, saves and validates the linked model, repeatedly
  calls `RESOLVE.RUNONESTEP()`, and extracts scenario results;
- existing tasks record lifecycle timestamps; and
- the active RESOLVE loop logs step number and simulation date but does not
  record a durable wall-time decomposition, memory/CPU use, or internal solver
  evaluation and convergence counts.

This gives Autogration an excellent external measurement boundary but not
automatic access to PETEX internals.

### Current official PETEX evidence

Current official PETEX pages state that:

- GAP uses a proprietary equation-based steady-state solver that balances
  pressure, flow, and temperature across integrated networks;
- GAP supports nonlinear optimization and both compositional and black-oil PVT
  descriptions;
- RESOLVE exposes reusable Data Objects;
- RESOLVE performs multilevel global optimization using linear, nonlinear, and
  routing algorithms;
- RESOLVE supports advanced PVT lumping and delumping across connected
  applications;
- RESOLVE supports parallel scenario/probabilistic workflows; and
- RESOLVE advertises clustering and hyperthreading for multi-core and
  distributed execution.

These are capability statements. They do not document cache invalidation,
specific OpenServer tags, the scope of parallel execution, whether Jacobian
columns are parallelized in our GAP version, expected scaling, or whether the
features are licensed and configured in our environment.

### Historical PETEX performance evidence

The removed runtime case study and surviving search-index fragments point to a
stack of interventions:

- parallel Jacobian construction;
- PVT simplification or lumping;
- reuse of Data Objects;
- relocation of separator-related work from a frequently repeated path; and
- model or optimization reformulation.

Fragments support portions of a timing story involving `344`, `17.8`, and
`10.5` seconds and a roughly `3.5` minute optimization. The full timing chain,
the reported `3.7` second endpoint, hardware, model, software version, and
meaning of `0.5%` have not been independently recovered.

Therefore the mechanisms are strong investigation leads, but neither their
individual contribution nor their cumulative result is an acceptance target.

### WhitsonPVT evidence

The public WhitsonPVT manual documents detailed parent fluid models and child
black-oil/lumped-EOS workflows. Its black-oil method fixes reservoir
temperature and surface process and documents difficult critical,
extrapolation, closure, and non-monotonic cases. This supports a controlled
child-model experiment; it also demonstrates why black oil is not a universal
drop-in acceleration.

The public API page proves that an OAuth API can be provisioned and illustrates
one project-scoped wells read. Other endpoints and exports are client-specific.
No live inner-loop integration should be designed around unverified endpoints.

## The Runtime Model We Need To Measure

End-to-end task time should initially be decomposed as:

$$
T_{task} = T_{queue} + T_{download} + T_{open} + T_{mutate} +
T_{save/validate} + \sum_{k=1}^{N_{steps}} T_{step,k} +
T_{extract} + T_{upload} + T_{teardown}.
$$

Within one RESOLVE step, the conceptual cost is:

$$
T_{step} = T_{reservoir} + N_{GAP}T_{GAP} + T_{coupling} +
T_{optimisation} + T_{workflow}.
$$

A GAP calculation can conceptually contain:

$$
T_{GAP} = T_{residual/closure} + T_{Jacobian} + T_{linear} +
T_{globalisation} + T_{controls}.
$$

Autogration can measure the first equation around its own boundaries. It can
split the second and third equations only when PETEX exposes supported counters,
logs, commands, or timing data. A whole `RUNONESTEP` duration is still a valid
measured bucket; it must not be relabelled as reservoir, GAP, or PVT time based
on intuition.

### Amdahl's law as a prioritization check

If a fraction $f$ of runtime is improved by a factor $s$, the maximum task
speedup is:

$$
S = \frac{1}{(1-f) + f/s}.
$$

If PVT accounts for 10% of measured runtime, even eliminating it entirely can
produce at most $1/(0.9)=1.11\times$ task speedup. If repeated GAP work accounts
for 90%, a tenfold improvement there could produce
$1/(0.1+0.9/10)=5.26\times$.

This simple bound should reject attractive projects that cannot materially
change end-to-end time even under impossible best-case assumptions.

## PETEX-Like Optimization Mechanisms

### 1. Parallel Jacobian construction

For residual equations $F(x)=0$, a finite-difference Jacobian column may require
perturbed physical evaluations:

$$
J_{:,j} \approx \frac{F(x+h_je_j)-F(x-h_je_j)}{2h_j}.
$$

When many columns invoke expensive multiphase pipeline or PVT calculations,
independent derivative work can be parallelized. The historical PETEX material
described a dense Jacobian and parallel construction as material in one model.

**What is established:** current RESOLVE advertises multi-core, hyperthreaded,
and distributed acceleration; the historical case pointed specifically to
parallel Jacobian construction.

**What is unknown:** the supported setting, licence, GAP version, scheduling
scope, core scaling, reproducibility, and whether it applies to our models.

**Autogration's role:** record host/core/licence context, request only a
PETEX-supported profile, compare fixed-core variants, and show scaling and
quality evidence. Autogration should not attempt to implement or intercept
GAP's proprietary Jacobian.

**Disproof:** the measured `RUNONESTEP`/GAP-dominated span does not improve, CPU
or licence contention offsets the gain, or outcomes/failures become unstable.

### 2. PVT simplification, lumping, and delumping

A compositional flash and its derivatives become more expensive as the
component representation and number of evaluated states grow. A validated
lumped EOS or black-oil table may make each network/well evaluation cheaper.
RESOLVE officially describes PVT lumping/delumping for thermodynamic
consistency between connected applications; GAP officially supports
compositional and black-oil descriptions.

**What is established:** the product family supports these representations and
WhitsonPVT can create child-model candidates with documented assumptions.

**What is unknown:** the PVT share of runtime, the exact representation used by
each linked module, conversion/import path, and error over the actual
pressure-temperature-composition trajectory.

**Autogration's role:** fingerprint the parent and child model, preserve the
component map and generation conditions, run property compatibility before
integrated comparison, and restrict an approved child model to its validated
envelope.

**Required comparison ladder:** composition mapping; saturation pressure;
density, viscosity, and phase split; table continuity; one-well response; small
network response; full integrated central/extreme/event cases.

**Disproof:** there is no material runtime saving, the operating path leaves the
child-model envelope, or phase/constraint/decision results change beyond the
declared contract.

### 3. Reusable RESOLVE Data Objects

Current RESOLVE material explicitly calls Data Objects reusable engineering
functionality for PVT, wells, transient flow, probabilistic analysis, and smart
wells. Reuse could avoid rebuilding or reevaluating unchanged responses inside
a workflow.

**What is not established:** that a Data Object is a memoization cache, what
persists across timesteps or tasks, which dependencies invalidate it, and
whether arbitrary existing linked models can adopt it without reformulation.

**Autogration's role:** identify a PETEX-supported object and its complete
inputs, treat its definition or exported response as a versioned dependency,
and compare explicit fresh versus supported reused execution. Never reuse it
solely because two objects have the same display name.

**Disproof:** hidden state or dependencies produce order-sensitive results,
reuse does not survive the intended lifecycle, or validation costs consume the
saving.

### 4. Move invariant separator or property work out of hot loops

The historical evidence suggests that separator-related work was relocated.
The general optimization is loop-invariant code motion: calculate a quantity
once rather than during every residual, derivative, coupling, or optimizer
evaluation.

It is valid only if the quantity's complete dependency set is unchanged. A
separator result may depend on inlet composition, pressure, temperature,
surface process, routing, recycle, and control state. Those values may change
at every step or optimizer trial.

**Autogration's role:** help quantify invocation counts and preserve model
variant identity and comparison results. The formulation change itself belongs
to PETEX model/workflow engineering, not an automatic Autogration rewrite.

**Disproof:** dependency perturbations change the supposedly invariant result,
or a schedule/control event invalidates it without recomputation.

### 5. Reformulate optimization and coupling

The historical example and current RESOLVE description indicate that an outer
optimization can amplify a 10-second calculation into minutes. Possible
mechanisms include fewer decision variables, staged discrete and continuous
choices, less frequent optimization, warm starts, response-assisted candidate
search, and removal of redundant calculations from the objective/constraint
path.

**What is established:** RESOLVE coordinates linear, nonlinear, and routing
algorithms; current Autogration exposes selected optimizer and timestep
settings through allowlisted definitions.

**What is unknown:** the active algorithm, evaluation count, active constraints,
warm-start behavior, and permitted reformulations for each model.

**Autogration's role:** freeze the optimization question and constraints,
record exposed settings and evaluation counts where available, compare
candidate profiles, and reject any profile that changes the feasible set or
accepted optimum materially.

**Disproof:** a faster profile misses a feasible solution, changes routing or a
binding constraint, becomes initialization-sensitive, or saves little outside
the demonstration case.

## Additional Viable Optimization Families

### A. Exact run avoidance

- Canonicalize typed assumptions and settings.
- Remove exact duplicates.
- Suppress engineer-approved inactive combinations.
- Reuse a prior result only when the full model/data/PVT/settings/engine/output
  fingerprint matches.

This changes useful study time without changing PETEX execution. It should be
reported separately from per-case acceleration.

### B. OpenServer and application lifecycle

- Measure download, application startup, model open, mutation, save,
  validation, extraction, upload, and teardown separately.
- Batch supported settings and result requests when semantics are unchanged.
- Avoid extracting the full discoverable tree when a declared output contract
  needs a smaller set, while preserving existing legacy behavior.
- Test supported application/session reuse only with explicit state-reset and
  cross-case contamination checks.

Session reuse can be powerful for short cases, but it creates a serious risk:
case $B$ may inherit state from case $A$. A random-order equivalence test and
periodic clean-session control are mandatory.

### C. Timestep, event, restart, and continuation policy

Fewer or larger timesteps can reduce calls; smaller timesteps can sometimes
avoid convergence failure and retries. Warm/restart states may accelerate
nearby cases. These are physical/numerical policy changes, not free operational
optimizations.

Test timestep sequences, event alignment, accumulated volumes, constraint
crossings, and retry/failure rates. Do not compare only final rate or end date.

### D. Approved well and equipment responses

PROSPER IPR/VLP or equipment response artifacts may replace repeated detailed
calculations in a declared range. Record all inputs affecting the response,
interpolation method, domain, units, source model/version, and error evidence.

This is a precursor to the later fidelity ladder, but a narrow response may be
a practical near-term PETEX optimization if it is already supported by the
model.

### E. Case-level parallelism and infrastructure

One task per `AssumptionSet` creates natural case-level parallelism. Measure:

- queue and licence wait;
- worker startup and model transfer;
- throughput at controlled concurrency levels;
- CPU, memory, disk, and shared-storage contention;
- retry and failure rates; and
- accepted cases per licence-hour and compute-hour.

Do not report a 10-worker batch as a `10x` solver speedup. Report wall-clock
study throughput and resource efficiency.

### F. Result extraction and persistence

Large recursive OpenServer discovery and result export can dominate short
calculations. A versioned output contract can request only the variables needed
by a study, while a full extraction remains available for registration,
diagnostics, or legacy callers.

The experiment must prove that the reduced extraction contains every required
KPI, quality signal, and audit dependency.

### G. Study design after per-case evidence exists

DOE, screening, common samples, and adaptive selection reduce the number of
full cases. They should use the same runtime cost model and accepted runtime
profiles, but remain a separate scientific claim. A faster study due to fewer
cases must show that omitted cases do not change its declared conclusion.

## Autogration Integration Architecture

The performance capability should be a set of evidence objects around the
existing task path, not a forked PETEX executor.

```text
BenchmarkSuiteRevision
  -> AcceptanceContract
  -> RuntimeExperimentRevision
      -> baseline RuntimeVariant
      -> candidate RuntimeVariant(s)
          -> ordinary PETEX tasks
              -> PerformanceTrace
              -> engineering outcomes and quality
          -> ComparisonEvidence
      -> optional approved RuntimeProfileCertificate
```

### 1. `PerformanceTrace`

A versioned trace should contain immutable span/event records plus a compact
summary. Minimum fields:

| Field | Purpose |
| --- | --- |
| Schema version and trace ID | Permit evolution and stable reference |
| Task, case, parent, worker, and correlation IDs | Connect backend, node, and artifacts |
| Monotonic start/end/duration | Correct elapsed timing despite clock changes |
| UTC wall timestamps | Cross-service investigation and ordering |
| Span name and parent span ID | Represent queue, transfer, setup, step, extraction, and upload nesting |
| Simulation step and start/end simulation dates | Relate cost to physical progression |
| Command category | Distinguish supported lifecycle commands without logging secrets or every value |
| Success, cancellation, warning, and failure state | Prevent failed fast runs appearing favorable |
| Host/core/memory and PETEX version when observable | Explain environment differences |
| Exposed PETEX counts/diagnostics | Store facts; use `unavailable` rather than estimates |

Initial spans should be coarse and low overhead:

```text
queue
download-model-data
open-application-model
apply-model-and-settings
save-resolve
validate-gap
resolve-run-one-step[n]
declared-result-commands[n]
extract-results
upload-finalize
```

Do not initially trace every `DoGet` and `DoSet`. A command-level diagnostic
mode can be enabled for a short approved experiment because detailed tracing
may perturb COM/OpenServer performance and create large sensitive logs.

Use a monotonic high-resolution timer in the node process. Buffer trace events
locally and upload them in batches or with the final artifact; synchronous
network writes inside `RUNONESTEP` would contaminate the measurement.

### 2. `BenchmarkSuiteRevision`

This freezes the representative cases and why they exist. Each case records:

- immutable case/model/data/PVT/settings/output fingerprints;
- classification: typical, slow/convergence-heavy, PVT/network-different,
  constraint-sensitive, event-sensitive, or synthetic;
- declared cold/warm lifecycle;
- expected successful behavior and known warnings;
- required outputs and hard constraints; and
- data-handling and licence boundary.

Changing any case or required output creates a new revision. A convenient newer
model must not silently replace the slow reference case.

### 3. `RuntimeExperimentRevision`

An experiment records before execution:

- hypothesis and mechanism;
- baseline and candidate variants;
- exact changed fields;
- unchanged fields and environment controls;
- execution order/randomization and repetition rule;
- trace level;
- performance and engineering metrics;
- acceptance, rejection, and inconclusive rules;
- owner and required reviewers; and
- vendor source or approved engineering rationale.

Once the first task is admitted, the revision is immutable. A correction creates
a new revision rather than changing the target after seeing results.

### 4. `RuntimeVariant`

A variant is not an arbitrary settings bag. It can contain:

- an approved RESOLVE settings set from the existing definition catalog;
- approved module settings or workflow/model artifact revision;
- PVT materialization identity;
- worker/core/concurrency profile;
- lifecycle policy such as cold start or supported reuse; and
- output/extraction contract.

Every difference from baseline must be machine-readable. PETEX settings absent
from official licensed documentation must not be guessed and added to the
allowlist.

### 5. `AcceptanceContract`

The contract has two layers.

**Universal execution checks:** terminal success, required steps and outputs,
no unexplained new errors, trace completeness, and fingerprint compatibility.

**Case-specific engineering checks:** material/pressure balance when exposed,
phase state, timestep/event sequence, cumulative and peak rates, well/facility
constraints, routing/control state, integrity limits, and decision KPIs.

Hard constraints use no-cross rules. Continuous quantities use units, absolute
and relative tolerances, and a denominator floor. Time series specify alignment
and integration rules. Engineers own the tolerances; Autogration owns their
versioning and enforcement.

### 6. `ComparisonEvidence`

Comparison is an append-only result linking one candidate to the exact
baseline. It contains:

- per-case paired runtime distributions;
- cold/warm and queue/execution breakdowns;
- lower/central/upper speedup estimates;
- resource and licence efficiency;
- outcome deltas and constraint/phase/control changes;
- failures, exclusions, and missing telemetry;
- PASS, FAIL, or INCONCLUSIVE per criterion; and
- the overall result without averaging away a failed hard gate.

### 7. `RuntimeProfileCertificate`

An accepted experiment does not immediately become a global default. A
certificate binds an approved runtime profile to:

- benchmark-suite revision;
- compatible model family and model fingerprint rules;
- PETEX and adapter versions;
- PVT/materialization requirements;
- hardware/licence profile;
- output contract;
- validity conditions and prohibited regimes;
- acceptance evidence and reviewers;
- expiration/review policy; and
- automatic invalidation dependencies.

A changed PETEX version, model structure, PVT model, optimization question, or
required output can invalidate the certificate. Rollback means selecting the
baseline profile; no model repair should be required.

## Ownership In The Existing Codebase

This is a proposed placement, not an implemented schema.

| Concern | Natural owning surface | Reason |
| --- | --- | --- |
| Case generation and preview | Frontend simulation study surface | Show cases and expected cost; do not decide scientific acceptance in the browser |
| Immutable experiment, suite, contract, and certificate | Backend study/task domain | Central authorization, identity, persistence, and audit |
| Settings/type validation | Existing shared RESOLVE/module definition catalogs | Preserve allowlists and typed coercion |
| Queue/staging timestamps | Backend task/events and worker assignment | These stages exist outside the PETEX process |
| OpenServer lifecycle and step spans | Node-client base and PETEX executor | This process owns model open, settings, validation, `RUNONESTEP`, and extraction |
| Exposed PETEX diagnostics | Node-client IPM/OpenServer adapter | Keep proprietary-engine details behind the adapter |
| Outcome comparison | Backend comparison service | One deterministic implementation for UI, export, and audit |
| Runtime-profile approval | Backend gated workflow | Separate evidence and engineering authorization from ordinary task launch |
| Trace/result display | Study/task detail UI | Explain where time went and why a candidate passed or failed |

All new task links should initially be optional. The current PETEX start API and
ordinary task execution should continue to work without an experiment. Trace
collection can be feature-flagged and additive. This lets Phase 1 measure the
existing path before changing it.

### Concrete seams in the reviewed implementation

The following are the narrowest current attachment points. They are not a
commitment to these exact schemas, but they avoid inventing a second execution
path.

| Existing surface | Verified role | Proposed additive responsibility |
| --- | --- | --- |
| [`buildComputeSet`](../../autogration_frontend/frontend/src/utils/ass.ts) | Expands frontend selections into a Cartesian `ComputeSet` | Later preview experiment/study identity and estimated cost; do not calculate authoritative acceptance in the browser |
| [`prepare_petex_compute`](../../autogration/apps/backend/backend/modules/tasks/service/prepare_tasks/petex.py) | Creates one ordinary PETEX task per assumption set and archives its files | Attach optional immutable experiment/variant/case links and preserve existing task creation behavior |
| [`ComputeSet` and `AssumptionSet`](../../autogration/shared/models/models/assumptions.py) | Carry current case inputs and model operations | Keep legacy payloads compatible; put durable experiment definitions in a separate backend domain rather than turning every task payload into a benchmark |
| [`RESOLVE_SETTING_DEFINITIONS`](../../autogration/shared/models/models/resolve_settings.py) | Provides typed, allowlisted RESOLVE settings | Admit only documented candidate settings and distinguish approved runtime profiles from ordinary overrides |
| [`execute_task`](../../autogration/apps/nodeclient/nodeclient/task_execution/base.py) | Owns model/data download, retry, and OpenServer execution lifecycle | Emit transfer, attempt, retry, and top-level execution spans with one trace correlation ID |
| [`execute_petex_task` and `_run_resolve_step`](../../autogration/apps/nodeclient/nodeclient/task_execution/petex.py) | Apply changes, save/validate, loop through `RUNONESTEP`, and collect step results | Emit save, validation, step, command-result, and error spans around unchanged calls |
| [`OpenServer`](../../autogration/apps/nodeclient/nodeclient/openserver/openserver.py) | Wraps blocking `DoCmd`, `DoGet`, and `DoSet` calls | Offer optional category-level diagnostic timing behind the adapter; do not log model values or enable it by default |
| [`execute_extraction_task`](../../autogration/apps/nodeclient/nodeclient/task_execution/extraction.py) | Discovers and assembles final model/scenario results | Measure extraction separately and later honor an approved output contract without breaking full legacy extraction |
| [`Task`, task failures, and node logs](../../autogration/shared/models/models/backend/tasks.py) | Preserve task lifecycle, attempts, timestamps, failure, and worker context | Link append-only trace artifacts and comparison evidence; keep existing task fields/API behavior optional and backward compatible |

The first implementation should wrap these boundaries, not move them. In
particular, `RUNONESTEP` remains the execution command, the existing setting
catalog remains the allowlist, and ordinary task/result persistence remains the
source of task truth.

## Proof Protocol

### Define two kinds of equivalence

1. **Exact-preserving change:** lifecycle batching, tracing, or task scheduling
   is expected to leave PETEX inputs and outputs identical under their normal
   serialization precision.
2. **Engineering-equivalent change:** PVT, timestep, response, tolerance, or
   formulation changes are approximate and must satisfy an engineer-owned
   acceptance contract.

An approximate change must never inherit the label or cache semantics of an
exact change.

### Control runtime noise

- Separate queue time, cold startup, model setup, simulation, extraction, and
  teardown.
- Keep model, data, PETEX version, worker class, core allocation, licence
  context, output contract, and background-load policy fixed within a paired
  comparison.
- Define cold-start and warm-start experiments separately.
- Use randomized paired blocks: run baseline/candidate in randomized `AB` or
  `BA` order on the same controlled worker context.
- Include an explicit warm-up only when the measured lifecycle excludes cold
  startup; never discard a slow first run without naming the reason.
- Start with at least ten measured pairs per reference case, then continue
  until the agreed precision or budget stop rule is met. The final requirement
  is interval precision, not a ritual fixed sample count.
- Report median and tail runtime, paired speedup ratios, and a bootstrap 95%
  confidence interval. Do not treat hundreds of timesteps from one task as
  independent task replicates.
- Investigate order effects, throttling, licence waits, retries, and outliers;
  do not silently delete them.

Across heterogeneous cases, report each case separately. A weighted geometric
mean speedup may summarize the suite only when the weights represent the
declared workload. Always retain the worst accepted case and failure-rate
change.

### Performance acceptance

Before execution, declare the minimum useful gain. For example, a candidate
might require the lower confidence bound on paired execution speedup to exceed
`1.10x`, with no increase in failure rate. The number is a program decision,
not a universal recommendation.

Tracing itself receives an overhead experiment. The passive trace should have
an agreed small overhead ceiling; detailed diagnostic tracing can exceed that
ceiling only when its measurements are not used as production runtime evidence.

### Engineering acceptance

At minimum compare:

- completed schedule and timestep/event sequence;
- solver status, warnings, and retry behavior;
- phase regime and phase transitions;
- pressure, temperature, rates, and cumulative volumes at declared locations;
- well, network, separator, compressor, water/gas handling, routing, and
  integrity constraints;
- material/pressure balances when exposed;
- objective and feasible-control result for optimization; and
- study-specific decision KPIs.

A candidate fails if a hard constraint or feasible decision changes outside
the contract, even when mean field rate differs by less than a small
percentage. There is no inherited `0.5%` rule.

### Classify the result honestly

- **PASS:** performance criterion and every engineering hard gate pass.
- **FAIL:** any hard gate fails or the measured performance is materially worse.
- **INCONCLUSIVE:** telemetry, statistical precision, comparability, or
  engineering evidence is insufficient.

Inconclusive is not a soft pass. It identifies the next measurement needed.

## Phase 1: Several Viable Ways To Begin

The first phase should not be one large instrumentation project. These options
can be combined deliberately.

### Option A: Minimal external timer

Add durations around existing task lifecycle and `RUNONESTEP` calls, retain the
current logs, and produce a simple per-task report.

**Advantages:** smallest code surface, low overhead, quickly establishes step
cost distribution and operational overhead.

**Limitations:** cannot distinguish GAP, reservoir, coupling, optimization, or
PVT inside the black-box step; insufficient for many PETEX-like mechanisms.

**Use:** minimum fallback if schema or vendor work is delayed.

### Option B: Structured passive trace

Implement the coarse span model described above across backend and node-client
boundaries, with immutable environment/fingerprint context and a declared
output contract.

**Advantages:** durable foundation for all later experiments, compatible with
ordinary tasks, enough to prioritize lifecycle versus step work.

**Limitations:** still needs PETEX-supported diagnostics for internal
attribution.

**Use:** recommended Autogration-owned Phase 1 core.

### Option C: Temporary detailed OpenServer diagnostic trace

In an approved non-sensitive benchmark mode, count and time command categories
and selected reads, without persisting sensitive values.

**Advantages:** can expose repeated external calls, extraction cost, setting
traffic, and workflow patterns.

**Limitations:** higher overhead and volume; external commands still do not
reveal calculations internal to one PETEX command.

**Use:** short diagnostic campaigns after Option B, never the default tracer.

### Option D: PETEX-supported internal telemetry

Work with PETEX support and licensed manuals to expose documented application
timings, calculation/evaluation counts, convergence data, clustering settings,
and Data Object lifecycle behavior.

**Advantages:** best route to proving the historical mechanisms and assigning
time within `RUNONESTEP`.

**Limitations:** vendor/licence/version dependent; may expose only some modules.

**Use:** run in parallel with Option B. Autogration must tolerate unavailable
fields.

### Option E: Model/workflow instrumentation

Add approved counters/timestamps to a copied reference RESOLVE workflow or
model to count Data Object, separator, GAP, reservoir, and optimizer activity.

**Advantages:** can answer model-specific repeated-work questions when generic
telemetry is absent.

**Limitations:** changes the model, may perturb runtime, and cannot be assumed
portable. Requires PETEX/model engineering ownership.

**Use:** targeted fallback for unresolved high-value hypotheses.

### Recommended Phase 1 combination

Use **Option B plus Option D** as the main program. Use Option A only as an
early subset of B, Option C for brief diagnostics, and Option E only where the
remaining black box prevents a material decision.

This combination is viable because Autogration can build the external evidence
contract independently while PETEX support supplies only documented optional
details. It does not block all measurement on vendor access and does not pretend
external timing proves internal causality.

## Phase 1 Work Packages

### WP0: Freeze the question and governance

Before implementation or runs:

1. Name a runtime-program owner, PETEX/model engineer, operations owner, and
   reviewers.
2. Select candidate reference studies and their data boundary.
3. Define exact versus engineering-equivalent change classes.
4. Declare required outputs, constraints, and comparison conventions.
5. Request the removed case study, licensed manuals, release notes, supported
   performance tags, and licence/HPC guidance from PETEX.
6. Inventory the installed PETEX/OpenServer versions and available licences
   when execution is authorized.

**Deliverable:** approved measurement and access charter.

### WP1: Define the reference benchmark suite

Choose at least:

- a typical successful forecast;
- a slow or convergence-heavy forecast;
- a materially different PVT/network case;
- a constraint- or event-sensitive case; and
- later, a transparent synthetic case for instrumentation checks.

Freeze complete input and output identity and document why each case matters.
Do not begin with only the most favorable model.

**Deliverable:** immutable `BenchmarkSuiteRevision` and
`AcceptanceContract` specifications.

### WP2: Specify and build passive observability

Design the versioned trace schema, event names, retention, redaction, and
summary calculations. Add coarse spans to the existing execution path without
changing model settings or run semantics. Add trace completeness and overhead
tests before trusting benchmark numbers.

**Deliverable:** feature-flagged trace artifact and per-task runtime breakdown.

### WP3: Establish baseline behavior

When runs are authorized, execute the paired/repeated baseline campaign across
the reference suite. Characterize cold and warm behavior, run-to-run variation,
step-cost distribution, queue/licence wait, failures, and trace overhead.

**Exit gate:** enough end-to-end time is assigned to measured external spans to
distinguish lifecycle, simulation-step, extraction, and operational bottlenecks.
Internal `RUNONESTEP` cost may remain explicitly unattributed.

### WP4: Complete the PETEX capability matrix

For the installed versions, record documented support and observed availability
for:

- clustering/hyperthreading and its scope;
- scenario versus inner-calculation parallelism;
- Data Object definitions, persistence, and dependencies;
- PVT lumping/delumping and accepted materializations;
- pre-calculated well/network responses;
- optimizer/coupling/timestep controls and diagnostics;
- restart, warm start, and continuation;
- application/session lifecycle; and
- exposed timings, evaluation counts, and convergence signals.

Each row must be `supported`, `unsupported`, `unavailable`, or `unknown`, with a
source. Marketing capability alone is not `supported in our environment`.

**Deliverable:** versioned PETEX capability and evidence matrix.

### WP5: Rank the first mechanism experiments

Use measured fractions and Amdahl bounds. Prefer experiments that are:

- supported and reversible;
- high potential according to measured runtime share;
- narrow enough for one-factor attribution;
- low risk to engineering equivalence; and
- reusable across reference models.

**Deliverable:** approved experiment queue, not a settings backlog.

## Later Experimental Sequence

Once Phase 1 closes, candidate experiments should normally proceed from least
semantic risk to greatest:

1. Trace and instrumentation overhead control.
2. Output/extraction contract and OpenServer batching.
3. Case-level concurrency under licence/resource control.
4. Supported lifecycle/session/Data Object reuse with contamination tests.
5. Supported core/cluster/hyperthread profiles.
6. Pre-calculated well or equipment responses.
7. Timestep/restart/continuation profiles.
8. Optimizer/coupling cadence and formulation.
9. PVT lumped EOS or black-oil child model.
10. Model/workflow refactoring that relocates invariant calculations.

The measured bottleneck can reorder this sequence. A reservoir-dominated case
should not wait behind an elaborate GAP PVT experiment simply because the
historical vendor example used one.

### Test one factor, then test the stack

First isolate mechanisms. Then test combinations because speedups do not
necessarily multiply:

$$
S_{A+B} \neq S_A S_B.
$$

Two changes may remove the same work, compete for cores, alter convergence, or
invalidate each other's assumptions. Preserve every cumulative variant and
report its incremental gain over the preceding accepted variant as well as the
original baseline.

## Product Promotion Path

Optimization should move through explicit modes:

```text
documented hypothesis
  -> benchmark experiment
  -> accepted comparison evidence
  -> shadow profile on selected studies
  -> engineer-approved model-family certificate
  -> opt-in ordinary execution
  -> possible default after operational evidence
```

### Shadow mode

Shadow mode runs the candidate only on approved duplicate/reference work and
does not control a production decision. It checks different run order,
operators, workers, schedule periods, and model revisions. Failures revoke or
narrow the proposed certificate.

### Opt-in before default

The first product surface should display:

- baseline and candidate profile identity;
- expected versus observed saving;
- exact or approximate classification;
- validity and invalidation conditions;
- required confirmation runs;
- comparison evidence and approvers; and
- a one-action fallback to baseline.

No optimization profile should be hidden in infrastructure defaults or silently
applied because it was fast on another asset.

### Automatic invalidation

Invalidate or require review when any certificate dependency changes, including:

- model topology or linked-module set;
- PETEX/OpenServer/adapter version;
- PVT source, component map, or child materialization;
- RESOLVE schedule, objective, controls, constraints, or required outputs;
- worker/core/licence configuration outside the tested range; or
- a new failure or engineering-gate violation in shadow/ordinary use.

## What We Should Build First In Autogration

Subject to WP0 agreement, the smallest durable implementation slice is:

1. A schema-versioned coarse `PerformanceTrace` with monotonic spans.
2. Correlation from backend queue/task lifecycle through node execution and
   final artifact.
3. Step-level `RUNONESTEP` duration and simulation-date context.
4. Separate save/validation, extraction, and transfer spans.
5. Environment and complete case/output fingerprints.
6. A backend summary that calculates time shares and trace completeness.
7. An immutable benchmark/acceptance specification outside ordinary task
   fields, with optional task links for backward compatibility.
8. A comparison report that can return PASS, FAIL, or INCONCLUSIVE.

Do not begin by adding every possible performance setting, building automatic
profile selection, modifying PVT, or reusing live PETEX sessions. First make the
unchanged path measurable and prove the measurement overhead.

## Decisions Required From Engineering And Operations

1. Which models represent typical, slow, PVT-heavy, network-heavy,
   reservoir-heavy, constrained, and event-sensitive work?
2. Which outputs and constraints define engineering equivalence for each?
3. Which PETEX versions, modules, licences, and HPC features are available?
4. Are there lawful internal copies of the removed PETEX case study or related
   user-meeting material?
5. Which Data Objects and response artifacts are already used, and what does
   PETEX document about their dependencies?
6. Which PVT parent/child representations and component mappings exist today?
7. What worker/core/memory and licence-hour budget can support controlled
   repetitions?
8. Which data and traces may be retained, and which model values must be
   redacted?
9. What minimum gain justifies promotion, and what failure-rate increase is
   unacceptable?
10. Who may approve an approximate runtime profile for shadow and ordinary use?

## Failure Modes This Program Is Designed To Prevent

- Claiming a solver speedup when only queueing or parallel throughput changed.
- Optimizing an unmeasured component with a low Amdahl ceiling.
- Treating a reusable Data Object as a safe cache without dependency evidence.
- Reusing a PETEX application session with hidden state contamination.
- Accepting a PVT child model based only on field-rate agreement.
- Coarsening timesteps while missing events or constraint crossings.
- Changing optimizer settings and comparing only the objective value.
- Pooling correlated timesteps as independent benchmark samples.
- Discarding failed or slow runs as outliers after seeing the result.
- Applying a profile outside its model, PVT, version, hardware, or output
  envelope.
- Turning an unrecovered vendor `0.5%` into an invented acceptance rule.

## Definition Of A Successful First Program

The first program succeeds even if it finds no immediate 10x improvement. It
succeeds when:

1. Representative execution time is reproducibly decomposed at Autogration's
   observable boundaries.
2. The installed PETEX capability matrix separates supported facts from unknown
   mechanisms.
3. Reference cases and engineering acceptance contracts are immutable and
   reviewable.
4. At least one high-potential mechanism has a falsifiable, affordable
   experiment design.
5. Autogration can compare baseline and candidate without changing ordinary
   task semantics.
6. No optimization can reach normal execution without evidence, scope,
   approval, invalidation, and rollback.

The likely early outcome is a portfolio rather than one trick: remove exact
study waste, reduce lifecycle/extraction overhead where material, enable
supported parallel capacity, reuse only explicitly valid PETEX responses, and
then investigate PVT or optimization reformulation where traces show that the
inner loop dominates.

That is how the historical PETEX idea should be incorporated into Autogration:
not as a hard-coded `fast mode`, but as a disciplined capability for discovering,
proving, governing, and safely reusing faster ways to answer an engineering
question.

## Sources And Companion Notes

Official product capabilities and access caveats are indexed in `sources.md`.
The current execution boundary, PETEX/IPM roles, subsystem contracts,
WhitsonPVT integration, open opportunity map, and long-term destination are
described in the accompanying research notes. Licensed PETEX manuals, support
guidance, observed installed-version behavior, and approved benchmark results
remain required before implementation-specific performance claims can be
promoted.