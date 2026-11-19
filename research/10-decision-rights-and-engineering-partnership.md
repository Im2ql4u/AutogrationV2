# Decision Rights And Engineering Partnership

Status: vision governance document. It identifies who must decide what before a
vision branch becomes delivery work. It is not an execution plan or approval to
change a production workflow.

## What Is Already Agreed

The following positions are now part of the vision:

| Position | Status |
| --- | --- |
| Strengthen and patch the existing product before building major new capability | Agreed: Pillar 1 is first |
| Use smarter compressed runs rather than defaulting to large Cartesian batches | Agreed direction; exact study modes remain open |
| Show distributions for value/income/flow where the uncertainty design supports them | Agreed, but conditional by study type |
| Keep scenario/sensitivity results distinct from probability claims | Agreed |
| Put ML and later AI after the core study and uncertainty foundations | Agreed |
| Retain a limited, gated Economic Decision Studies branch but postpone it | Agreed: deliberately deferred |
| Build smart queues before adaptive studies, then open cases one by one under explicit logic | Agreed |
| Keep adaptive behavior aligned with reservoir, production, facilities, and economics engineers | Agreed |
| Treat subsystem/multifidelity and native physics as long-term, lower-priority research branches | Agreed |

These conclusions should not be reopened casually while individual defects are
being reviewed. They are the current compass, not the eventual feature list.

## Decisions That Need The Product Owner

None of these need an answer today to preserve the vision. They are the choices
that must be made before their corresponding branch becomes real delivery work.

| Decision | Why it needs product-owner judgment | Proposed default | Engineer input required? |
| --- | --- | --- | --- |
| Reference decision landscape | It determines how broad historic evidence is organized before one archetype becomes a delivery focus | Keep continue/shut-in, intervention/defer, drill/no-drill, and additional discovered archetypes open | Yes, heavily |
| Meaning of a preset | This defines the product promise of reuse | Keep an assumptions library, but add a separate full-scenario/study artifact; never imply the former is the latter | Yes, for scenario completeness |
| Run-budget governance | It trades user freedom against cost, queue pressure, and accidental waste | Environment-configured soft warning, hard cap, and named exception route | Operations input |
| First smart-run modes | It affects the initial product surface and learning curve | Retain full factorial; add quick sensitivity and one screening/space-filling mode before broad DOE | Yes, for usefulness |
| Probability-result policy | It controls when the UI may say P10/P50/P90 or probability | Only weighted/declared probability plans may show percentiles; scenarios and sensitivities cannot | Yes, for uncertainty semantics |
| First Economic Decision Studies template | It defines what the gated branch can responsibly claim | Deferred until the technical/reference branches mature | Yes, plus economics owner later |
| Smart-queue policy | It determines how a fixed study plan is held, ordered, and released | Start with transparent priority/release rules without changing the planned sample | Yes, for operational policy |
| Adaptive autonomy level | It changes whether the system merely recommends or may spend compute automatically | First open cases one by one under a human-approved policy; later consider bounded automatic batches | Yes |
| Evidence publication rule | It determines what is visible as a recommendation versus exploratory output | Publish reviewed decision evidence, never an autonomous operational instruction | Yes, plus governance/legal if needed |

### Current Product-Owner Decisions

Your latest direction resolves several prior questions:

1. Keep the reference decision landscape open across continue/shut-in,
  intervention/defer, drill/no-drill, and further archetypes found in the
  corpus. Do not select one canonical decision yet.
2. Treat the existing Autogration application, historical runs, CDF references,
  and available results as a broad evidence corpus to analyze.
3. Postpone the economics branch; retain its safety gates as a future vision.
4. Build smart operational queues first, then one-by-one adaptive studies.

The remaining product-owner questions are intentionally smaller:

1. What policy should distinguish an ordinary queued run from an urgent,
  exploratory, reference, or confirmation run?
2. Who may approve an exception to a future run-budget or queue policy?
3. At what point should one reference decision archetype graduate from the broad
  corpus into a focused delivery candidate?
4. When economics returns to active consideration, which governance owner should
  approve its first limited template?

## Decisions That Need Engineering Co-Design

These cannot be settled responsibly by product preference alone.

| Topic | Required engineering contribution | Why |
| --- | --- | --- |
| Input range/distribution | Physical bounds, elicitation basis, units, transform, revision cadence | A plausible UI range is not a defensible uncertainty model |
| Realization bundles and weights | Which geology/PVT/rel-perm/aquifer combinations belong together and how they are weighted | Independent sampling can create physically impossible worlds |
| P10/P50/P90 convention | Exceedance versus quantile language and asset reporting convention | Terminology otherwise reverses high and low cases |
| Pruning rules | When a RESOLVE setting is inactive, contradictory, or conditionally meaningful | Product code cannot infer PETEX/field semantics safely |
| KPI and constraint definitions | Formula, unit, time aggregation, data source, and failure treatment | A rate, volume, or facility margin can be calculated many ways |
| Model-quality policy | What warnings, non-convergence, partial results, or missing data mean | A task status alone is not an engineering quality judgment |
| Economics assumptions | Cost, price, tax, discounting, timing, and approval convention | These materially determine a recommendation |
| Adaptive stop conditions | What uncertainty level or constraint margin is sufficient for a decision | Optimization cannot choose an acceptable business risk by itself |
| Response/subsystem validity | Boundary variables, validity envelope, and escalation rule | Partial models are unsafe without a physical contract |

## Things We Can Clarify Without Waiting For Engineers

These are platform quality improvements. Engineer review is welcome, but lack of
immediate availability should not block understanding or documentation.

- deterministic semantic case identifiers and exact case fingerprints;
- canonical typed equality and duplicate detection;
- explicit warnings for lossy preset conversion;
- separate labels for exploration, sensitivity, screening, probability, and
  decision evidence;
- audit histories for changes, retries, exclusions, and overrides;
- a transparent explanation of the Cartesian multiplication causing a run count;
- a consistent representation of task attempt versus engineering case; and
- scoped editing that reduces accidental changes to unrelated module settings.

## Things Deliberately Deferred

The following should remain research or later-policy questions until the earlier
vision branches establish trustworthy inputs, outcomes, and validation:

- choice of ML algorithm or neural architecture;
- a cross-asset universal surrogate;
- arbitrary correlation-matrix editing;
- automated adaptive dispatch without review;
- automatic graph partitioning or arbitrary subsystem execution;
- a production native network solver;
- a REVEAL-like reservoir simulator; and
- automated operational or investment decisions.

Deferral is not rejection. It protects the more ambitious work from being built
on ambiguous data and weak validation.

## Collaboration Model For Each Vision Branch

| Branch | Product and platform role | Engineer role | Economics/operations role |
| --- | --- | --- | --- |
| Pillar 1 | Make current behavior exact, visible, and reproducible | Confirm semantic exceptions and model rules | Set run-budget and queue expectations |
| Uncertainty outputs | Preserve distributions, samples, weights, and display conventions | Define valid uncertainty and realization meaning | Confirm commercial uncertainty where relevant |
| Economic Decision Studies | Build gates, templates, traceability, and evidence views | Confirm technical KPIs and constraints | Own cashflow assumptions and recommendation review |
| Adaptive studies | Make selection/rationale/stopping transparent | Set technical decision boundaries and review proposed runs | Set compute budget and decision-risk tolerance |
| ML/AI | Provide data lineage, validation, and controlled interaction | Judge domain validity and engineering failure modes | Approve use in decision evidence |
| Multifidelity/native physics | Build benchmark and interface infrastructure | Define physical validity/acceptance | Decide whether savings justify risk and support cost |

## How The Existing Mistakes Feed The Vision

The existing assumptions audit is not separate cleanup. It is the proof that
Pillar 1 is needed before the later branches:

- case identity, dedupe, and complete scenarios are prerequisites for trustworthy
  distributions;
- run budgets and pruning are the first form of smart compression;
- visible failure/lossiness policy is required before economics can rely on a
  study outcome;
- declared setting semantics are the seed of later adaptive and multifidelity
  validity rules; and
- deterministic study records become the training and validation substrate for
  future ML.

This is why the correct next conversation is a review of the first-pillar issues
and the Golden Decision Pack, not a premature choice of AI model or solver stack.