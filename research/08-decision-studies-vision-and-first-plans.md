# Decision Studies Vision And First Plans

Status: planning document. This defines a direction and acceptance gates; it
does not authorize product code or financial recommendations yet.

## The Vision

Autogration should become the place where an engineer can take a field decision
from question to defensible evidence:

```text
Decision question
  -> alternatives and constraints
  -> uncertainty model and run budget
  -> smallest defensible set of calculations
  -> RESOLVE and other execution adapters
  -> validated technical and economic outcomes
  -> reviewable decision evidence
```

The product is not primarily a replacement for GAP or RESOLVE. RESOLVE remains
the trusted integrated execution engine in the first phase. Autogration owns the
study definition, case selection, evidence, economics, risk framing, and the
reason why each calculation was worth paying for.

The intended experience is not "run every combination." It is:

> Here are the alternatives. Here is what is uncertain. Here is the evidence
> needed to choose. Here are the calculations that materially reduce that
> uncertainty. Here is what would change the answer.

## Product Modes

One interface should not imply that every study has equal evidential status.
Autogration needs explicit modes.

| Mode | Purpose | Permitted output | Not permitted |
| --- | --- | --- | --- |
| Exploration | Debug a model, understand a local effect, inspect a scenario | Technical plots, sensitivities, warnings | Probability or economic recommendation claims |
| Screening | Rank inputs and reduce a large uncertainty space | Factor rankings and candidate regions | P10/P50/P90 as a probability result unless a probability plan exists |
| Forecast uncertainty | Propagate declared distributions or realization weights | Weighted distributions, exceedance statistics, risk metrics | Automatic investment recommendation without economics and review |
| Economic decision study | Compare named alternatives under explicit uncertainty | Decision evidence, NPV/risk distributions, review package | Unreviewed automatic approval or operational command |
| Research sandbox | Benchmark new numerical, surrogate, or subsystem approaches | Experimental results and validation reports | Customer-critical decisions |

This avoids a common failure mode: a fast sensitivity study accidentally being
presented as a statistically defensible reserves or investment forecast.

## The Core Study Model

The current `ComputeSet` is a useful execution payload but is not a study. The
future conceptual hierarchy is:

```text
Study
  -> immutable StudyRevision
      -> DecisionArm(s)
      -> UncertaintyPlan
      -> DesignPlan
      -> StudyCase(s)
          -> CaseExecution attempt(s)
              -> RESOLVE task(s)
              -> Outcome(s)
```

### Meaning of each object

| Object | Meaning | Must be immutable after run starts? |
| --- | --- | --- |
| Study | Durable business/engineering question | No; it may have new revisions |
| StudyRevision | Frozen model reference, assumptions, rules, and economics version | Yes |
| DecisionArm | A controllable alternative, such as shut in, continue, intervene, or drill | Yes within a revision |
| UncertaintyPlan | Inputs, distributions, realization weights, dependencies, and seed | Yes |
| DesignPlan | How candidate cases are generated and selected | Yes, with later adaptive decisions logged separately |
| StudyCase | One exact assignment of decisions plus uncertain inputs | Yes |
| CaseExecution | One execution attempt; retries do not make a new case | No |
| Outcome | Technical KPIs, quality flags, cashflows, and provenance | Append/recompute with versioning |

The separation matters. A retry, a VM change, or a new task attempt must not
silently become a different engineering case. Conversely, a new model revision
must not be presented as the same study evidence.

## Smart Compressed Runs

Yes. This is the best first technical product direction, provided "compressed"
means less wasted information collection, not less physical rigor.

### The working hypothesis

For many existing studies, the largest avoidable cost is not the RESOLVE solver
itself. It is launching cases that are duplicates, inactive, infeasible,
dominated, or uninformative for the decision.

**Disproving experiment:** take one completed, representative study; recreate
its conclusion using a proposed compressed plan; compare the number of
high-fidelity runs, runtime, constraint findings, and final decision against the
full reference plan. If the decision changes or a material constraint is missed,
the compressed method has failed for that decision class.

### Compression ladder

Implement these in order. Each lower row requires more validation than the row
above it.

| Technique | Why it reduces runs | What it can safely claim | First implementation |
| --- | --- | --- | --- |
| Canonicalization and exact deduplication | Removes semantically identical cases such as `100`, `100.0`, or repeated settings | Exact equivalence | Normalize values and hash a canonical case payload |
| Declarative pruning | Removes branches where a selected mode makes another input inactive | A setting is inapplicable under known rules | Encode and display rules such as fixed timestep suppressing max adaptive timestep |
| Exact result reuse | Avoids repeating a prior identical full-engine calculation | Exact reuse if full fingerprint matches | Reuse only when model, data, settings, assumptions, engine version, and output contract match |
| Baseline plus one-at-a-time | Quickly identifies local response and broken assumptions | Local sensitivity only | Baseline plus low/high perturbation per selected factor |
| Screening DOE | Finds likely important factors at far fewer cases than a full factorial | Screening, with stated aliasing/interaction limits | Start with an engineer-reviewed two-level fractional design or Morris screening |
| Space-filling DOE | Covers continuous uncertainty without enumerating every level | Broad exploratory coverage | Seeded Latin hypercube design with bounds and units |
| Representative realization selection | Avoids treating every reservoir realization as equally unrelated scalar inputs | Weighted ensemble analysis if realization weights are valid | Select and preserve named reservoir realization bundles |
| Adaptive selection | Spends later runs where uncertainty or decision risk remains | A documented information-seeking sequence | Candidate pool plus deterministic heuristic, then validated surrogate selection |
| Response-model or subsystem reuse | Replaces a validated narrow subsystem with a cheaper response | Only inside declared validity envelope | One approved component response contract and escalation rule |

### What "compressed" looks like in practice

Suppose there are eight inputs and each is considered at low/base/high values.
A full factorial requires $3^8 = 6561$ cases. That is often a poor first study.

| Goal | Better first design | Indicative scale | What the engineer learns |
| --- | --- | --- | --- |
| Check model behavior | Baseline plus one-at-a-time low/high changes | $1 + 2k = 17$ for $k=8$ | Direction and obvious bad inputs |
| Rank many inputs | Morris or a reviewed screening design | Tens to low hundreds | Which variables deserve detailed study |
| Explore continuous uncertainty | Seeded maximin Latin hypercube | Often 32-64 starting cases | Broad response surface and interactions worth investigating |
| Compare alternatives | Same uncertainty samples across each decision arm | Depends on arms and budget | Lower-noise difference between alternatives |
| Resolve a close call | Adaptive batches after an initial design | Fixed budget, e.g. batches of 8-16 | Cases selected near uncertainty or constraint boundaries |

These numbers are illustrations, not universal prescriptions. The model's cost,
number of relevant variables, physics, and consequence of a wrong answer set the
budget.

### Important distinction: screening versus probability

An adaptive or screening plan deliberately oversamples informative regions. Its
raw rows cannot automatically be treated as an unbiased probability sample.

Therefore Autogration should keep two lanes separate:

- **Learning lane:** screening, adaptive selection, and surrogate training.
- **Probability lane:** a frozen, weighted, reproducible sample plan used for
  P10/P50/P90 and risk reporting.

If adaptive samples contribute to a probability result, the sampling/weighting
method must explicitly correct for that. In the early product, do not do this.
Use adaptive runs to decide where to learn, then confirm the decision with a
representative probability sample or a full-engine holdout set.

### First smart-run release

The first later code release should not require ML. It should offer four clearly
labeled run modes:

1. **Full factorial:** retained for small, discrete studies.
2. **Quick sensitivity:** baseline plus selected low/high one-at-a-time changes.
3. **Screening:** an engineer-reviewed fractional/Morris design for a bounded
   number of inputs.
4. **Uncertainty sample:** seeded Latin hypercube over declared distributions.

All modes use the same case fingerprint, run budget, preflight report, and
result quality contract.

## Uncertainty, Distributions, And P10/P50/P90

### Should we do this?

Yes, but only when the product can distinguish a scenario range from a stated
probability model. P10/P50/P90 are valuable decision outputs, but they are easy
to misuse.

An input described as "P10/P50/P90" is a three-point expert summary, not by
itself a mathematical distribution. It must be treated in one of two ways:

1. As three named low/base/high scenarios with no probability claim; or
2. As evidence used to define a reviewed distribution, transform, and
  correlation assumptions.

### Make percentile meaning unambiguous

Petroleum usage often calls P10 the high case because there is a 10% probability
of exceeding it. Statistical software often calls the 10th percentile the low
case. Autogration must never rely on the label alone.

Store and display both:

- **Quantile:** $Q_p$ such that $\Pr(Y \leq Q_p)=p$.
- **Exceedance value:** $E_p$ such that $\Pr(Y \geq E_p)=p$.

For every card and export, show the convention in words, for example:

```text
NPV high case: 10% probability of exceedance
NPV central case: 50% probability of exceedance
NPV low case: 90% probability of exceedance
```

Do not label something P10/P50/P90 until the study revision declares its
convention.

### Distribution types to support first

Start narrowly. A simple, inspectable uncertainty model is more useful than a
large list of poorly understood probability widgets.

| Input type | First representation | Examples | Notes |
| --- | --- | --- | --- |
| Fixed | Scalar plus unit and source | Known pipe diameter, approved capex | Still versioned and attributable |
| Discrete weighted | Named values/realizations and weights | Reservoir realization, equipment availability state | Best initial representation for model ensembles |
| Triangular | Minimum, most likely, maximum | Elicited skin or deliverability factor | Requires source and engineer review |
| Uniform | Explicit lower and upper physical bounds | Bounded unknown setting | Do not use merely because no distribution is known |
| Lognormal or truncated normal | Later, reviewed distribution family | Positive multiplicative uncertainty | Requires parameterization and suitability evidence |
| Joint realization bundle | Named coherent combination with weight | Geology/PVT/rel-perm realization bundle | Prefer this to an arbitrary correlation matrix initially |

Decision variables are not distributions. "Drill a well" and "shut in" are
decision arms. Price, availability, permeability, and deliverability may be
uncertain inputs.

### Correlation strategy

Correlation is necessary but should not begin as a free-form matrix editor.
Initial support should be:

1. **Named realization bundles:** compatible geology, PVT, relative permeability,
  and aquifer choices travel together with one weight.
2. **Shared sampled drivers:** the same price or availability path is applied to
  every decision arm for an uncertainty sample.
3. **Correlation matrices later:** only after validation of positive
  semidefiniteness, variable transforms, and engineer interpretation.

For fair comparisons, use **common random numbers**: run the same uncertainty
sample across every decision arm. Then the difference between alternatives is
less noisy and more explainable.

### Sample-size and stability rules

There is no universal number of runs that makes P10/P50/P90 trustworthy. Tails
are especially unstable with small samples. A result must show:

- planned and completed sample count;
- realization/scenario weights and effective sample size;
- failed/excluded cases and their treatment;
- bootstrap confidence intervals for percentiles when applicable; and
- whether the decision ranking remains stable under resampling.

Use a fixed initial budget and add representative sample batches until the
percentile uncertainty and decision ranking meet the declared tolerance, or the
budget stops the study. A preliminary result must be labeled preliminary rather
than given false precision.

## The Economic Decision Gate

The requested limited/blocked economics branch is the right idea, with one
important refinement: make it a **feature-gated workflow branch**, not a
permanent divergent Git branch. It should share the same study/case/task
foundation while imposing stronger entry and publication rules.

Call the first product area **Economic Decision Studies**. It is enabled only
for selected assets, users, and decision templates while it is being validated.

### Why it is a gate

Economics turns a technical study into a capital or operating decision. That
requires more discipline than a sensitivity plot. The gate prevents Autogration
from publishing an apparently authoritative recommendation with hidden price,
cost, model-quality, or probability assumptions.

### Lifecycle

```text
Draft
  -> Engineering ready
  -> Economics ready
  -> Running
  -> Results reviewed
  -> Decision evidence ready
  -> Approved or archived
```

Each transition records the user, time, review note, and study revision hash.

### Entry requirements

A study may enter Economic Decision Studies only when all of these are true:

| Gate | Required evidence |
| --- | --- |
| Model provenance | Registered model task, linked data files, model revision/fingerprint |
| Decision framing | Named alternatives, horizon, operational constraints, and owner |
| KPI contract | Defined rates, volumes, uptime, emissions, facility, and integrity metrics with units and aggregation rules |
| Uncertainty declaration | Every variable classified as fixed, decision, scenario, or probabilistic input; weights/dependencies stated |
| Economics template | Currency, base date, real/nominal basis, price deck, capex, opex, tax/royalty scope, discounting convention |
| Quality policy | What constitutes a failed, excluded, retried, or warning-only simulation result |
| Review ownership | Named engineering and economics reviewers |

### Publication requirements

The workflow remains blocked from a recommendation until:

- all selected cases are terminal and their treatment is visible;
- the full-engine confirmation cases required by the plan pass;
- economics uses a pinned, approved template version;
- assumptions and distribution convention are visible in the result;
- constraint violations are reported rather than averaged away; and
- the required reviewers sign the evidence package.

The first version should publish **decision evidence**, not an autonomous
instruction to shut in or drill. A human remains accountable for the action.

### First economics scope

Start with one decision template, one currency/base-date convention, one
approved cashflow cadence, and a limited set of inputs. For example:

```text
Decision arms: continue / shut in / intervention
Outputs: monthly oil, gas, water, uptime, capex, opex, NPV, facility margin
Constraints: water-handling limit, minimum uptime, approved spend envelope
```

Validate every cashflow formula against a finance-owned reference spreadsheet
before making the template available to users.

## What Should Be Adaptive

Adaptivity should change **what Autogration asks the execution engine to do
next**, not silently change the physical model or business rules.

| Adaptable thing | Initial method | Later method | Must not happen automatically |
| --- | --- | --- | --- |
| Case selection | Deterministic coverage/sensitivity heuristic | Uncertainty-aware surrogate acquisition | Hidden removal of unfavorable cases |
| Run order and concurrency | Cost, queue, license, and priority aware queueing | Predicted runtime-aware scheduling | Changing the scientific sample after results are seen without audit |
| Study stopping | Budget, completion, or human approval | Decision-stability and percentile-confidence rule | Declaring success merely because a model is uncertain |
| Fidelity choice | Exact cache hit or mandatory full RESOLVE run | Validated response-model escalation | Downgrading a decision-critical case without a validity certificate |
| Result review | Quality flags and missing-output checks | Anomaly triage | Silently discarding difficult or failed cases |
| Presentation | Show most decision-relevant differences | Explainable ranking and evidence retrieval | Concealing contrary outcomes |

### The adaptive control loop

1. Freeze a candidate domain, uncertainty plan, budget, and decision arms.
2. Run an initial representative batch.
3. Check task/result quality and calculate decision KPIs.
4. Score remaining candidates with a declared rule.
5. Queue a small next batch and log the rationale.
6. Re-evaluate stopping conditions.
7. Confirm the answer with designated full-engine and representative cases.

The first scoring rules should be transparent:

- **Coverage:** choose the candidate furthest from already sampled inputs.
- **Sensitivity:** investigate the dimensions currently associated with the
  largest outcome change.
- **Constraint boundary:** investigate where water, pressure, capacity, or
  integrity margins are close to zero.
- **Decision disagreement:** investigate where two decision arms have similar
  expected value or opposite outcomes across plausible realizations.
- **Tail stabilization:** add representative probability samples when a stated
  percentile has a wide confidence band.

### Explicit stop rules

Every adaptive study chooses one or more before it runs:

- high-fidelity run-credit budget exhausted;
- all required cases complete;
- decision preference remains unchanged across bootstrap/resampling checks;
- percentile confidence interval is below a stated tolerance;
- no eligible candidate remains inside the declared domain;
- full-engine confirmation passes; or
- an engineer pauses/stops the study.

Store the reason the system chose the next run and the reason it stopped. This
record is part of the engineering evidence.

### What stays human-controlled

Autogration must not automatically alter:

- model topology, well additions, shutdown logic, or physical assumptions;
- safety, integrity, facility, or regulatory limits;
- price deck, cost model, or discount-rate assumptions;
- solver tolerances or RESOLVE optimization strategy outside an approved plan;
- the meaning of a failure; or
- the final field action.

## Where ML Fits

ML is useful after the study foundation exists. The progression should be
evidence-first.

### Stage A: no ML, but intelligent algorithms

Implement canonicalization, pruning, DOE generation, KPI calculation, result
quality checks, deterministic sensitivity, and transparent candidate scoring.
These deliver most early value and create clean training data.

### Stage B: statistical surrogates for narrow outputs

For fewer than roughly 10-15 well-defined numerical inputs and a few hundred
reference cases, begin with an uncertainty-aware tabular surrogate such as a
Gaussian process. Predict only stable, well-defined outputs such as 5-year NPV,
peak water rate, cumulative oil, or a facility constraint margin.

Train one model per compatible model family/revision and output contract. Do not
train a universal field model from unrelated assets and call it physics.

### Stage C: active learning

Use the surrogate to propose the next full RESOLVE cases where uncertainty,
constraint risk, or decision ambiguity is greatest. The proposal remains
auditable and can initially require engineer approval.

### Stage D: advanced models

Only after repeated evidence of value should Autogration investigate reduced
order models, learned state evolution, learned warm starts, or deeper structured
surrogates. These are research projects, not an MVP feature.

### ML acceptance contract

No ML output may influence a Decision Evidence result unless it has:

1. A versioned training dataset, source engine version, and study/model scope.
2. Scenario/realization-separated validation; no random leakage between nearly
  identical timesteps or cases.
3. KPI error metrics broken down by important operating regimes.
4. Prediction-interval calibration evidence.
5. Out-of-domain detection and an automatic full-engine escalation rule.
6. Physical/operational checks such as nonnegative rates, bounds, and declared
  monotonic constraints where applicable.
7. A decision-level comparison against held-out full-engine results.

LLM-style assistance has a separate, lower-risk role: search study evidence,
explain named assumptions, draft reports from cited results, and help navigate
models. It must not invent a physical explanation or act as the numerical model.

## Clarifying The Earlier "Point 7"

There were two plausible references in the earlier outline. Both matter.

### Adaptive-loop step 7: validate and stop

The final adaptive-loop step is not an administrative afterthought. It prevents
the system from endlessly chasing a local optimum or stopping after a flattering
sample.

At this step Autogration must:

1. Test the selected decision against designated holdout or representative
  full-engine cases.
2. Recalculate percentiles and decision ranking with resampling/weight checks.
3. Confirm that required constraints have not been averaged away.
4. Check whether surrogate predictions are inside their validated domain.
5. Record whether the stopping rule was met, the remaining uncertainty, and the
  condition likely to overturn the result.

The output is allowed to be "inconclusive; buy more information or run more
cases." That is a valid engineering outcome.

### Previous plan point 6: multifidelity and partial-system work

This is how Autogration can eventually make runs cheaper without pretending the
rest of the field does not exist.

There are four increasingly difficult levels:

1. **Exact reuse:** same complete case fingerprint, same result. Safe and first.
2. **Response reuse:** replace one component with a response table/model inside
  a tested input range. Example: an approved well or facility response over a
  pressure/rate range.
3. **Fixed-boundary local study:** simulate a component while imposing a known
  separator pressure, composition, or rate boundary. Valid only if full-model
  sensitivity demonstrates the boundary is sufficiently stable.
4. **Iterative co-simulation:** separate reservoir/network/facility executors
  exchange pressure, rate, temperature, composition, and controls every
  timestep until interface residuals converge.

Levels 3 and 4 require an explicit interface contract, units/sign conventions,
coupling cadence, tolerance, iteration cap, residual history, and comparison to
full-model reference cases. Shared manifolds, gas lift, compression, routing,
recycle, and reservoir communication are strong-coupling red flags.

The first build should be level 1, followed by one tightly bounded level-2
response contract. Do not build arbitrary graph cutting as an early feature.

### Previous plan point 7: native physics sandbox

The native physics sandbox is a separate research track, not an extension of
the economic study feature. Its purpose is to establish a transparent,
independently testable capability and to learn where native computation might
eventually create real value.

It begins with deliberately small problems:

1. A transparent steady-state network with known sources, pipes, and simple
  pressure-drop closures.
2. Mass-balance and pressure-balance residuals at every node and edge.
3. A robust nonlinear solution process with damping/trust-region behavior and
  detailed convergence diagnostics.
4. Synthetic cases covering shared-manifold back pressure, constraint switching,
  and simple controls.
5. Comparison against hand calculations, transparent reference code, and later
  approved PETEX benchmark cases.

It does **not** begin with a commercial-scale compositional reservoir simulator,
GAP cloning, or customer-critical operating recommendations. The physical closure
models and verification burden are the hard part, not merely implementing
Newton's method.

OPM Flow and MRST are valuable inspectable research references. Their licenses
must be reviewed before any runtime integration or distribution; use them first
as benchmark/reference assets, not assumed embeddable production dependencies.

The sandbox earns a production role only when it meets predefined conservation,
convergence, runtime, KPI-agreement, and decision-regret criteria on versioned
benchmarks. Until then, it remains research.

## First Plans

The plans are ordered by dependency, not by a calendar. Do not start the next
one because time passed; start it when the previous exit criteria are met.

### Plan 0: Golden Decision Pack - no code

**Goal:** choose one recurring real decision and make its current evidence
reproducible using existing Autogration and RESOLVE capabilities.

**Scope:** one asset, one registered model revision, one decision question, and
one approved economics reference.

**Work:**

1. Write a decision charter: decision owner, alternatives, horizon, constraints,
  consequences of a wrong answer, and success metric.
2. Freeze a reference model/data fingerprint and capture existing RESOLVE run
  settings, schedules, assumptions, and result locations.
3. Build an input registry: target, unit, role, source, range/distribution,
  dependency, owner, and review date for every input.
4. Define a KPI dictionary: calculation formula, time aggregation, unit, data
  source, and validation rule for each output.
5. Run or collect a reference set of current full-engine cases, including
  baseline, credible extremes, and known difficult/failed cases.
6. Measure runtime decomposition: queue, archive/copy, model load, RESOLVE run,
  result extraction, and human interpretation time.
7. Reconcile one cashflow calculation against an economics-owned spreadsheet.

**Deliverables:** decision charter, input registry, KPI dictionary, benchmark
case pack, runtime report, economics reconciliation sheet, and explicit known
limitations.

**Exit gate:** an engineer can rerun the reference cases and explain why a case
exists, what it means, and which assumptions can reverse the decision.

### Plan 1: Study Shell And Safe Compression

**Goal:** later create the smallest product vertical slice that turns a run batch
into a versioned, inspectable study without changing RESOLVE execution.

**Scope:** only discrete assumptions and current full RESOLVE tasks. No
probabilistic claims, ML, subsystem cuts, or automatic recommendations.

**Later implementation shape:**

- Introduce `Study`, immutable `StudyRevision`, `StudyCase`, and
  `CaseExecution` above the existing task model.
- Preserve `/v1/tasks/petex_start` for legacy users.
- Add a study launch path that materializes cases and uses the existing task
  event chain to create normal PETEX tasks.
- Add canonical case fingerprints, server-side dedupe, a hard run budget,
  deterministic case IDs, and a preflight report.
- Implement only exact reuse and declarative inactive-setting pruning.
- Present study progress while retaining links to existing task detail pages.

**Exit gate:** the Golden Decision Pack runs through the new shell with the same
technical outcomes as the legacy flow, fewer duplicate/inactive cases, and full
case provenance.

### Plan 2: Uncertainty Forecast And Economic Gate

**Goal:** produce a limited, reviewable uncertainty result for the Golden
Decision Pack.

**Scope:** one decision template; discrete weighted realizations plus triangular
or uniform scalar inputs; seeded Latin hypercube; one economics template.

**Work:**

1. Add input classification and distribution/weight capture.
2. Define realization bundles and common sampled drivers across decision arms.
3. Generate a frozen probability sample plan and retain its seed/weights.
4. Execute full RESOLVE cases and calculate technical KPIs/cashflows.
5. Report weighted distributions, stated exceedance conventions, sample quality,
  and failed-case treatment.
6. Enforce Economic Decision Studies entry and publication gates.

**Exit gate:** the output matches an approved reference calculation within agreed
tolerance, shows all assumptions and conventions, and cannot be published as a
recommendation without required reviews.

### Plan 3: Adaptive Pilot Without ML

**Goal:** prove that sequential selection reduces full-engine runs without
changing the decision for the Golden Decision Pack.

**Scope:** a fixed candidate pool, initial representative sample, and one
transparent scoring rule. Engineer approves every selected next batch.

**Work:**

1. Choose a scoring rule: coverage, sensitivity, constraint boundary, or
  decision disagreement.
2. Establish a high-fidelity run-credit budget and a stop rule before running.
3. Log every candidate score, selected case, rationale, and human override.
4. Keep adaptive runs separate from the frozen probability lane unless a valid
  weighting method is implemented.
5. Confirm final choice on designated representative full-engine cases.

**Exit gate:** the pilot reaches the same reviewed decision as the reference plan
with fewer high-fidelity runs, while preserving its constraints and audit trail.

### Plan 4: Narrow Surrogate And Validated Response Reuse

**Goal:** learn whether a narrow output surrogate or one component response
model can safely reduce run count further.

**Scope:** one output contract and one model family/revision. No universal AI
model and no automatic subsystem cutting.

**Work:**

1. Choose one stable target such as 5-year NPV, peak water, or facility margin.
2. Train and validate an uncertainty-aware surrogate on full-engine cases.
3. Measure error by operating regime and prediction-interval calibration.
4. Add out-of-domain detection and mandatory full-engine escalation.
5. Compare decision outcome and cost against the no-surrogate adaptive pilot.

**Exit gate:** held-out full-engine cases show acceptable accuracy and calibrated
uncertainty, and the decision remains correct under the documented guardrails.

### Plan 5: Native Physics Sandbox

**Goal:** establish evidence for or against a narrow native numerical capability.

**Scope:** synthetic, transparent, non-customer-critical steady-state network
benchmarks. This is separate from Decision Studies delivery.

**Work:** define equations, component closures, test cases, conservation checks,
convergence diagnostics, reference comparisons, and license boundaries before
selecting a production implementation language or dependency.

**Exit gate:** a benchmark report demonstrates where the sandbox is correct,
where it fails, its runtime profile, and whether it solves a measured product
problem better than study compression or existing engine integration.

## Decisions Needed Before Plan 0 Can Close

1. Select the first real decision and its accountable technical/economic owners.
2. Choose the approved model revision and allowed data handling boundary.
3. Agree the first economics template and review roles.
4. Decide whether the primary objective is expected NPV, downside protection,
  constraint compliance, or a documented combination.
5. Define what level of residual uncertainty is acceptable for that decision.

Those choices make the vision operational. Without them, the platform risks
becoming a large collection of technically impressive but decision-neutral runs.