# Subsystems and Multifidelity

## The rule

A subsystem can run independently only when the omitted system is represented
by a valid boundary-response contract, and the error induced at that boundary is
small enough for the decision being made.

Removing the rest of a model does not remove its physics. It turns the omitted
system into boundary conditions.

For a subsystem $A$ connected to the remainder $B$, an interface can include:

$$
b(t) = \{p, q, T, z, \text{phase state}, \text{composition},
\text{control availability}\}_{interface}
$$

The local calculation is only valid if its imposed $b(t)$ approximates the
response of $B$ for the scenarios under study, or if $A$ and $B$ iteratively
exchange boundary values until the interface residual converges.

## What current Autogration evidence says

The reviewed node-client path applies overrides to an archived PETEX model and
repeatedly calls `RESOLVE.RUNONESTEP()` through the schedule end date. That
demonstrates a whole-model execution interface with a timestep boundary. The
reviewed surfaces do not demonstrate a native dependency graph, partial-model
executor, interface contract, or error certificate for a partial run.

This does not prove that PETEX cannot reduce or internally partition work. It
means Autogration cannot yet claim a physically controlled partial-execution
capability based on the reviewed code.

## Partition classes

| Class | When it is valid | Example | Required proof |
| --- | --- | --- | --- |
| Exact disconnected component | No physical or control path connects it to the rest | Separate independent assets | Graph and shared-resource check |
| Fixed-boundary local solve | External pressure/rate/composition is known and insensitive | Local well response under an imposed separator pressure | Sensitivity bound on boundary variation |
| Cached/reused response | Inputs affecting a prior result are unchanged within tolerance | Same well response curve and fluid state | Dependency fingerprint and validity range |
| Weakly coupled co-simulation | Feedback is modest and interface iterations converge | Reservoir and surface model exchanged per timestep | Interface residual and full-model spot checks |
| Strongly coupled partition | Significant feedback exists | Shared manifold, compression, gas lift, recycling, common facility constraint | Iterative/monolithic coupling; no independent result claim |
| Surrogate boundary | Omitted domain is replaced by a calibrated response model | Facility capacity response or remote reservoir region | Predictive interval and escalation rule |

Shared capacity, back pressure, common gas-lift supply, recycle, routing,
composition blending, reservoir communication, and time-dependent events are
common sources of strong coupling. They are precisely where an apparently local
change can alter all wells.

## Domain decomposition is not a shortcut without iteration

The reservoir-simulation literature provides a useful mental model. Domain
decomposition solves regions at different resolutions while exchanging pressures,
saturations, and fluxes across their interface. It may use overlapping or
non-overlapping domains, Dirichlet/Neumann interface conditions, relaxation, and
outer iterations to convergence.

That translates to Autogration as a product requirement:

1. Declare the cut and each exchanged quantity.
2. Declare the coupling method, cadence, tolerance, and maximum iterations.
3. Persist the interface residual history and failure status.
4. Validate against a full model across baseline, extremes, and events.
5. Escalate to a larger or full model when the validity envelope is crossed.

A partial answer without those facts is a faster calculation, not an engineering
result.

## Candidate product mechanisms

### Dependency-aware reuse

Build a typed influence graph from assumptions to model objects, controls,
constraints, and KPIs. Reuse a prior computation only if no dependency changes,
or a declared response model remains within its validity envelope. This is the
lowest-risk performance feature because it can be exact for unchanged inputs.

### Response surfaces at model cuts

Replace an expensive component with a tabulated or fitted mapping such as:

$$
(p, T, z, u) \mapsto (q, \Delta p, \text{quality flags})
$$

Store the training domain, interpolation method, uncertainty band, and reference
solver version. Outside the domain, automatically request a higher-fidelity run.

### Iterative co-simulation

Run reservoir, wells, network, and facilities as separate executors. Exchange
their interface state at a shared timestep and iterate with relaxation until mass,
pressure, composition, and control residuals meet tolerance. This is technically
realistic but needs a robust interface protocol before it is a product feature.

### Multifidelity study plans

Use inexpensive models to screen broad uncertainty and reserve full PETEX or
other high-fidelity cases for model calibration, decision boundaries, constraint
activation, and final confirmation. Every output must display its fidelity and
validation status.

## Partition eligibility algorithm

For a proposed local study:

1. Identify decision KPIs and all constraints that could be affected.
2. Trace physical, material, energy, control, and economic dependencies upstream
   and downstream of the selected nodes.
3. Propose a cut and interface quantities with units and sign conventions.
4. Perturb interface quantities in trusted full-model runs to estimate KPI
   sensitivity.
5. Choose fixed boundary, response surrogate, iterative coupling, or full run.
6. Validate the chosen scheme across representative and extreme cases.
7. Record an error envelope and reject/escalate cases outside it.

The acceptance threshold should be decision-relative. A 2% rate error can be
irrelevant far from a choice boundary and unacceptable when it reverses a
drill-versus-shut-in recommendation.

## First practical slice

Start with response reuse and single-boundary studies around an approved,
well-understood component. Do not start with automatic arbitrary graph cuts.
The first success criterion is an auditable reduction in full-model calls with
no change in the approved decision for a held-out reference set.