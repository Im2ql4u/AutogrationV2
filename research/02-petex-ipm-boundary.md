# PETEX/IPM Boundary

This note distinguishes public product behavior from hidden implementation. It
is the guardrail against trying to reverse engineer a proprietary solver from a
brochure.

## Names that must stay separate

| Product | Publicly described role | Consequence for Autogration |
| --- | --- | --- |
| GAP | Equation-based steady-state multiphase production/injection network modelling and optimisation | A network balance problem, not a reservoir time-integration problem by itself. |
| RESOLVE | Vendor-neutral integration, workflow, scheduling, scenario, and multilevel-optimisation platform | The orchestration/coupling layer currently exposed by Autogration. |
| REVEAL | Specialised fully thermal finite-difference reservoir simulator | A reservoir-physics simulator, distinct from RESOLVE. |
| PROSPER | Well and pipeline nodal analysis, including IPR/VLP and lift systems | Important closure/response-model source in an integrated model. |
| MBAL | Analytical material-balance reservoir toolkit and fast proxy-style forecasts | Evidence that low-fidelity reservoir representations are useful when their limits are explicit. |

The initial "revolve" reference has been clarified as **RESOLVE**. Use the
product names above consistently in future technical decisions.

## What can be said about GAP

Public PETEX material describes GAP as an equation-based steady-state solver
that balances pressure, flow, and temperature across wells, pipes, chokes,
compressors, pumps, and facilities. It can draw on dynamic component models or
pre-calculated responses such as lift curves. It also provides constrained,
nonlinear optimisation and a rule-based forecast mode.

The former public PETEX runtime case study gave unusually useful, but still
vendor-authored, evidence about the numerical shape of one GAP model. Its URL
now returns 404, no snapshot was found in the checked Internet Archive index,
and only portions survive in search-index fragments and the prior research
notes. Treat the following as historical vendor claims pending lawful recovery
of the original source:

- Roughly 1,100 network variables represented rate-balance and pressure-drop
  equations.
- Its reported Jacobian was substantially dense, with more than 75% of entries
  populated.
- Some derivative entries required repeated full multiphase pipeline
  calculations, including centered perturbations.
- The case study attributes much of network runtime to Jacobian construction;
  it reports parallel Jacobian generation and model-formulation changes as
  material speed levers.

The full timing sequence, comparison conditions, hardware, software version,
and meaning of a cited `0.5%` have not been independently recovered. They must
not be presented as a verified near-100x benchmark for Autogration.

This supports a specific conclusion: a better GAP-like solver is not mainly
about choosing Newton versus another outer nonlinear method. Derivative quality,
the cost of constituent hydraulic/PVT evaluations, Jacobian structure, linear
algebra, continuation, and model formulation dominate the hard part.

## What can be said about RESOLVE

Public descriptions identify RESOLVE as the platform that connects reservoir,
well, network, process, and transient applications, runs forecast schedules,
supports adaptive timesteps, and coordinates optimisation and scenarios. PETEX
describes the integrated optimisation as mixed-integer, nonlinear, and
non-convex, with SLP/routing in RESOLVE and nonlinear optimisation in GAP.

Autogration's exposed tag catalog supports the broad public description: it has
forecast mode, adaptive-timestep settings, optimisation frequency, an SLP-style
parameter group, and a `GIRO` option. Those tags reveal selectable behavior, not
the solver's implementation.

## What can be said about REVEAL

PETEX describes REVEAL as a fully thermal finite-difference numerical simulator
that solves coupled pressure-flow-temperature equations. Its public material
also describes optional coupling with fractures/geomechanics, chemistry, EOR,
and complex wells. That makes it a very different technical target from a
steady-state surface network: it contains state evolution, spatial
discretisation, constitutive laws, nonlinear phase behavior, and potentially
multiphysics coupling.

## What is not knowable from public sources

Do not assert any of the following without lawful access to official manuals,
tests, or observed behavior:

- GAP's exact residual variables, equation ordering, Jacobian construction,
  globalization, or convergence policy.
- RESOLVE's IPR-scaling algorithm or precise coupling algorithm.
- REVEAL's discretisation details, linear solvers, phase behavior algorithm, or
  proprietary special-physics implementations.
- Optimiser formulations, default constraints, objective transformations, or
  tie-breaking behavior.

Public marketing and case studies are evidence of capability, not a substitute
for a technical specification.

## Additional boundary evidence

The official OpenServer page describes the externally visible control model:
`DoSet` mutates a value, `DoCmd` invokes a calculation, and `DoGet` retrieves a
value or status. It also describes a generic wrapper for third-party APIs and
RESOLVE visual workflows as a layer over those capabilities. This matches the
Autogration integration boundary; it does not expose the solvers behind it.

GAP Transient is a separate product surface. PETEX describes it as switching
between steady-state and transient multiphase modeling, with transient studies
typically spanning minutes to days while steady-state forecasts span weeks to
years. This reinforces that "simulation" has multiple time-scale and fidelity
meanings in the IPM ecosystem.

## Lawful evidence plan

1. Obtain manuals, release notes, example models, and training material through
   the organisation's PETEX licence/support channels.
2. Record only original summaries, parameter maps, observed input/output
   behavior, and reproducible benchmarks in this repository.
3. Use small synthetic models to infer externally visible behavior; do not
   decompile, circumvent licensing, or reproduce copyrighted manual text.
4. Compare any native capability against published conservation, convergence,
   and KPI acceptance criteria rather than claiming algorithmic equivalence.

## Product position

Autogration need not become a clone of GAP, RESOLVE, or REVEAL to be more
valuable. Its independent position can be: the system that makes integrated
engineering studies reproducible, uncertainty-aware, economically legible, and
adaptive across many calculation engines.