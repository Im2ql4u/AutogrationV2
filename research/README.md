# Autogration Research Foundation

This directory is the durable research record for taking Autogration beyond a
PETEX execution and scenario-management layer. It records sources, separates
verified facts from hypotheses, and turns research into benchmarkable technical
decisions.

## Working terminology

The intended PETEX target in this research is **RESOLVE**: an integration,
workflow, scheduling, and optimisation platform. Autogration's current source
code explicitly exposes RESOLVE settings through OpenServer.

**REVEAL** is a separate specialised reservoir simulator with fully thermal,
finite-difference physics. It remains useful context for integrated reservoir
studies, but it is not what the initial "revolve" reference meant.

## Current falsifiable system model

**Hypothesis:** current Autogration owns study definition, scenario expansion,
task orchestration, and result handling; PETEX applications own the underlying
physical calculations.

Evidence collected on 2026-08-25:

- `prepare_petex_compute` creates one `PETEX_COMPUTE` task per assumption-set
  file and archives a PETEX project plus input data for the node.
- The RESOLVE settings catalog is composed of OpenServer tag/value overrides,
  including forecast mode, adaptive timesteps, and optimiser controls.
- The existing scenario design uses a Cartesian expansion of input choices,
  rather than an in-process residual/Jacobian solver.

The cheapest disproof is an in-house implementation that assembles and solves
the reservoir/network residual equations. It has not been found in the current
task-preparation and settings control path; the node-client review remains an
explicit follow-up item.

## What the public evidence already says

- GAP is presented by Petroleum Experts as a proprietary, equation-based
  **steady-state** multiphase production/injection network solver. Its model
  balances pressure, flow, and temperature across equipment and uses physical
  component models or pre-calculated responses.
- RESOLVE is presented as the layer that couples reservoir, well, network,
  process, and transient models over time. It offers adaptive timesteps,
  scenarios, probabilistic studies, workflows, and multi-level optimisation.
- REVEAL is presented as a fully thermal finite-difference reservoir simulator
  that solves coupled pressure-flow-temperature equations and can couple
  geomechanics/fractures.
- None of the public vendor material is sufficient to reconstruct the
  proprietary algorithms. It is evidence of observable capability, not a
  specification of the exact implementation.

## Research discipline

Every nontrivial statement in this directory should be one of:

1. **Autogration fact**: traced to source, a model file, or an observed run.
2. **Vendor claim**: documented public behavior, not an implementation detail.
3. **Open technical evidence**: reproducible theory or source from an open
   project or peer-reviewed publication.
4. **Hypothesis**: plausible but not yet demonstrated; paired with a cheap
   discriminating experiment.

Do not copy licensed manuals or scrape unofficial mirrors into this repository.
Store source metadata and original summaries instead.

## Priority order

| Priority | Question | Immediate deliverable |
| --- | --- | --- |
| P0 | What do GAP, RESOLVE, and REVEAL each solve and own? | Vendor/system boundary dossier |
| P0 | What equations, states, constraints, and algorithms must a credible independent solver represent? | Solver architecture note and benchmark plan |
| P0 | How can a study be reproducible, comparable, and economically decision-ready? | Uncertainty and decision framework |
| P1 | When is a subsystem run physically valid and materially cheaper? | Partitioning/interface contract |
| P1 | Where can ML accelerate work without becoming an uncalibrated source of engineering truth? | Surrogate and active-learning design |
| P2 | Which product slice should become Autogration's first native compute capability? | Evidence-backed build decision |

## Initial conclusion

The future opportunity is not "a faster Newton method" in isolation. It is a
reproducible, decision-aware computation system that can choose the smallest
physically defensible model, use PETEX or another trusted engine as a reference,
and spend expensive full-model runs only where they change a decision.

## Current Findings And Direction

### Long-term north star

Autogration should become a **decision-grade engineering computation platform**.
An engineer defines a decision, alternatives, constraints, uncertainty, and
available evidence. Autogration compiles that question into the smallest
defensible set of calculations, chooses eligible engines and fidelities,
requests more evidence where it matters, and produces a reproducible review
record.

```text
Decision question
  -> alternatives, constraints, and uncertainty
  -> calculation and evidence graph
  -> cheapest valid evaluators
  -> selective trusted full-physics execution
  -> quality, uncertainty, and decision checks
  -> reviewable engineering evidence
```

PETEX should remain a trusted integrated-physics stack rather than being
replaced prematurely. WhitsonPVT can become the controlled source of fluid
evidence and engine-specific PVT materializations. Autogration should own study
identity, calculation selection, execution evidence, validation, and the reason
each expensive calculation was required.

The mature product is a study compiler with a governed fidelity ladder:

```text
Exact approved result reuse
  -> validated table or interpolation
  -> approved well or facility response
  -> analytical or material-balance model
  -> reduced subsystem or numerical model
  -> trusted full RESOLVE/PETEX execution
```

Cheaper evaluators are local, revocable privileges. Cases must escalate to
trusted full physics near phase boundaries, events, active constraints,
extrapolated conditions, or decisions that remain difficult to distinguish.

### Immediate strategic focus: runtime

The first focused program is to optimize the current RESOLVE/PETEX execution
path. A small number of visible controls does not imply a small calculation. A
study's cost is approximately:

$$
T_{study} \approx \sum_{cases}\sum_{steps}
\left(T_{reservoir} + N_{GAP}T_{GAP} + T_{coupling} +
T_{optimisation} + T_{I/O}\right).
$$

The reviewed Autogration path creates one PETEX task per assumption set, applies
allowlisted OpenServer changes, and repeatedly invokes `RESOLVE.RUNONESTEP()`.
It currently provides an excellent external timing boundary but no durable
decomposition of step cost or PETEX's internal calculation counts.

Current official PETEX material establishes that RESOLVE offers reusable Data
Objects, PVT lumping/delumping, multilevel optimization, parallel scenario
workflows, and clustering/hyperthreading. GAP supports equation-based network
solving, nonlinear optimization, and compositional/black-oil PVT. It does not
publicly establish how those capabilities are configured, invalidated, or
scaled in our installed version.

The removed PETEX performance case points toward cumulative gains from parallel
Jacobian construction, cheaper PVT representation, Data Object reuse, moving
separator/property work out of repeated loops, and optimization reformulation.
Only parts of its reported timing sequence survive in indexed fragments. The
`3.7 s` endpoint and meaning of `0.5%` remain unverified, so neither is an
Autogration target or acceptance rule.

### Recommended first phase

Phase 1 combines two workstreams:

1. **Autogration-owned passive tracing:** add low-overhead, monotonic spans for
   queueing, transfer, model open, mutation, save/validation, each
   `RUNONESTEP`, extraction, upload, retry, and teardown without changing the
   executed model.
2. **PETEX-supported telemetry:** use licensed manuals and vendor support to
   identify documented timings, evaluation counts, convergence information,
   Data Object lifecycle, PVT representations, clustering, hyperthreading,
   restart, and optimizer controls available in the installed environment.

The external trace remains useful when internal fields are unavailable. It must
report an opaque `RUNONESTEP` bucket honestly rather than infer that GAP,
reservoir, optimization, or PVT dominated it.

Before any performance change, freeze representative typical, slow,
PVT/network-different, constraint-sensitive, and event-sensitive reference
cases. Give every case a complete model, data, PVT, settings, engine,
environment, and output fingerprint plus an engineer-owned acceptance contract.

### How runtime ideas will be proved

Candidate mechanisms include exact run avoidance, OpenServer lifecycle and
extraction improvements, supported session or Data Object reuse, case-level and
inner-loop parallelism, timestep/restart policy, approved well responses, PVT
child models, optimization/coupling changes, and relocation of invariant work.

They are selected from measured bottlenecks using Amdahl's law:

$$
S = \frac{1}{(1-f) + f/s},
$$

where $f$ is the measured runtime fraction affected and $s$ is that fraction's
candidate speedup. This prevents investment in an impressive optimization with
little possible end-to-end value.

Experiments use frozen baseline/candidate variants, randomized paired execution,
repeated runs, runtime confidence intervals, and explicit treatment of cold
start, warm start, queueing, licences, failures, and outliers. Timesteps from
one task are not treated as independent benchmark repetitions.

Every candidate is classified as:

- **PASS:** the performance threshold and every engineering hard gate pass;
- **FAIL:** a hard gate fails or performance is materially worse; or
- **INCONCLUSIVE:** telemetry, precision, comparability, or engineering evidence
  is insufficient.

Engineering acceptance includes schedule completion, warnings, timestep/event
behavior, phases, pressures, rates, cumulative volumes, balances where exposed,
well/facility/integrity constraints, optimization feasibility, and declared
decision KPIs. A candidate fails when a material constraint or decision changes,
even if average rate error is small.

### How successful optimization enters Autogration

There should be no global `fast mode`. The promotion path is:

```text
Documented hypothesis
  -> controlled benchmark
  -> accepted comparison evidence
  -> shadow use
  -> model-family runtime certificate
  -> opt-in ordinary execution
  -> possible default after operational evidence
```

A certificate binds a profile to benchmark, model family, PETEX and adapter
versions, PVT/materialization, hardware/licence context, output contract,
validity conditions, reviewers, and rollback. Dependency changes invalidate or
reopen the certificate. Exact reuse remains distinct from any approximate PVT,
response, timestep, or formulation change.

The first Autogration implementation should therefore be evidence plumbing:
structured traces, complete fingerprints, immutable benchmark and acceptance
specifications, comparison evidence, and optional backward-compatible task
links. It should not begin by changing solver settings, PVT, model formulation,
or application-session behavior.

No PETEX run, runtime benchmark, product implementation, or solver-setting
change has yet been executed under this program. The detailed destination is in
[the long-term north star](16-long-term-north-star.md); the complete mechanisms,
architecture, proof protocol, and Phase 1 work packages are in the
[PETEX runtime optimization proof program](17-petex-runtime-optimization-proof-program.md).

## Research map

1. [Autogration baseline](01-autogration-current-state.md): what the currently
  inspected product code does and does not demonstrate.
2. [PETEX/IPM boundary](02-petex-ipm-boundary.md): GAP, RESOLVE, REVEAL, and
  the limits of public evidence.
3. [Physics and solver architecture](03-physics-and-solver-architecture.md):
  the answer to the Newton-method question and a credible independent-solver
  path.
4. [Uncertainty and decisions](04-uncertainty-and-decision-engine.md): how to
  make shut-in, drill, and intervention decisions under uncertainty.
5. [Subsystems and multifidelity](05-subsystems-and-multifidelity.md): when a
  partial model is physically defensible.
6. [ML and adaptive studies](06-ml-and-adaptive-studies.md): where ML helps and
  where it must not be trusted alone.
7. [Benchmark and roadmap](07-benchmark-and-roadmap.md): ordered product and
  engineering bets.
8. [Decision-studies vision and first plans](08-decision-studies-vision-and-first-plans.md):
   product vision, smart-run compression, probability/economics gates,
   adaptivity, and staged delivery plans.
9. [Pillar 1: strengthen the current product](09-pillar-1-strengthen-current-product.md):
  the current-product reliability, reproducibility, and usability branch.
10. [Decision rights and engineering partnership](10-decision-rights-and-engineering-partnership.md):
    what is already agreed, what needs product-owner judgment, and what needs
    engineering co-design.
11. [Reference corpus and smart queues](11-reference-corpus-and-smart-queues.md):
    how historical Autogration evidence becomes a broad reference base, followed
    by operational queue intelligence and later one-by-one adaptive studies.
12. [WhitsonPVT integration and PVT engine](12-whitsonpvt-integration-and-pvt-engine.md):
  API and fluid-model integration, PVT uncertainty, multifidelity screening,
  and a measured native PVT-engine research path.
13. [Five WhitsonPVT maturity approaches](13-whitsonpvt-maturity-approaches.md):
  concise context, motivation, and product ideas for using WhitsonPVT to
  mature Autogration.
14. [Performance, PVT, and compute priority plan](14-performance-and-pvt-priority-plan.md):
  evidence-gated order for runtime measurement, PETEX experiments, WhitsonPVT,
  physically valid subsystem work, and advanced studies.
15. [Open performance opportunity map](15-open-performance-opportunity-map.md):
  discussion dossier that keeps acceleration branches open, grades the PETEX
  runtime evidence, and defines shared discriminating experiments.
16. [Long-term north star](16-long-term-north-star.md): the decision-grade
  engineering-computation destination, motivation, dependency-ordered phases,
  and principles for getting there.
17. [PETEX runtime optimization proof program](17-petex-runtime-optimization-proof-program.md):
  evidence-graded PETEX-like and additional runtime mechanisms, Autogration
  integration architecture, proof protocol, and viable Phase 1 approaches.
18. [Phase 1 runtime execution brief](18-phase-1-runtime-execution-brief.md):
  code-level runtime path, early hypotheses, measurement contract, decision
  gates, experiment routing, and proposed engineering working sessions.
19. [Goose, CDF, and Autogration run inspection](19-goose-cdf-run-inspection.md):
  governed agent and CDF retrieval patterns, current simulation-run discovery
  gap, executable result inspection, and the Power BI intake plan.
20. [Local access and reference inspection](LOCAL_ACCESS.md): multi-repository
    workspace, read-only localhost API inspection, and approved CDF access
    boundary.
21. [Source ledger](sources.md): the priority reading, talks, manuals, and
  acquisition queue.
22. [Alvheim tie-in study](21-alvheim-tie-in-study.md): with/without simulation
  design, value channels, settlement between licences and companies, hub vs
  company optimisation, data-science track, the study environment in
  `studies/alvheim-tiein`, and the stakeholder question log.
23. [Optimisation schemes and projects](22-optimisation-schemes-and-projects.md):
  what GAP optimises today (bookings and weights as the "nudge"), gates on the model
  before any recommendation, three selectable schemes (soften bookings as firm plus
  interruptible capacity, optimise the total then settle with a closed-form
  settlement, outer optimiser around Autogration), optional projects and an
  optimisation module in Autogration, phases and decisions needed.