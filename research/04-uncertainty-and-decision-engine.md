# Uncertainty and Decision Engine

The real question is not "what did one simulation produce?" It is: given what
we know and do not know, should we shut in, drill, intervene, defer, or gather
more information?

## Treat uncertainty as a model, not a list of sweeps

For decision $d$, uncertain quantities $\theta$, operating uncertainty $\xi$,
and a simulation/response model $f$, define outcomes as:

$$
Y = f(d, \theta, \xi)
$$

and economic value as:

$$
V(d, \theta, \xi) = NPV(Y, \text{prices}, \text{costs}, \text{tax},
\text{emissions}, \text{discounting})
$$

The product must record where each uncertainty comes from, its distribution or
scenario weight, its units and transforms, its dependence on other variables,
and its evidence/owner. A five-value input sweep is not automatically a
probabilistic distribution.

### Required uncertainty classes

| Class | Examples | Product treatment |
| --- | --- | --- |
| Geological/reservoir | volumes, permeability fields, faults, aquifer strength, rel-perm | Ensemble/realisations and history-match provenance |
| Fluids and wells | PVT, IPR/VLP, skin, lift efficiency, failure rate | Calibrated parameter distributions and model-form uncertainty |
| Surface/facilities | capacity, availability, compressor maps, flow assurance | Operational states, constraints, and event uncertainty |
| Strategy | well count, sequencing, choke policies, intervention timing | Explicit decision variables, not random inputs |
| Commercial/external | price, tariffs, capex, opex, tax, carbon cost | Versioned economic scenarios and correlations |
| Model form/data | correlation choice, grid resolution, measurement error | Named alternative models and observation likelihoods |

Correlations are non-negotiable. Treating related reservoir properties, prices,
or outages as independent can produce confident but false economics.

## Decision metrics

Maximising one deterministic rate is rarely adequate. A decision record should
support at least:

- expected NPV and discounted cash flow;
- probability of negative NPV or breaching a facility/safety/operability limit;
- downside metrics such as a lower-tail value measure;
- production, recovery, emissions, water handling, and integrity constraints;
- the distribution of outcomes by decision, not just an average; and
- explicit P10/P50/P90 convention. Prefer stating exceedance probability so the
  high-side/low-side convention cannot be misread.

A risk-aware formulation can be expressed as:

$$
\max_d \; \mathbb{E}[V(d,\theta,\xi)]
\quad \text{subject to} \quad
\Pr(C_j(d,\theta,\xi)>0) \leq \alpha_j
$$

where $C_j$ represents a constraint violation. The correct objective and risk
limits are business decisions, so Autogration must make them visible rather
than silently embedding them.

## Study modes

| Mode | Use | Not sufficient for |
| --- | --- | --- |
| Baseline and one-at-a-time | Fast debugging and local sensitivity | Interaction discovery or probability statements |
| Full factorial | Small categorical studies with all interactions needed | High-dimensional continuous uncertainty |
| Fractional factorial/screening | Identify influential factors | Final uncertainty distributions |
| Latin hypercube or low-discrepancy sampling | Broad continuous-space coverage | A calibrated posterior by itself |
| Monte Carlo over weighted realisations | Propagate a stated uncertainty model | Cheap exploration when each run is expensive |
| Adaptive sampling | Focus runs near a decision or constraint boundary | An unvalidated proxy's extrapolation |

The existing Cartesian expansion is a valid small-study mode, but should not be
the default representation of uncertainty.

## Smart sequence: an adaptive study controller

This is the strongest near-term meaning of a "smart sequence": select the next
calculation because it is likely to change the decision, not because it is the
next Cartesian row.

1. Define actions, stopping rule, value metric, hard constraints, and the
   uncertainty registry.
2. Generate a space-filling initial design with stable semantic case IDs and a
   persisted random seed.
3. Run a small number of high-fidelity reference cases.
4. Fit a response/surrogate model only for outputs that have enough support.
5. Estimate uncertainty in the output and in the *decision*, including surrogate
   uncertainty.
6. Select the next reference runs where a decision boundary is uncertain, a
   constraint could become active, or the surrogate is out of distribution.
7. Refit, validate against held-out full runs, and stop only when the preferred
   action and its risk bound are stable under the declared acceptance rule.

Possible acquisition functions include expected improvement, expected reduction
in decision loss, expected constraint-information gain, or deliberate
space-filling. The first implementation can be simple and transparent; it does
not need a neural network.

## Product data model to build first

Add these concepts to the scenario model rather than attaching them as free-form
metadata later:

- `UncertainInput`: distribution, support, units, transform, provenance, and
  correlation-group identifier.
- `Realisation`: a named, weighted set of consistent reservoir/model choices.
- `StudyPlan`: design method, seed, budget, fidelity policy, and stopping rule.
- `Decision`: alternatives, objective, risk limits, economic-model version, and
  approver.
- `Case`: canonical assignments, solver/fidelity version, parent state, and
  reproducibility fingerprint.
- `Outcome`: KPI time series, economics, constraint margins, warnings, runtime,
  and quality flag.

This corrects two current design limitations at once: index-based case identity
and unbounded Cartesian growth.

## Minimum viable decision study

For "shut in or build more wells", an initial credible workflow is:

1. Establish a history-matched baseline or explicitly label the model as
   uncalibrated.
2. Define discrete actions and their capex, opex, schedule, abandonment, and
   operating constraints.
3. Select only decision-relevant uncertainties, including correlated reservoir
   realisations and commercial assumptions.
4. Use a bounded DOE/ensemble plan, not all combinations.
5. Run trusted full-model cases, calculate weighted economic and operational
   outcomes, and show outcome distributions per action.
6. Add runs where the recommendation is sensitive or constraints are close.
7. Publish an auditable decision record containing assumptions, evidence,
   residual risks, and the condition that would reverse the recommendation.

## Critical failures to prevent

- Presenting sweep frequencies as probabilities without declared weights.
- Mixing history-match calibration and forecast uncertainty without provenance.
- Training a proxy on near-duplicate Cartesian cases, then claiming broad
  uncertainty coverage.
- Averaging a binary safety or integrity constraint away.
- Optimising on a surrogate without full-model confirmation near the proposed
  optimum.
- Hiding price, cost, discount, and emissions assumptions outside the study
  definition.