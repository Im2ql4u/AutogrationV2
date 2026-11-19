# Performance, PVT, And Compute Priority Plan

Status: consolidation for discussion, 2026-09-09. This turns the current
research into an evidence-gated order of work. It is not a claim that PETEX's
internal algorithms are known, nor approval to change a production model.

## The System We Have Today

Autogration is presently a study-definition and execution layer around PETEX.
It expands assumptions into PETEX compute tasks, applies allowlisted OpenServer
overrides, advances RESOLVE one scheduled step at a time, and collects scenario
results. It does not currently own a reservoir, PVT, or production-network
solver.

The model roles must remain separate:

| System | Question it answers | Role in the near-term architecture |
| --- | --- | --- |
| Reservoir simulator | How do pressure, saturation, composition, and wells evolve underground over time? | Trusted dynamic physics engine. |
| PROSPER | What is the well's inflow/outflow and lift response? | Well-response and closure model. |
| GAP | Given wells, pipes, equipment, PVT, and controls, what steady-state network pressure, flow, and temperature balance is feasible? | Trusted surface-network physics engine. |
| RESOLVE | How do reservoir, well, network, process, schedule, and optimization models exchange conditions through time? | Integrated workflow and coupling engine. |
| WhitsonPVT | What is the fluid model and how credible is its phase/property behavior? | Authoritative PVT evidence and model-artifact provider. |
| Autogration | Which cases should run, with which frozen assumptions and evidence, and what can be concluded from them? | Study compiler, execution coordinator, and decision-evidence record. |

The future target is therefore not a new GAP first. It is a more intelligent
Autogration around trusted engines, with a versioned fluid boundary and a
measured route to cheaper calculations.

## Why Runtime Can Be High Despite Few Visible Controls

The apparent decision degrees of freedom, such as choke settings and well
rates, are not the computational state count. A forecast repeatedly evaluates
reservoir states, well responses, nonlinear network hydraulics, phase/PVT
properties, active constraints, and optimization/coupling logic at many
timesteps. A useful workload model is:

$$
T_{study} \approx \sum_{cases} \sum_{steps}
  (T_{reservoir} + N_{network} T_{GAP} + T_{coupling} + T_{I/O}),
$$

where a network evaluation may itself contain many multiphase hydraulic and
PVT/flash evaluations. Vendor material reports that Jacobian construction and
physical closure evaluations can dominate the network linear solve in at least
one GAP case study. This is useful direction, not proof that the same component
dominates an Autogration model.

The local hypothesis is therefore:

> The highest near-term savings will come from fewer redundant full-engine
> executions and fewer expensive physical evaluations per execution, rather
> than from replacing the outer nonlinear algorithm.

**Cheap disproof:** instrument one representative RESOLVE forecast and show
that an irreducible reservoir calculation dominates wall time while case
duplication, setup, network calls, and extraction are negligible. That result
would redirect the work toward reservoir-model configuration or an approved
lower-fidelity reservoir representation.

## Priority 0: Establish A Performance Baseline

Do this before attempting a solver rewrite, a live Whitson call from a solver,
or automatic partitioning.

1. Select three approved, non-sensitive reference cases: a typical successful
   forecast, a slow/convergence-heavy forecast, and a model with materially
   different PVT or network complexity.
2. Freeze their model, data, OpenServer settings, requested outputs, and
   machine/licence context. Record the full case fingerprint.
3. Add durable timing and count telemetry around the existing execution path:
   archive/setup, OpenServer mutation, each RESOLVE step, reservoir execution,
   GAP/network execution when externally observable, optimization, result
   extraction, errors/retries, and queue time.
4. For each step, capture timestep size, coupling/optimization settings,
   warnings, convergence status, and counts of externally visible calculation
   commands. Where PETEX does not expose an internal count, record it as
   unavailable rather than estimating it as fact.
5. Produce a baseline report of wall time, cost/queue time, failure modes, and
   decision KPIs. Repeat each case sufficiently to separate run-to-run noise
   from an actual change.

**Exit gate:** at least 80% of end-to-end wall time is attributed to observable
stages, and the team can state whether the first bottleneck is case volume,
reservoir work, network/PVT work, optimization/coupling, or operational I/O.

## Priority 1: Eliminate Waste Around The Existing Engine

These improvements increase useful throughput regardless of which physical
engine later dominates.

| Work | Expected value | Proof before reuse or pruning |
| --- | --- | --- |
| Semantic case fingerprint and typed canonicalization | Remove exact duplicate cases and make reruns reproducible | Fingerprint includes model/data/PVT/settings/output contract and demonstrates identical result reuse. |
| Declarative applicability rules | Avoid combinations known to be inactive or contradictory | Engineer-approved rule, visible explanation, and a regression case for each rule. |
| Full-study provenance and result-quality record | Make expensive outputs comparable and usable as future reference evidence | A past reference recommendation can be reproduced and explained. |
| Run-budget admission and smart queue | Avoid opening a large batch before baseline/validation evidence exists | Policy-backed hold/release states; queue priority does not change the frozen sample. |
| DOE instead of Cartesian default | Learn from materially fewer cases | Held-out comparison preserves the stated engineering conclusion and constraint findings. |

The first study modes should be explicit: small full factorial, quick
sensitivity, engineer-reviewed screening, and seeded uncertainty sampling.
Screening or adaptively selected rows must not be labelled as probability
results. Probability outputs require declared distributions or weighted,
coherent realizations.

## Priority 2: Run Controlled PETEX Performance Experiments

Only after the baseline identifies a bottleneck, form a small experiment matrix
around the approved reference cases. Change one performance lever at a time,
compare with the frozen baseline, and preserve the model/result artifacts.

Candidate levers, subject to PETEX documentation and engineer approval, are:

- timestep and event policy, warm starts, continuation, and restart behavior;
- optimizer frequency, controls, constraints, and tolerances;
- reuse of unchanged approved response data or results;
- network/PVT representation, including validated detailed, lumped, and
  black-oil child-model materializations; and
- model formulations that remove an unnecessary calculation from the inner
  loop without changing the physical question.

Vendor examples of large speedups and small KPI differences are hypotheses for
this experiment, not acceptance criteria. The acceptance table must contain
runtime, completed/failed steps, material/pressure balance where available,
well/facility constraint changes, PVT-property agreement, and decision-KPI
error. A speedup is rejected when it crosses an engineer-defined decision or
constraint tolerance, even if its average rate error appears small.

## Priority 3: Make WhitsonPVT A Versioned Fluid Boundary

WhitsonPVT should not be queried remotely in a nonlinear GAP or RESOLVE inner
loop. A remote call increases latency and availability risk, and its documented
public API surface is tenant-specific. Instead use this pipeline:

```text
WhitsonPVT source/QC/model revision
  -> immutable Autogration PVT snapshot and realization
  -> local engine-specific materialization plus property checks
  -> GAP/RESOLVE or other trusted execution adapter
  -> outcomes linked back to the source revision
```

The first WhitsonPVT value is more than data synchronization:

1. **PVT provenance and impact analysis.** Link samples, QC, EOS/viscosity
   choices, component mapping, child model, and exported artifact to every
   case. A changed parent model can identify affected prior studies.
2. **Operating-envelope preflight.** Screen planned pressure, temperature, and
   composition paths for extrapolation, phase-envelope proximity, or
   incompatible black-oil-table assumptions before expensive execution.
3. **Cross-engine compatibility tests.** Compare composition, saturation
   pressure, density, viscosity, phase split, tables, one-well response, then a
   small network before comparing full forecasts.
4. **Coherent PVT uncertainty bundles.** Run named EOS/viscosity/
   characterization alternatives that retain their compatible assumptions;
   do not independently sample correlated PVT properties into unphysical
   combinations.
5. **Multifidelity PVT screening.** Use the detailed parent model for QC and
   targeted checks while a validated child model handles repeated, lower-cost
   calculations inside its declared pressure-temperature-composition range.
6. **A future transparent PVT validation engine.** Start with parsing,
   fingerprinting, table validation, interpolation, and out-of-range refusal;
   only later research a cubic-EOS flash kernel against approved references.

**Whitson feasibility gate:** a read-only vendor sandbox must prove the actual
available endpoints, stable identifiers/revisions, permitted export formats,
and target-engine import route. A three-condition pilot passes only when an
engineer can regenerate the same materialization and explain any property
mismatch. Credentials remain outside task archives, logs, and source control.

## Priority 4: Reduce Scope Only With A Physical Interface Contract

The idea of running disconnected or weakly interacting portions separately is
sound, but correlation is evidence for investigation, not a licence to split a
model. The omitted domain becomes a boundary condition.

Start in this order:

1. Exact reuse where the complete dependency fingerprint is unchanged.
2. Truly disconnected assets, after checking physical, material, control, and
   shared-resource paths.
3. Fixed-boundary local responses, only after full-model perturbations bound
   the effects of interface pressure, rate, temperature, composition, and
   control availability.
4. Tabulated/calibrated boundary-response models with validity ranges and
   uncertainty bands.
5. Iterative co-simulation with interface residuals for weakly coupled models.

Shared manifolds, facilities, compression, gas lift, recycling, composition
blending, reservoir communication, and schedule events usually prohibit an
independent claim. Every partition must declare exchanged quantities, units,
cadence, coupling tolerance, residual history, escalation rules, and full-model
spot checks at base, extreme, and event cases.

**Exit gate:** reduced execution preserves the approved conclusion and all
material constraints for a held-out reference set, with a recorded validity
envelope. An arbitrary graph cut is never a valid engineering result by itself.

## Priority 5: Grow Advanced Studies On The Measured Foundation

Once case identity, quality, PVT provenance, runtime telemetry, and a reference
corpus are reliable, Autogration can mature into the desired analysis system:

- weighted reservoir/PVT/operational realization ensembles;
- uncertainty distributions and stability checks for named KPIs;
- common uncertainty samples across decision alternatives;
- transparent one-by-one adaptive case selection based on coverage,
  sensitivity, constraint proximity, and decision disagreement;
- local uncertainty-aware response surrogates, verified against full-engine
  cases and never used outside their validity domains; and
- a native physics sandbox using transparent synthetic benchmarks and open
  references before any production-critical native calculation.

This ordering matters: a fast, opaque ensemble of ambiguous cases does not
become decision evidence merely because it has percentiles or an ML model.

## Recommended First Three Deliverables

1. **Reference-run performance dossier:** instrumented traces and a ranked
   bottleneck statement for three frozen cases.
2. **Case and PVT evidence contract:** a study/case fingerprint that can later
   include PVT materialization identity, exact reuse, and change-impact links.
3. **WhitsonPVT read-only sandbox and three-condition compatibility pilot:**
   establish the real integration boundary before committing to a connector.

These three deliverables answer the questions that decide the next investment:
where the time actually goes, which runs can be removed without approximation,
and whether WhitsonPVT can provide a reproducible, lower-cost fluid-model path.

## Deliberately Not First

- Reimplementing GAP, RESOLVE, or a full reservoir simulator.
- Calling WhitsonPVT live for every PVT or flash evaluation.
- Treating low output correlation as proof that a subsystem is independent.
- Training a cross-asset black-box surrogate from unclassified historical runs.
- Publishing P10/P50/P90 from a Cartesian sweep or adaptive learning sample.
- Changing PETEX solver settings in production without a frozen comparison and
  an engineer-defined acceptance rule.

## Evidence Sources

This plan consolidates the documented current execution path and boundaries in
the accompanying Autogration, PETEX/IPM, solver, subsystem, roadmap, and
WhitsonPVT notes. Source URLs and access boundaries are maintained in
`sources.md`; official PETEX and Whitson documentation, licensed examples, and
observed sandbox behavior remain required for implementation-specific claims.