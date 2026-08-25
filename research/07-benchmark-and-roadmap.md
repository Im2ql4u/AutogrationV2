# Benchmark and Roadmap

## Strategic thesis

Autogration should become the decision and computation fabric around reservoir,
well, network, facility, and economic models. It should be engine-neutral where
possible, fidelity-explicit everywhere, and capable of progressively owning
native calculations only where it can prove value and validity.

The moat is not a cloned proprietary solver. It is a trusted study record and
decision loop that makes all solvers more useful.

## Ordered bets

### 1. Make each study reproducible and economically legible

Build semantic case fingerprints, a versioned full-study specification, run
budget/cost estimates, complete input/result provenance, and an economic-output
contract. This immediately improves existing PETEX work and is prerequisite
infrastructure for every later capability.

**Gate:** an engineer can reproduce a past recommendation, see every model and
economic assumption used, and identify why two cases differ.

### 2. Replace Cartesian-only studies with DOE and uncertainty plans

Add bounded full-factorial, screening, one-at-a-time, Latin-hypercube, weighted
ensemble, and seeded random plans. Introduce distributions, correlation groups,
and weighted result aggregation.

**Gate:** a study can report an outcome distribution and probability of a named
constraint/NPV event without pretending a sweep is a probability distribution.

### 3. Add adaptive sequence management

Use case runtime, result quality, sensitivity, and decision uncertainty to select
the next calculations. Initially use transparent heuristics; only later add
surrogate acquisition functions.

**Gate:** a held-out decision study reaches the same recommendation with fewer
high-fidelity calls and a recorded stopping rationale.

### 4. Introduce verified reuse and multifidelity

Start with cache validity and response-model contracts, then fixed-boundary local
studies. Add iterative co-simulation only after interfaces, residuals, and
validation suites exist.

**Gate:** reduced runs have an explicit validity envelope and preserve approved
full-model decisions in the benchmark suite.

### 5. Build a native physics sandbox, not a production replacement

Create transparent benchmark networks and a small residual/automatic-
differentiation kernel. Use it to learn, validate interfaces, and establish an
independent capability. Use OPM/MRST as inspectable reservoir references.

**Gate:** conservation, convergence, and KPI acceptance criteria are passed on
versioned benchmarks before any customer-critical use.

## Benchmark hierarchy

| Tier | Purpose | Reference |
| --- | --- | --- |
| Unit physics | Verify component closures and units | Analytic/hand-calculated cases |
| Network | Verify balance, constraints, and optimisation | Synthetic transparent networks |
| Reservoir | Verify fully implicit dynamic behavior | OPM/MRST public examples |
| Coupling | Verify interface mass/pressure/composition behavior | Small coupled synthetic model |
| Engine comparison | Verify decision KPI agreement | Approved PETEX reference models |
| Decision | Verify economics and risk recommendation | Frozen historical or synthetic study packs |

Metrics must include mass/energy balance, residuals, Newton/linear iterations,
runtime, failure taxonomy, KPI error, interval calibration, and decision regret.

## Core architectural boundary

Adopt an execution-adapter contract:

```text
StudyPlan -> Case -> ExecutionAdapter -> Outcome
                         |                 |
                         v                 v
                 PETEX / OPM / proxy   KPIs / diagnostics / provenance
```

Every adapter declares:

- input schema and supported physics;
- fidelity level and validity envelope;
- solver version/settings and data dependencies;
- resource/cost estimate;
- result schema, residual/quality diagnostics, and failure taxonomy; and
- whether it can participate in adaptive or partial execution.

That turns PETEX from the product boundary into one trusted adapter and gives
native capability a home without destabilising current workflows.

## Evidence backlog before a native-solver commitment

1. Obtain official licensed manuals, release notes, examples, and OpenServer
   documentation through approved channels.
2. Capture a small set of anonymised real-model study traces: input changes,
   runtime, warnings, outputs, and decisions.
3. Build the synthetic benchmark pack and publish acceptance criteria.
4. Measure where time and engineering effort are actually spent: setup,
   convergence, PVT/flash, workflow logic, licensing/queueing, interpretation,
   or reruns.
5. Select the first decision workflow and success measure with reservoir,
   production, facilities, and economics stakeholders.

## The decision rule

Do not invest in a native solver merely because the equations look tractable.
Invest when a measured bottleneck or missing capability cannot be solved more
cheaply by better study design, model reduction, caching, engine integration, or
an open reference engine, and when the native slice has a testable validation
envelope.