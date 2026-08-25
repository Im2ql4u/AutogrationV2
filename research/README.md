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
9. [Source ledger](sources.md): the priority reading, talks, manuals, and
  acquisition queue.