# Physics and Solver Architecture

## Direct answer: is this "just Newton"?

No, though Newton-like methods often appear inside the solution process.

A steady production network can be represented as a nonlinear algebraic system:

$$
F_{network}(x; u, \theta) = 0
$$

where $x$ contains pressures, phase/component rates, and possibly equipment
states; $u$ contains controls such as chokes, lift, compressor speed, and routes;
and $\theta$ contains PVT, geometry, correlations, and reservoir/well-response
parameters. Typical residual blocks include:

$$
\sum q_{in} - \sum q_{out} - q_{source} = 0
$$

at a junction, and

$$
p_i - p_j - \Delta p_e(q_e, T_e, z_e; \theta_e) = 0
$$

for an edge. Well inflow/outflow, equipment performance, constraints, and phase
behavior add more nonlinear relations and regime changes.

Newton's method locally solves a linearisation:

$$
J(x_k) \delta x = -F(x_k), \qquad x_{k+1}=x_k+\alpha\delta x
$$

It is only reliable when the residual is sufficiently smooth, the derivatives
are sound, the linear system can be solved robustly, and the step is controlled.
Multiphase flow correlations, phase transitions, equipment limits, changing flow
regimes, inactive constraints, and switching controls violate the convenient
version of those assumptions.

For a reservoir simulator, time and spatial states add a different class of
problem. A simplified phase mass balance is:

$$
\frac{\partial}{\partial t}(\phi \rho_\alpha S_\alpha) +
\nabla \cdot (\rho_\alpha v_\alpha) - q_\alpha = 0
$$

with Darcy flux:

$$
v_\alpha = -\frac{k k_{r\alpha}}{\mu_\alpha}
  (\nabla p_\alpha - \rho_\alpha g\nabla z)
$$

Finite-volume discretisation and an implicit timestep produce a nonlinear
residual for pressures, saturations, compositions, temperatures, and well
variables. A production forecast therefore behaves like a coupled DAE system:

$$
M(y)\dot y = f(y,z,u,t;\theta), \qquad 0=g(y,z,u,t;\theta)
$$

where $y$ are dynamic reservoir states and $z$ are algebraic network/equipment
states. Optimisation then wraps this simulation in a constrained decision
problem. Parameters may be chosen at the start, but the model response still
changes across timesteps and operating regimes.

## Why a naive rewrite fails

- Physical closure is the work: PVT/EOS, relative permeability, capillary
  pressure, IPR/VLP, multiphase pressure drop, heat transfer, and equipment
  maps are not interchangeable parameters.
- The linear algebra differs by domain. Reservoir discretisations are generally
  large and sparse; a highly connected surface-network Jacobian can be much
  denser. PETEX's public case study explicitly makes this contrast for one GAP
  model.
- Robustness requires timestep control, damping/trust regions, continuation,
  constraint activation, failure recovery, and diagnostics, not just a root
  finder.
- Optimisation is mixed discrete/continuous, non-convex, and constrained. A
  root solve does not find the best development plan.
- Engineering validity is empirical. A numerically converged answer can still
  be wrong if correlations, calibration, PVT, or boundary conditions are wrong.

## Open reference implementations

Open Porous Media (OPM) Flow and MRST are the primary reproducible references
for this research, not because they are drop-in replacements for PETEX, but
because their concepts and behavior can be inspected and benchmarked. Public
OPM material describes fully implicit black-oil simulation, automatic
differentiation, Newton and nonlinear domain-decomposition solvers, adaptive
step control, and CPR/ILU/multigrid linear-solver families. MRST provides open
books, examples, automatic differentiation, and a research-oriented framework.

They make a practical research stack possible:

| Question | Reference asset |
| --- | --- |
| Fully implicit reservoir formulation | OPM Flow and MRST examples |
| Residual/Jacobian construction | MRST-AD source and books |
| Sparse linear solver/preconditioner behavior | OPM Flow documentation and source |
| Upscaling/reduced models | OPM/MRST modules and literature |
| Production-network comparison | A native benchmark with transparent component response functions |

## A credible native-compute progression

Do not begin with a commercial-scale compositional reservoir competitor. Build
evidence and ownership in layers.

### Stage 0: study intelligence around trusted engines

Own canonical inputs, units, case identity, result schemas, provenance,
cost/queue information, constraints, and economic metrics. This is useful even
if every physical calculation remains in PETEX.

### Stage 1: transparent response and screening models

Add audited well, reservoir-tank, IPR/VLP, and facility response models with
explicit validity envelopes. They support screening and sensitivity work, but
must label their fidelity and assumptions.

### Stage 2: native steady-state network kernel

Use open or documented component closures first. Assemble mass-balance and
pressure-drop residuals with automatic differentiation where possible. Support
damped Newton/trust-region steps, sparse or block-aware linear algebra, bounds,
and continuation. Validate on synthetic networks before comparison against
approved PETEX reference cases.

### Stage 3: coupled black-oil reservoir/network experiments

Use OPM or MRST as an inspectable reference. Begin with a well-controlled,
fully implicit black-oil model and an explicit coupling contract. Do not claim
REVEAL-equivalent thermal, compositional, geomechanical, or chemical capability.

### Stage 4: differentiated physics only when demand justifies it

Choose one costly, high-value physics domain from actual field decisions. Add it
only with calibration data, acceptance tests, and a clear reason that an
existing engine or proxy is insufficient.

## Better solver agenda

A solver initiative should measure improvement on five axes:

| Axis | Example measure |
| --- | --- |
| Physical validity | Mass/energy balance, calibrated response, agreement on decision KPIs |
| Numerical robustness | Convergence rate, failure modes, residual history, recovery success |
| Speed | Wall time, expensive closure calls, linear iterations, compute cost |
| Transparency | Visible equations, assumptions, tolerances, diagnostics, reproducibility |
| Decision quality | Regret against a high-fidelity reference, constraint-violation probability |

Likely high-leverage technical work includes analytic/automatic derivatives,
response caching, warm starts across related cases, active/inactive constraint
management, continuation from a stable base case, physics-aware reduced models,
and choosing fidelity by expected decision impact. These should be benchmarked,
not assumed.

## First benchmark set

Create synthetic, versioned cases before touching a customer model:

1. One well with a transparent IPR/VLP intersection.
2. Two wells sharing a manifold, showing back-pressure interaction.
3. A choke/compressor/pump constraint-switching case.
4. A small reservoir plus surface-network coupled case with a known timestep
   event.
5. A routing or well-control optimisation case with a feasible baseline.

Each benchmark must specify inputs, units, expected conservation residuals,
accepted KPI bands, convergence diagnostics, and a reference result. Only then
is a claim of a "better solver" testable.