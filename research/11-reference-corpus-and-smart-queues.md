# Reference Corpus And Smart Queues

Status: vision branch. This document describes two linked foundations: a broad
reference corpus from existing Autogration evidence, followed by smart queueing
for fixed study plans. It is not an execution plan or authorization to change
production scheduling.

## Why These Belong Together

Autogration already contains more evidence than a blank new product: registered
models, PETEX compute tasks, assumption sets, result trees and time series, task
metadata, logs, file provenance, and CDF ensemble references. That evidence can
teach us which runs are common, costly, failed, duplicated, valuable, or useful
as future benchmarks.

Smart queues should be built from that understanding. Without a reference corpus,
"priority" would be a guess. Without controlled queues, the corpus cannot become
the basis for cautious one-by-one adaptive studies.

## Keep The Decision Landscape Open

There is no requirement to choose one first decision archetype now. The corpus
should remain open to at least:

- continue production versus shut in;
- intervention versus defer;
- drill versus no-drill;
- well/control/facility optimization choices; and
- further recurring decision patterns discovered in historical evidence.

The point is not to merge these into one statistical population. Each will have
different inputs, constraints, outcomes, and evidence quality. The point is to
discover and catalog them before deciding where a focused study capability has
the strongest foundation.

## Existing Evidence Surfaces

The current Autogration implementation already exposes useful evidence, with
important limits:

| Evidence | Current surface | What it can show | Limitation |
| --- | --- | --- | --- |
| Task lineage | `core.tasks`, parent task IDs, task APIs | Asset, user, type, state, time, parent model relation, attempts | No native logical-study grouping |
| Case inputs | Assumption-set files and task assumption APIs | What was applied to a PETEX task | Current presets can be partial; comparisons need canonicalization |
| Model/result structure | `model.node`, properties, topology, result values | Hierarchy, result variables, time series | Schema/output consistency may vary by model/version |
| Result files | Task archives and result metadata | Final resolved result artifacts | Compute-task project/data copies are cleaned after terminal state |
| Logs | `core.vm_log` and task log UI | Queue/run/error clues | Automatic 90-day log retention |
| Step signals | node-client `StepResult` stream | Schedule progression and tracked values | Currently streamed rather than a durable dedicated telemetry history |
| CDF ensemble reference | `cdf_ensemble_id` and CDF export | External ensemble/grouping trail | External lifecycle and model meaning need verification |
| File provenance | `files.metadata` | Original/resolved paths and archive provenance | Distributed storage; not a semantic model-version catalog |

"Everything inside Autogration" is therefore a strong starting point, but not a
guarantee that every historic run is complete, comparable, retained, or suitable
for statistics or ML. The corpus must classify that rather than assume it.

## Reference Corpus Questions

The corpus should answer questions before it tries to predict anything:

1. Which assets, model families, and registered-model parents have enough
   complete cases to compare?
2. What recurring run patterns and decision archetypes exist?
3. Which settings/assumptions commonly vary together?
4. How often do runs fail, warn, retry, or end early, and under what conditions?
5. Where is time spent: queue, archive/copy, model setup, RESOLVE calculation,
   result extraction, or human interpretation?
6. Which outputs are sufficiently consistent to become named technical KPIs?
7. Which historical cases are exact or near duplicates after normalization?
8. Which results are reference-quality, exploratory-only, incomplete, or
   ineligible because their provenance/retention is insufficient?

## Corpus Classification

Each historic item should eventually receive a descriptive classification, not a
retrospective claim of scientific validity.

| Classification | Meaning |
| --- | --- |
| Reference-quality | Model, inputs, outcome, and required provenance are intact; suitable for a benchmark/comparison within declared scope |
| Comparable with caveats | Enough context for a limited comparison, but known model/output/config differences exist |
| Exploratory | Useful to understand behavior or workload; not suitable for probability or decision validation |
| Incomplete | Required assumptions, results, files, or quality evidence are missing |
| Failed/diagnostic | Valuable for reliability analysis; not a technical outcome sample |
| Retention-limited | A known log/telemetry/result context has expired or is externally unavailable |

This classification must be reviewable. It cannot be inferred solely from a task
status such as `Completed`.

## Smart Queue: Operational Intelligence First

The existing path prepares every case and marks it `ENQUEUED` immediately. It
has operational limits such as maximum nodes and licences, but no apparent
study-aware hold/release layer. A smart queue should first improve **when** a
fixed case plan runs, not decide **which** engineering cases belong in that plan.

### Smart queue contract

For a fixed, frozen plan, the queue may:

- hold a planned case until required files, model reference, budget, and policy
  checks are satisfied;
- prioritize baseline, smoke, reference, confirmation, or urgent cases under a
  visible policy;
- respect available node/licence capacity, estimated runtime, and fairness;
- release one case or a small approved batch at a time;
- stop release after a quality/policy gate fails; and
- explain why a case is held, eligible, opened, deferred, or blocked.

It must not:

- silently remove, invent, or reweight planned cases;
- alter a physical assumption, solver setting, or business constraint;
- treat a queue priority as a probability weight; or
- claim that an ordered execution plan is an adaptive study.

### Conceptual case states

```text
Planned -> Held -> Eligible -> Opened -> Enqueued -> Running -> Terminal
                         |                         |
                         +-> Deferred / Blocked ---+
```

`Planned` means the case belongs to a frozen study design. `Opened` means policy
has allowed task creation/release. `Terminal` includes success, controlled
failure, cancellation, or a declared exclusion with an audit record.

The state should live above an individual task attempt. The current task model
already represents execution status; future study/case state should not overload
it.

### First smart-queue questions for engineers and operations

- Which case classes must run first: baseline, model-validation, safety check,
  reference, or user-priority?
- What makes a case ineligible: incomplete files, invalid configuration, licence
  shortage, budget limit, unresolved warning, or another rule?
- When should a case release pause the rest of a plan?
- What fairness policy applies across users, assets, and urgent operations?
- Which runtime/queue estimates are trustworthy enough to display?

These are operational and engineering policies, not merely scheduler settings.

## Adaptive Studies: One-By-One Logic Second

After a smart queue can hold and release a fixed plan safely, it can support a
different capability: opening the next case because prior outcomes changed what
is worth learning.

### Difference from a smart queue

| Smart queue | Adaptive study |
| --- | --- |
| A fixed case set already exists | A candidate pool exists, but only some cases will be opened |
| Optimizes order, readiness, capacity, and policy | Selects the next informative case based on evidence |
| Does not change the study sample | Changes which eligible candidate is opened next, under an approved study rule |
| Can work without outcome analysis | Requires outcome/KPI quality checks and a declared selection rationale |

### One-by-one opening logic

1. Freeze a candidate domain, rules, budget, decision arms, and stop conditions.
2. Open baseline and required reference/validation cases first.
3. Validate their result quality before allowing selection logic to proceed.
4. Score unopened candidates using a transparent criterion.
5. Open exactly one next case, or a very small policy-approved batch.
6. Recalculate evidence and record why that case was selected.
7. Stop or continue under the frozen stop rules.

Initial scoring must not require ML. It can use coverage, local sensitivity,
constraint proximity, runtime cost, or disagreement between named alternatives.

### Why one by one first

One-by-one release makes the causal chain inspectable:

```text
Observed result -> quality check -> selection rationale -> next opened case
```

It prevents a large, opaque burst of costly runs from being described as
adaptive. Once that logic proves useful, a later policy can permit small parallel
batches when their simultaneous value is clear and their rationale remains
auditable.

## Relationship To ML And Economics

The reference corpus may later supply well-labeled examples for ML, but it is
not automatically a training dataset. Historic selection bias, missing context,
mixed model versions, incomplete logs, and non-comparable outputs must be
classified first.

Economics is intentionally postponed. The corpus may catalog technical outcomes
and run behavior now. It should not retroactively attach economics or infer
investment recommendations until the gated Economic Decision Studies branch is
reactivated with its own review and provenance rules.

## Evidence Before Delivery Work

Before these concepts become product work, the team should be able to point to:

- a corpus inventory with known retention and provenance limits;
- several classified reference families across more than one decision archetype;
- a shared KPI and result-quality vocabulary;
- observed current queue/run behavior and operational bottlenecks;
- engineer/operations input on priority and hold/release policies; and
- a clear boundary between fixed-plan queueing and evidence-driven adaptation.

That evidence lets Autogration progress from "many available historical runs" to
a trustworthy foundation for smarter run management.