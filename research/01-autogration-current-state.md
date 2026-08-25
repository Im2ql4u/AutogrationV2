# Autogration Baseline

Status: initial source review completed 2026-08-25. This note records only what
was directly observed in the sibling `autogration` and `autogration_frontend`
repositories. It is not a claim about every implementation path.

## Current execution unit

The current system is an execution and study-definition layer around PETEX:

1. The frontend expands selected assumption values into a Cartesian product.
2. The backend creates one `PETEX_COMPUTE` task per generated assumption set and
   archives the PETEX project and associated data files for that task.
3. The node client applies model, schedule, RESOLVE, and module overrides through
  allowlisted OpenServer `DoSet` calls.
4. The active reviewed executor saves and validates the model, then invokes
  `RESOLVE.RUNONESTEP()` until the RESOLVE schedule end date.
5. The client checks solver errors and reads RESOLVE scenario-result time series
  back through OpenServer.

The relevant reviewed surfaces were:

- `apps/backend/.../prepare_tasks/petex.py`: creates and archives PETEX compute
  tasks.
- `shared/models/models/assumptions.py`: defines one sparse `AssumptionSet` per
  simulation case.
- `shared/models/models/resolve_settings.py`: exposes RESOLVE OpenServer
  settings, including timestepping and optimisation controls.
- `apps/nodeclient/.../task_execution/petex.py`: applies overrides, steps
  RESOLVE through its schedule, captures step results, and checks errors.
- `apps/nodeclient/.../ipm_client/utils.py`: applies OpenServer settings and
  retains a legacy helper containing a full `RESOLVE.RUN()` call.
- `apps/nodeclient/.../ipm_client/scenario.py`: reads RESOLVE scenario results.

## Demonstrated capabilities

| Capability | Evidence |
| --- | --- |
| Property, schedule, and structural overrides | `AssumptionSet` includes sparse nodes, new nodes, topology, schedules, and module operations. |
| Run-level RESOLVE configuration | Catalogued OpenServer settings include forecast mode, fixed/adaptive timesteps, and optimiser parameters. |
| Parallel independent cases | The backend creates one PETEX compute task per assumption set. |
| Scenario-result capture | The node client enumerates RESOLVE modules, published variables, and scenario-result series. |
| Full-factorial studies | The frontend design notes describe Cartesian expansion of selected values. |

## Not demonstrated by the reviewed surfaces

These are deliberately phrased narrowly. A deeper repository review or a live
model may disprove any item.

- An in-house assembly of reservoir or production-network residual equations.
- An in-house nonlinear, linear, or optimisation solver replacing PETEX.
- A probabilistic input model with distributions, correlations, posterior
  weights, or statistical aggregation of outcomes.
- A graph-level scheduler that executes only a physically isolated subsystem.
- A native economic decision model connecting costs, value, risk, and actions.
- A design-of-experiments planner beyond Cartesian expansion.

## Immediate product implication

Autogration already has the beginning of a study compiler: it maps a study
definition to concrete, executable cases. The best next abstraction is not
another form editor. It is a versioned **study specification** that also owns:

- semantic case identity and provenance;
- uncertainty distributions and correlation groups;
- sampling/DOE strategy and random seed;
- solver/fidelity selection;
- economic assumptions and decision criteria; and
- result quality, validation, and reuse metadata.

That lets the same study run through PETEX today, an analytical proxy tomorrow,
and a native solver only when its validation envelope permits it.

## Falsifiable follow-up

**Hypothesis:** every currently submitted PETEX case advances the full linked
RESOLVE model through each scheduled step.

**Cheap discriminating check:** trace the active node-client task entrypoint to
the reviewed executor, then run a small instrumented PETEX model with one local
override and inspect which linked modules receive calculation calls. Do not
infer runtime scope only from the presence of a command wrapper.