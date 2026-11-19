# Open Performance Opportunity Map

Status: discussion dossier, 2026-09-09. This document deliberately does not
select an architecture or replace the priority posture in the companion notes.
It keeps the plausible acceleration paths open, identifies what evidence would
make each path sensible, and defines experiments that can eliminate weak ideas
before they become projects.

## The Question We Are Actually Asking

The useful question is not simply "how do we make RESOLVE faster?" It is:

> For each engineering question, what is the least expensive calculation that
> preserves the relevant physics, constraints, uncertainty, and decision?

That question has several possible answers. Some remove study cases, some make
the existing PETEX execution cheaper, some replace a bounded calculation with a
validated response, and some change how coupled systems exchange information.
They are complementary in some models and mutually exclusive in others. No
single answer should be chosen before runtime and dependency evidence exists.

The stable product boundaries remain:

| System | Present role |
| --- | --- |
| Reservoir simulator | Evolves reservoir pressure, saturation, composition, and well state. |
| PROSPER | Supplies well inflow/outflow and lift response. |
| GAP | Solves the steady-state multiphase production network and its constraints. |
| RESOLVE | Couples applications, schedule, scenarios, and optimisation through time. |
| WhitsonPVT | Supplies fluid evidence, QC, fluid-model development, and child models. |
| Autogration | Defines studies and cases, coordinates execution, and records evidence. |

Autogration currently invokes the trusted stack; it does not contain an
independent reservoir, network, or PVT solver. That is a useful starting point,
not a restriction on the research.

## Why A Small-Looking Model Can Be Slow

A few visible controls do not imply a small numerical problem. One requested
forecast can contain many scheduled steps, coupled iterations, optimisation
evaluations, network solves, hydraulic calculations, PVT/flash evaluations,
reservoir advances, retries, and result transfers:

$$
T_{study} = \sum_{c \in cases}\sum_{t \in steps}
\left(T_{reservoir} + n_{net}T_{network} + T_{coupling} +
T_{optimisation} + T_{I/O}\right).
$$

The visible count of chokes, rates, or assumptions describes only the outer
study controls. It says little about $n_{net}$, the nonlinear state dimension,
the number and cost of physical closure calls, or the number of times RESOLVE
asks an application to recalculate.

The first unresolved fact is therefore not "which solver is bad?" It is the
runtime attribution of representative real models.

## What The PETEX Performance Story Does And Does Not Establish

A removed PETEX case-study page is repeatedly cited in the working discussion
as a progression of approximately `344 -> 17.8 -> 10.5 -> 3.7 seconds`, which
would be close to a hundredfold end-to-end improvement. Publicly recoverable
material does not currently justify repeating that whole chain as verified
fact.

| Evidence | Current status | Permitted conclusion |
| --- | --- | --- |
| The original PETEX URL | Now returns 404 | The former page cannot currently serve as a citable primary source. |
| Internet Archive CDX lookup for that URL | No snapshot returned | There is no recovered archived page in the checked index. |
| Search-index fragments mentioning `344` and `17.8` seconds | Secondary remnant of vendor-authored material | One vendor example reported a large improvement associated with several interventions; exact conditions still need the original material. |
| Search-index fragments mentioning a `10.5` second calculation and roughly `3.5` minute optimisation | Secondary remnant of vendor-authored material | Repeated model evaluations can amplify a modest per-evaluation cost. |
| The `3.7` second endpoint | Not independently recovered | Keep it as an unverified working lead. |
| The meaning of `0.5%` | Not independently recovered | Do not claim that it is rate error, objective error, accuracy loss, or runtime share. |
| Current PETEX product pages | Available official descriptions | They establish product capability and boundaries, not the removed benchmark's method or result. |

The fragments and prior summary indicate a *stack* of interventions rather than
one hidden algorithm: parallel Jacobian construction, simplification or lumping
of PVT work, reuse of Data Objects, moving separator-related work out of a hot
loop, and optimisation/model reformulation. Until the source is lawfully
recovered, those details are research leads, not a recipe and not a benchmark
for Autogration.

The responsible claim is:

> PETEX published a case indicating that very large speedups can arise from
> cumulative changes to derivative construction, physical evaluations, data
> reuse, and formulation. The exact timing ladder, accuracy comparison, model,
> hardware, and meaning of `0.5%` remain unverified.

The best next source is the organisation's licensed PETEX support, training, or
user-meeting channel. Ask for the removed case study, its figures or table, the
software version, model description, hardware, and definition of every error
metric.

## Three Scales Of Acceleration

Keeping these scales separate prevents an impressive result at one layer from
being mistaken for another.

| Scale | Basic move | Possible examples | Main failure mode |
| --- | --- | --- | --- |
| Study scale | Ask fewer expensive questions | Deduplication, applicability pruning, DOE, adaptive batches, exact result reuse | Missing a material interaction, tail, or constraint |
| Execution scale | Make a full trusted-engine case cheaper | Session reuse, warm starts, timestep policy, optimiser cadence, cached response data, PVT child model | Changing behavior without detecting it |
| Physics scale | Evaluate a smaller or different model | MBAL/streamline screening, response surface, subsystem solve, reduced model, native kernel | Invalid boundary or validity envelope |

Parallel execution is a throughput multiplier across these scales, not proof
that any individual calculation is cheaper. Licence capacity, memory, archive
I/O, and shared services can make naive concurrency slower or less reliable.

## Open Opportunity Branches

### 1. Runtime attribution and calculation accounting

Instrument case setup, each `RUNONESTEP`, externally visible reservoir and GAP
work, optimisation, extraction, retry, queue, and teardown. Record counts as
well as durations. Where PETEX does not expose internals, say "unavailable"
rather than infer them.

**Becomes compelling when:** a small number of stages explain most wall time and
repeat consistently.

**Loses priority when:** timing is too unstable or opaque to associate a change
with a component. The immediate task then becomes better observation, not a
solver intervention.

### 2. Study compilation and run avoidance

Treat the Cartesian expansion as one possible design, not the definition of a
study. Canonicalize exact cases, remove inapplicable combinations, reuse only
complete fingerprint matches, and offer explicit full-factorial, sensitivity,
screening, and probability-sampling modes.

**Becomes compelling when:** historical runs contain duplicates or inactive
dimensions, or a held-out DOE preserves conclusions with substantially fewer
full cases.

**Fails when:** omitted interactions change a decision, miss a binding
constraint, or distort a declared probability sample.

### 3. PETEX workflow and formulation experiments

Use one-factor controlled experiments around schedule/timestep behavior,
optimiser frequency and tolerances, warm/restart state, pre-calculated well
responses, Data Object reuse, separator/property work, and documented PVT
representations. This branch should be run with PETEX engineering support when
the setting changes internal behavior.

**Becomes compelling when:** the baseline attributes material time to the
affected loop and repeated runs show a stable saving.

**Fails when:** convergence, mass/pressure balance, phase behavior, facility
constraints, or decision KPIs leave the approved tolerance.

### 4. PVT as both evidence and a fidelity controller

WhitsonPVT can support several distinct products:

- immutable source, sample, QC, model, and export provenance;
- change-impact analysis when a sample or parent EOS is revised;
- pressure-temperature-composition operating-envelope preflight;
- coherent PVT uncertainty realizations;
- detailed, lumped-EOS, and black-oil child-model comparisons;
- cross-engine property and phase-behavior tests; and
- a future transparent table/flash validation kernel.

The interesting acceleration idea is not a remote Whitson call inside every
network iteration. It is a versioned local materialization selected by a
declared fidelity policy. Stable, single-phase regions may admit a cheap child
model; phase-boundary, critical, compositional, or extrapolated states should
escalate to the detailed representation.

**Becomes compelling when:** PVT/flash work is material, a child model gives a
measurable saving, and property plus decision-KPI tests define a useful validity
envelope.

**Fails when:** the API/export contract cannot reproduce an immutable artifact,
or the cheaper model changes phase, constraints, or decisions in the intended
operating range.

### 5. Well and network response reuse

PROSPER already represents inflow/outflow responses, and GAP can use
pre-calculated responses. This suggests testing immutable response artifacts
for wells or bounded network components instead of repeating unchanged detailed
calculations.

**Becomes compelling when:** dependency tracing shows that many cases leave the
response inputs unchanged or within a demonstrably smooth range.

**Fails when:** composition, lift, temperature, facility pressure, reservoir
state, or control changes invalidate the response more often than expected.

### 6. Reservoir fidelity ladder

The reservoir side need not be a binary choice between full simulation and no
reservoir. Depending on the engineering question, candidates include a frozen
boundary, analytical IPR, MBAL tank or multi-tank material balance, streamline
screening, a reduced numerical model, or the full simulator. REVEAL and GAP
Transient also show that specialised transient or multiphysics questions may
need *more* fidelity than an ordinary steady-state forecast, not less.

**Becomes compelling when:** reservoir work dominates and a lower-fidelity
representation preserves the relevant pressure, deliverability, breakthrough,
and decision response over a declared horizon.

**Fails when:** spatial effects, communication, displacement, phase change,
geomechanics, or event timing drive the decision.

### 7. Exact islands, boundary responses, and iterative co-simulation

Separate execution has four materially different meanings:

1. A truly disconnected component with no physical, control, or shared-resource
   path.
2. A local solve under a fixed external pressure/rate/temperature/composition.
3. An omitted domain replaced by a calibrated boundary-response model.
4. Two domains exchanging interface values until residuals converge.

Low output correlation is only a clue. It does not prove any of these. Shared
manifolds, facility constraints, compression, gas lift, recycle, composition
blending, reservoir communication, and scheduled events can create decisive
coupling even when historical correlations look small.

**Becomes compelling when:** full-model perturbations show low and bounded
interface sensitivity, or iterative exchange converges cheaply and reliably.

**Fails when:** interface residuals, event responses, active-set changes, or
held-out full-model KPIs exceed tolerance.

### 8. Optimisation restructuring

If many expensive physical evaluations occur only to support an outer
optimiser, the best intervention may be formulation rather than physics:

- reduce or stage the control set;
- optimize only when state or active constraints materially change;
- use a cheap response for candidate search and full physics for confirmation;
- separate discrete routing choices from continuous control refinement; or
- warm-start from nearby schedule and scenario states.

**Becomes compelling when:** optimisation/coupling accounts for repeated GAP or
reservoir evaluations and nearby cases have reusable structure.

**Fails when:** warm starts are unreliable, active constraints switch sharply,
or the restructured search loses the best feasible solution often enough to
alter a decision.

### 9. Case-level and inner-loop parallelism

Autogration can schedule independent cases across available workers. PETEX's
historical material also points to parallel derivative work inside a network
calculation. These are different experiments with different owners.

**Becomes compelling when:** workers, licences, memory, and storage scale without
contention, or PETEX exposes a supported inner-loop setting for the measured
bottleneck.

**Fails when:** licence waits, model startup, transfer, memory pressure, or
nondeterministic failures consume the apparent gain.

### 10. Native and open compute

There are several independent native targets, not one giant "replace PETEX"
project: case compiler, PVT artifact validator, table evaluator, response-model
service, synthetic network kernel, coupling laboratory, or reservoir-reduction
research using OPM/MRST references.

**Becomes compelling when:** a narrow target has a stable contract, open theory,
reference data, high call volume, and a clear validation set.

**Fails when:** matching proprietary edge behavior becomes the project, or the
target cannot be trusted without routinely rerunning the full stack.

### 11. Decision-directed adaptive studies

After the evidence contract is sound, Autogration can choose the next case based
on coverage, sensitivity, constraint proximity, uncertainty, or disagreement
between decision alternatives. This can coordinate any mixture of trusted full
engines and approved lower-fidelity evaluators.

**Becomes compelling when:** a fixed initial design leaves a large candidate
space and held-out tests show that sequential selection reaches the same
decision with fewer expensive calls.

**Fails when:** adaptive samples are mistaken for probability samples, the
acquisition rule hides unfavorable regions, or results cannot be reproduced
from the logged sequence.

## More Ambitious Combinations Worth Testing

These ideas become "very cool" only if the underlying contracts remain visible
and reversible.

### A study compiler with a fidelity ladder

Compile a decision question into a calculation graph. Each node declares its
inputs, dependencies, cost estimate, validity envelope, and available
evaluators. Autogration selects the cheapest eligible evaluator, records why,
and escalates when a boundary, uncertainty, or constraint is approached.

This combines exact reuse, Whitson-informed PVT validity, response artifacts,
reservoir fidelity, and full RESOLVE confirmation without pretending they have
equal evidential status.

### Shadow-mode trust accumulation

Run a candidate cheap evaluator beside selected full-engine cases without using
it to make the production decision. Build an error map by operating regime,
phase state, active constraint, and model revision. Promotion is local to a
validated envelope and automatically withdrawn when dependencies change.

### Reversible subsystem islanding

Construct a physical/control dependency graph, propose an island, perturb its
interfaces in the full model, and estimate the induced decision error. Choose
independent, fixed-boundary, response, iterative, or full coupling from those
tests. The system can escalate an island back into the full solve when interface
residuals or event conditions leave the certificate.

### Decision-error budgeting

Allocate an explicit error budget across PVT representation, reservoir
reduction, response interpolation, subsystem boundary, numerical tolerance, and
sampling. Spend high fidelity where the combined uncertainty could change a
constraint or decision, rather than demanding uniform accuracy everywhere.

This is a research direction, not yet a defensible production algorithm. Error
dependencies and non-smooth active constraints make naive addition unsafe.

## Shared Benchmark Spine

The branches should compete on the same frozen evidence rather than each using
a favorable demonstration.

### Reference cases

Use at least:

- a typical successful integrated forecast;
- a slow or convergence-heavy case;
- a materially different PVT/network case;
- a coupling-sensitive event or constrained case; and
- later, a small synthetic model whose expected balance and response can be
  inspected independently.

### Measurements

For each run preserve:

- immutable model, data, PVT, settings, engine/version, and output fingerprints;
- queue, setup, step, reservoir, network, optimisation, extraction, and teardown
  timings when observable;
- calculation, iteration, retry, warning, and failed-step counts;
- timestep sequence and event/control changes;
- pressure/material balance and convergence measures when available;
- well, facility, phase, and integrity constraints;
- declared technical and decision KPIs; and
- hardware, licence, worker, and run-order context.

Repeated baselines are required. A speedup smaller than ordinary run-to-run
variation is not a result.

### Acceptance is decision-specific

Do not use one global percentage such as the unrecovered `0.5%`. Before an
experiment, the engineer declares tolerances for the relevant quantities and
hard no-cross conditions. A candidate fails if it changes a binding constraint,
phase regime, feasible decision set, or preferred alternative beyond that
contract, even when its average production error is small.

## Discriminating Experiment Matrix

| Observation from the shared baseline | First cheap experiment | Branches strengthened by success | Branches weakened by failure |
| --- | --- | --- | --- |
| Many generated cases are duplicate, inactive, or dominated | Replay a completed study with canonicalization and declarative pruning | Study compilation, queueing, exact reuse | Solver replacement as the first move |
| GAP/network time dominates each step | Compare documented PVT/response/formulation variants one at a time | PVT ladder, response reuse, PETEX tuning, inner-loop parallelism | Reservoir-first reduction |
| Reservoir time dominates | Compare timestep policy and one approved lower-fidelity reservoir representation | Reservoir ladder, adaptive fidelity | Network/PVT-first work |
| Coupling or optimisation repeats expensive solves | Change cadence on a frozen case and count evaluations | Optimisation restructuring, warm starts, response-assisted search | Pure case-level scaling alone |
| Setup/extraction dominates short cases | Reuse a supported session/data object and batch output retrieval | Execution lifecycle optimisation | Physics rewriting |
| PVT child model agrees over the actual envelope | Shadow detailed versus child materializations in integrated cases | Whitson fidelity controller, local PVT cache | Live detailed PVT everywhere |
| Full-model interface perturbations have bounded low impact | Run a held-out fixed-boundary or response experiment | Subsystem islanding, response models | Monolithic-only execution |
| Interface feedback is material but contractive | Test relaxed iterative exchange and residual stopping | Co-simulation | Independent subsystem execution |
| Worker throughput scales nearly linearly | Increase controlled case concurrency under fixed licence/storage conditions | Parallel study execution | Premature case compression for throughput alone |
| A decision boundary occupies a small part of the domain | Compare adaptive selection with a frozen held-out design | Decision-directed studies, multifidelity allocation | Uniform full-factorial exploration |

An experiment may strengthen more than one branch. That is desirable: the goal
is to learn the shape of the opportunity before selecting the build.

## A Conditional Research Queue, Not A Roadmap

The following order buys information while preserving optionality:

1. Recover the PETEX source through licensed channels and define what remains
   unknown if it cannot be recovered.
2. Capture repeated, stage-level traces for representative real cases.
3. Build one common comparison report and acceptance contract.
4. Run the cheapest one-factor experiments indicated by those traces.
5. In parallel, prove the WhitsonPVT read/export/version boundary in a read-only
   sandbox because it affects provenance as well as performance.
6. Promote only the branches that survive held-out full-engine comparison.

This sequence chooses measurements, not an eventual architecture. Depending on
the evidence, the best result could be mostly study compression, a better PETEX
workflow, a PVT hierarchy, reservoir reduction, response reuse, subsystem
coupling, parallel capacity, a narrow native service, or a combination.

## Questions For The Joint Engineering Discussion

1. Which three real studies represent typical, slow, and materially different
   behavior, and which outputs actually determine their engineering decisions?
2. Can PETEX expose per-application time, evaluation counts, iteration counts,
   convergence state, and supported cache/restart controls through the licensed
   interface?
3. Which physical models and PVT representations are used in those studies,
   and where are their source and revision identities recorded today?
4. Which constraints are hard gates even when headline rate or NPV changes very
   little?
5. Which suspected weak connections can be perturbed safely in a full model to
   measure interface sensitivity?
6. Which existing result corpus contains enough provenance to support replay or
   held-out comparison, and which must be rerun?
7. What worker, licence, memory, and storage limits determine realistic
   parallel throughput?
8. Who can request the removed PETEX benchmark and a WhitsonPVT API/export
   sandbox through the organisation's vendor relationships?

## Evidence Classification

- **Autogration fact:** traced to the reviewed sibling source path.
- **Current vendor evidence:** an official page or manual that establishes a
  product capability or supported boundary.
- **Historical/indexed vendor evidence:** a fragment of formerly published
  vendor material; useful as a lead, insufficient for exact quantitative claims.
- **Open technical evidence:** inspectable open software, documentation, or
  peer-reviewed theory.
- **Hypothesis:** a proposed performance or product mechanism paired with a
  falsifying experiment.

Supporting detail is maintained in the Autogration baseline, PETEX boundary,
subsystem, WhitsonPVT, performance-priority, and source-ledger notes. This
dossier should change as measurements close branches; it should not be edited
to make the surviving idea appear inevitable in hindsight.