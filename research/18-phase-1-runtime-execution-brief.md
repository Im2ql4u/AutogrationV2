# Phase 1 Runtime Execution Brief

Status: discussion draft, 2026-09-11.

This brief narrows the runtime program to the current Autogration execution
path. It identifies what the code does today, what should be measured first,
which optimizations become credible under which observations, and how the work
can be sequenced. It does not authorize PETEX runs or propose a product-code
change for approval yet.

## Phase 1 Outcome

Phase 1 should end with four concrete results:

1. A trustworthy time and licence-occupancy decomposition for ordinary PETEX
   tasks.
2. A frozen benchmark set and engineering acceptance contract.
3. A ranked queue of measured optimization experiments with Amdahl bounds.
4. One or two low-semantic-risk candidates ready for controlled implementation
   and benchmark approval.

Phase 1 is not complete when logs exist. It is complete when the team can say
where time goes, which cost is avoidable, how much end-to-end improvement is
possible, and what evidence would permit a change.

## Verified Code Path

The current path crosses three repositories.

| Stage | Current code | Runtime implication |
| --- | --- | --- |
| Build cases | [`buildComputeSet`](../../autogration_frontend/frontend/src/utils/ass.ts) | A lazy Cartesian generator is ultimately materialized into `assumption_sets`; browser cost and case-count growth matter for large studies, but this is not PETEX solver time. |
| Create tasks | [`prepare_petex_compute`](../../autogration/apps/backend/backend/modules/tasks/service/prepare_tasks/petex.py) | One task is created per assumption set. All task initializations run concurrently. |
| Archive task inputs | [`_archive_petex_task_files`](../../autogration/apps/backend/backend/modules/tasks/service/prepare_tasks/petex.py) | The complete parent project/data set is copied into every child task archive. The assumption-set file is written last as the readiness token. |
| Download working inputs | [`execute_task`](../../autogration/apps/nodeclient/nodeclient/task_execution/base.py) | Each worker downloads project and data files from the parent archive before opening PETEX. Data files are downloaded sequentially. |
| Open PETEX | [`OpenServer.__enter__`](../../autogration/apps/nodeclient/nodeclient/openserver/openserver.py) | COM connection/licence checkout, `RESOLVE.START()`, and `RESOLVE.OPENFILE()` occur before compute-specific input retrieval. |
| Retrieve case inputs | [`execute_petex_task`](../../autogration/apps/nodeclient/nodeclient/task_execution/petex.py) | Registered-model results and the assumption set are fetched after PETEX is open. Waiting for the readiness token can therefore consume PETEX licence time. |
| Mutate model | [`execute_petex_task`](../../autogration/apps/nodeclient/nodeclient/task_execution/petex.py) | Nodes, edges, masking, schedules, RESOLVE settings, and module settings are applied through sequential OpenServer calls. |
| Save and validate | [`execute_simulation`](../../autogration/apps/nodeclient/nodeclient/task_execution/petex.py) | `BRSAVE` runs before the simulation; unsaved GAP files may use a fallback save; each GAP system receives solver and prediction validation. |
| Run schedule | [`_do_resolve_simulation`](../../autogration/apps/nodeclient/nodeclient/task_execution/petex.py) | One blocking `RESOLVE.RUNONESTEP()` is issued per simulation step until the end date. |
| Wait for commands | [`OpenServer.do_cmd_blocking`](../../autogration/apps/nodeclient/nodeclient/openserver/openserver.py) | Commands use `DoCommandAsync`, then poll `IsBusy` every 0.2 seconds. This is response-detection granularity, not evidence of 0.2 seconds of solver overhead per poll. |
| Stream step status | [`step_results`](../../autogration/apps/nodeclient/nodeclient/cc_client/step_results.py) | Step date and optional equipment results are queued and flushed by the heartbeat path. Duration and attempt identity are not included. |
| Discover results | [`discover_root`](../../autogration/apps/nodeclient/nodeclient/ipm_client/discovery.py) | Full RESOLVE/GAP discovery performs many OpenServer reads. Its total duration is already logged with `perf_counter`, but call volume and result size are not retained as structured evidence. |
| Persist artifacts | [`_execute_task`](../../autogration/apps/nodeclient/nodeclient/task_execution/base.py) | GAP debug-file archiving occurs while the `OpenServer` context and licence remain open. The result is archived and posted to Postgres after PETEX shuts down. |
| Retry | [`_run_with_retries`](../../autogration/apps/nodeclient/nodeclient/task_execution/base.py) | Up to three attempts reopen PETEX and rerun the task after 5- and 10-second backoffs. Downloads occur outside this loop. A retry can therefore multiply open, mutation, simulation, and extraction cost. |

The task model already provides `created_at`, `started_at`, `finished_at`,
`attempt_no`, `task_id`, `parent_task_id`, `assumption_group`, `assumption_case`,
and `vm_id`. These should be reused rather than replaced by a second task
identity system.

## Important Early Findings

### 1. Licence occupancy is wider than simulation

The PETEX context is entered before `execute_petex_task`. Inside that context,
the node retrieves the registered result and may poll for the assumption-set
readiness token. After simulation, it performs full result discovery and uploads
the GAP debug file before issuing `RESOLVE.SHUTDOWN()` and disconnecting.

Therefore:

$$
T_{licence} = T_{connect/open} + T_{input\ wait} + T_{mutate} +
T_{save/validate} + T_{simulate} + T_{discover} + T_{debug\ upload} +
T_{shutdown}.
$$

This creates a plausible exact-preserving optimization family: move work that
does not require PETEX outside the licence-held region. It must not be changed
until the spans prove its share is material and tests prove lifecycle semantics
are unchanged.

### 2. Child-task archiving scales with both case count and model size

The backend copies the complete project/data set into each PETEX child archive,
while the worker downloads its working copy from the parent archive. For $N$
cases and parent input size $B$, child archival traffic is approximately
$N\times B$ before metadata and assumption-set overhead. These copies run in
background tasks and can contend with worker downloads from the same storage.

The copies may be required for retention, restart, and task self-containment.
The first question is therefore not "remove them" but:

> What time, storage traffic, and readiness delay do per-task copies cause, and
> which ownership/recovery requirements depend on them?

### 3. Retries can hide the largest wasted-runtime category

The node retries the entire PETEX attempt for broad exceptions. The known
`6001: Command not recognised` startup error receives special logging, but the
same full retry boundary is used for other transient failures. A successful
task can therefore contain one or more discarded PETEX runs that are invisible
in a final-duration average unless attempt spans are preserved.

Before tuning a successful run, measure:

- retries and first-attempt success rate;
- failure stage and exception category;
- discarded PETEX and licence time;
- worker/model/version correlation; and
- recovery success by category.

Eliminating a recurrent failed attempt can be more valuable and safer than
tuning a solver setting.

### 4. Result discovery is already known to be observable

`discover_root` already uses a monotonic timer and logs its total duration. This
is the cheapest existing signal to promote into structured evidence. Discovery
reads module settings, optimization elements, topology, equipment properties,
constraints, dates, and result arrays. For short simulations, full-tree
discovery may be a material share of licence time.

### 5. The 0.2-second OpenServer poll is not the first optimization

Reducing the poll interval can only reduce completion-detection delay; it does
not accelerate PETEX computation and may increase COM/CPU pressure. Measure
command duration and busy-poll count first. Test polling policy only if short
commands are frequent enough for the detection tail to matter.

## Phase 1 Measurement Contract

### Coarse spans required first

Use `time.perf_counter()` in the node process. Buffer measurements locally and
persist them after the measured PETEX section so tracing does not add network
I/O to the hot path.

| Span | Owning boundary | Required dimensions |
| --- | --- | --- |
| `task.queue` | backend lifecycle | task, group, case, VM size |
| `task.download.model` | `download_model_file_to_tempdisk` | bytes, source task |
| `task.download.data` | `download_data_files_to_tempdisk` | file count, total bytes |
| `petex.attempt` | each `_execute_task` call | attempt number, outcome, failure category |
| `petex.connect_start_open` | `OpenServer.__enter__` | worker, PETEX/OpenServer version if supported |
| `case.registered_result_fetch` | `get_result` | bytes if available |
| `case.assumption_ready_wait` | `get_assumption_set` | polls, wait duration, assumption bytes |
| `case.mutate` | apply block in `execute_petex_task` | node, edge, schedule, setting and failed-set counts |
| `petex.save_pre` | first `BRSAVE` and fallback saves | command outcome, fallback count |
| `petex.validate_gap` | `_validate_gap` loop | GAP-system count and validation mode |
| `petex.step` | `_run_resolve_step` | step index, simulation start/end date, outcome |
| `petex.save_post` | final `BRSAVE` | command outcome |
| `petex.discover_result` | `discover_root` | module/equipment counts and serialized bytes later |
| `artifact.debug` | `write_debug_file` | bytes, found/not found, upload result |
| `petex.shutdown_disconnect` | `OpenServer.__exit__` | outcome |
| `result.archive` | first half of `write_result_file` | bytes and duration |
| `result.postgres` | backend result POST | bytes, duration and outcome |
| `task.recovery` | missing-file recovery loop | round, files requested/added, duration |

Every span needs a schema version, `task_id`, `attempt_no`, monotonic duration,
UTC start/end for correlation, outcome, and parent span. Do not initially log
OpenServer values, full command strings, model paths, or fluid/model data.

### Existing signals to reconcile

- Backend `created_at`, `started_at`, and `finished_at` remain authoritative for
  task lifecycle.
- Existing node log timestamps can reconstruct an approximate timeline but are
  not sufficient benchmark evidence.
- Existing discovery duration should feed the same trace summary rather than
  creating a competing metric.
- Existing step-result streaming should continue unchanged initially. Adding
  duration to its shared Pydantic contract requires explicit shared-contract
  approval and is not needed for the first local trace artifact.
- Existing `attempt_no` semantics must be checked against node-local retries;
  a trace needs an unambiguous local attempt sequence even if the backend field
  represents a wider rescheduling attempt.

### Trace acceptance before baseline use

The instrumentation itself must pass:

1. Unit tests using a deterministic/fake clock for nesting, failure, retry, and
   missing-span behavior.
2. Existing mocked simulation and step-result tests.
3. One approved Windows/OpenServer smoke case proving spans close on success,
   failure, and cancellation.
4. Trace-on versus trace-off repeated comparison with an agreed overhead ceiling.
5. Reconciliation: child durations may not exceed their parent except for
   explicitly concurrent archive/download spans.
6. No model values, secrets, access tokens, or sensitive paths in the artifact.

## Execution Sequence And Decision Gates

The sequence below is dependency-based. Calendar duration depends on access to
representative models, Windows workers, licences, and PETEX support.

### Gate 0: Measurement charter

**Can start now:** agree definitions and owners without running PETEX.

Decide:

- latency, throughput, licence occupancy, and useful-computation metrics;
- benchmark data boundary and approved environment;
- trace retention and redaction;
- cold versus warm lifecycle definitions;
- exact-preserving versus engineering-equivalent changes;
- engineering outputs and no-cross constraints; and
- who can authorize model/settings changes and PETEX runs.

**Exit:** signed measurement charter and named runtime, PETEX/model, operations,
and engineering-acceptance owners.

### Gate 1: Benchmark and capability inventory

**Can run in parallel after Gate 0.**

Freeze at least one typical case, one slow/convergence-heavy case, one
event/constraint-sensitive case, and one structurally different PVT/network
case. Fingerprint project, linked files, assumption set, RESOLVE/module settings,
PETEX/OpenServer/adapter version, worker class, requested outputs, and licence
context.

At the same time, build the installed-version capability matrix with PETEX:
supported timings/counters, optimizer evaluations, convergence signals,
clustering and hyperthreading scope, Data Object lifecycle, PVT
lumping/delumping, restart/continuation, and supported batching APIs.

**Exit:** benchmark revision, acceptance contract, and every capability marked
`supported`, `unsupported`, `unavailable`, or `unknown` with a source.

### Gate 2: Additive observability design

**Can be designed during Gate 1; implementation waits for review of shared
contracts and data handling.**

Choose the smallest persistence path that can survive retries and task cleanup.
A versioned trace artifact linked to the existing task is preferable to
hundreds of new task columns. Keep ordinary tasks backward compatible and trace
collection feature-flagged.

The smallest useful implementation increment is:

1. local node trace collector;
2. `petex.attempt`, connect/open, input wait, mutate, save/validate, each step,
   discovery, debug upload, shutdown, and final persistence spans;
3. backend queue/lifecycle summary using existing task timestamps;
4. one append-only trace artifact and completeness validator; and
5. tests for retries, errors, cancellation, and trace overhead.

**Exit:** reviewed design and test plan. No solver setting or model behavior is
changed.

### Gate 3: Baseline campaign

**Requires authorized PETEX execution and accepted tracing overhead.**

Use repeated controlled runs of unchanged cases. Separate cold and warm
campaigns. Preserve every failure and randomize case order where practical.
Report per case:

- queue, end-to-end, execution, and licence-held time;
- time share by coarse span;
- step-duration distribution and simulation progression;
- retries, failure stage, and discarded attempt time;
- bytes moved and archived;
- result discovery and persistence cost; and
- worker/licence utilization.

Do not treat steps from one run as independent repetitions.

**Exit:** enough measured coverage to assign the dominant external cost and an
explicit opaque `RUNONESTEP` share where PETEX cannot expose internals.

### Gate 4: Select first experiments

For each candidate, calculate the maximum plausible end-to-end gain from its
measured fraction. Approve only one-factor experiments with a rollback and a
predeclared comparison rule.

Use this routing table:

| Observation | First credible experiment | Required proof |
| --- | --- | --- |
| Material assumption-ready wait while licence is held | Retrieve readiness/input before entering `OpenServer` | Identical task inputs and outputs; lower licence-held time; unchanged cancellation/recovery behavior |
| Material debug upload while licence is held | Move debug artifact persistence after PETEX shutdown | Same artifact bytes and failure reporting; lower licence-held time |
| Material full-tree discovery | Define a versioned minimal output contract and compare selective extraction | Every required KPI/constraint/audit input present; full extraction remains available |
| High per-task duplicated archive traffic or readiness delay | Reference parent-owned immutable files or deduplicate archive storage | Restart, retention, provenance, and missing-file recovery remain valid |
| High sequential data-download share | Concurrent bounded downloads | Identical bytes and paths; no storage saturation or worse tail latency |
| High mutation share and many OpenServer calls | Supported batching or omission of unchanged sets | Exact applied-state comparison; same failures and outputs |
| High retry/discarded-attempt share | Fix the dominant classified failure, beginning with startup `6001` if confirmed | Higher first-attempt success and lower wasted licence time without masking real failures |
| High discovery/persistence share but low simulation share | Release licence before non-PETEX artifact work and avoid duplicate serialization | Identical artifacts and backend result; lower licence occupancy and task latency |
| `RUNONESTEP` dominates with exposed repeated GAP/optimizer work | PETEX-supported core, Data Object, optimizer, or workflow experiment | Paired runtime evidence plus all engineering hard gates |
| `RUNONESTEP` dominates but remains opaque | PETEX telemetry or copied-model counters before tuning | Internal attribution sufficient to distinguish competing mechanisms |
| Queue/licence wait dominates at study level | Controlled case concurrency and worker/licence scheduling experiment | Better accepted-case throughput per licence-hour, not a claimed solver speedup |
| Case count dominates useful study time | Exact duplicate/inactive-case suppression first; DOE later | Full fingerprint equality or engineer-approved study-design evidence |

### Gate 5: Controlled candidate benchmark

Run baseline/candidate pairs in randomized `AB`/`BA` blocks on the same worker
class and licence context. Start with at least ten measured pairs per case, then
continue to the declared precision or budget stop. Report median, tail,
paired-speedup distribution, bootstrap 95% confidence interval, failures, and
order effects.

An exact-preserving candidate must preserve serialized inputs, requested
outputs, warnings, steps, events, and failures under the declared normal
precision. A PETEX setting, timestep, PVT, response, or formulation candidate
requires the full engineer-owned acceptance contract.

**Exit:** `PASS`, `FAIL`, or `INCONCLUSIVE`. Only a pass can enter shadow use.

## Candidate Order Before Measurements

This is a provisional risk order, not a conclusion about benefit:

1. Trace overhead control.
2. Move non-PETEX network/storage work outside licence occupancy when measured.
3. Fix recurrent whole-attempt failures and retries.
4. Reduce result extraction to an approved output contract.
5. Reduce duplicated archival/transfer work while preserving recovery and
   provenance.
6. Bound case-level concurrency against licences and worker resources.
7. Use supported OpenServer batching or omit provably unchanged writes.
8. Test supported session/Data Object reuse with randomized cross-case
   contamination controls.
9. Test PETEX-supported CPU/cluster profiles.
10. Test timestep, restart, optimization, response, PVT, and model/workflow
    changes only with engineering-equivalence evidence.

Measurements can reorder this list. A candidate with a 2% measured share does
not outrank one responsible for 60% merely because it is easy to implement.

## Proposed Working Sessions

### Session A: Runtime-path review

Participants: Autogration backend/node engineers, operations, PETEX model
engineer.

Walk through the verified path and resolve:

- whether child archive copies are legally/operationally required;
- when backend `attempt_no` increments versus node-local retries;
- whether debug upload must occur before PETEX shutdown;
- which result fields are actually consumed by UI/export/engineering review;
- how licences are allocated and observed; and
- which PETEX version/build is deployed on each worker image.

### Session B: Benchmark contract

Participants: asset engineers, PETEX model engineer, runtime owner.

Select cases and declare required steps, events, phases, pressures, rates,
cumulatives, balances, constraints, optimization feasibility, and decision
KPIs. Agree tolerances only for engineering-equivalent experiments.

### Session C: Trace design review

Participants: backend/node engineers, security/data owner, operations.

Agree schema, redaction, artifact storage, feature flag, retention, attempt
identity, overhead ceiling, and failure/cancellation behavior. Review the
component instructions requiring approval for shared contracts and runtime
assumptions.

### Session D: PETEX capability review

Participants: PETEX support, PETEX model engineer, runtime owner.

Complete the installed-version capability matrix. Ask for documented counters
and settings, not generic product capability. Keep unknowns unknown.

### Session E: Baseline readout and experiment selection

Review time shares, Amdahl bounds, failure waste, licence occupancy, and
engineering variability. Select the first one or two candidates and freeze
their experiment revisions before implementation.

## Questions That Must Be Answered In Discussion

1. Is the primary business limit elapsed study time, interactive case latency,
   PETEX licence-hours, worker cost, or all four with separate targets?
2. Which existing studies are representative enough to become immutable
   references, and who owns their acceptance contract?
3. Are full child-task archives required indefinitely, or can provenance point
   to immutable parent files?
4. Can case input retrieval occur before licence checkout without violating
   cancellation, recovery, or security assumptions?
5. Must GAP logs be uploaded before `RESOLVE.SHUTDOWN()`, or only copied locally
   before shutdown?
6. Which result-tree fields are consumed today, and which are retained only
   because discovery is broad?
7. What exactly does backend `attempt_no` mean relative to the three local
   retries?
8. What PETEX timings, counts, and parallel controls exist in the deployed
   version and licence?
9. How many licences and cores are actually available, and what contention is
   acceptable?
10. What trace overhead and minimum useful speedup justify production work?

## Recommended Immediate Decision

Approve Gate 0 and the design portion of Gates 1 and 2. Do not yet approve a
polling change, session reuse, PVT simplification, optimizer setting, or model
reformulation.

The first implementation proposal brought back to the team should be a small,
feature-flagged, coarse trace around existing boundaries, with no shared
step-result change and no synchronous telemetry writes inside PETEX execution.
The first baseline readout should then decide whether the earliest optimization
belongs to licence-scope/lifecycle work, retries, storage/extraction, case
concurrency, or the internals of `RUNONESTEP`.