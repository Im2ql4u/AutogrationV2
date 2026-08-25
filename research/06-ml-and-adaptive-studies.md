# ML and Adaptive Studies

ML can make Autogration materially smarter, but only when it is subordinate to
physics, calibration, and explicit uncertainty. Its first job is to decide where
to spend expensive simulations, not to impersonate a reservoir engineer.

## Good early uses

| Use | Value | Guardrail |
| --- | --- | --- |
| Surrogate KPI prediction | Estimate NPV, rates, water cut, pressure, or constraint margin between expensive runs | Predictive uncertainty, out-of-domain detection, full-model confirmation |
| Adaptive DOE | Choose next cases with the most decision or constraint information | Persist acquisition logic, seed, and stopping reason |
| Run quality classification | Detect convergence anomalies, missing output, or implausible changes | Treat as triage; never silently discard a run |
| Sensitivity screening | Rank inputs worth additional full runs | Confirm rankings on independent cases |
| Warm starts/initial guesses | Reduce solve time for nearby scenarios | Solver still checks residuals and constraints |
| History-match assistance | Propose candidate parameter updates | Preserve posterior uncertainty and engineer review |
| Result retrieval/explanation | Help engineers find comparable cases and assumptions | Never fabricate a physical explanation |

## Bad early uses

- A black-box model declaring an operating plan safe or economically optimal
  without reference-solver confirmation.
- Training on an arbitrary Cartesian sweep and treating interpolation error as
  uncertainty in the earth.
- Replacing conservation laws, PVT, phase behavior, or integrity constraints with
  an unvalidated neural network.
- Random train/test splits over correlated timesteps or nearly identical cases;
  that leaks scenario information and overstates performance.
- Sending proprietary model data to an external model without a reviewed data
  and security boundary.

## Model selection by study size

For a modest number of interpretable inputs, a Gaussian process or another
uncertainty-aware tabular model is often a better first surrogate than deep
learning. It exposes predictive uncertainty, supports active learning, and is
easier to diagnose. For larger structured state fields, reduced-order models,
POD-style methods, or carefully validated neural surrogates may eventually be
appropriate, but they need much more data and stronger out-of-distribution
controls.

Published reservoir-surrogate work demonstrates that deep proxies can support
constrained optimisation under geological uncertainty. It is evidence that the
direction is viable, not proof that a generic proxy will be safe for an
Autogration asset. Models must be asset/model-family specific unless rigorous
transfer validation says otherwise.

## Validation contract for any surrogate

Every deployed surrogate needs:

1. A versioned training dataset and source-solver version.
2. Train/validation/test splits by scenario or realisation, and chronologically
   when forecasting from historical data.
3. KPI-level error metrics and error-by-regime slices.
4. Calibration tests: observed coverage of prediction intervals versus nominal
   coverage.
5. Physics/operability checks such as nonnegative rates, conservation residuals,
   bounds, and monotonic relationships where those are known.
6. An out-of-domain score and mandatory high-fidelity escalation threshold.
7. A decision-level test comparing the recommended action to full-model results.

The key quality criterion is not mean squared error alone. It is whether the
model makes the right action with correctly stated confidence near the action's
decision boundary.

## Smart sequence implementation order

1. Deterministic DOE, semantic case identity, result provenance, and run-budget
   controls.
2. Weighted uncertainty aggregation and decision dashboards using only trusted
   simulations.
3. Simple influence screening and a transparent run-selection heuristic.
4. An uncertainty-aware surrogate for a small, stable output contract.
5. Adaptive sampling with automatic escalation to a full run.
6. Only then evaluate deeper state-field models or learned solver accelerators.

## A concrete first experiment

Select one recurring study with fewer than about 15 declared uncertain inputs
and a decision KPI such as 5-year NPV subject to a water-handling limit. Generate
a space-filling initial design, run the trusted engine, compare a Gaussian-process
or similarly uncertainty-aware surrogate against held-out full cases, and select
additional points where the probability of constraint violation is uncertain.

The experiment passes only if it reduces full-model calls while preserving the
decision and its stated risk bound on an untouched reference set. Otherwise it
remains a research artifact, not a production feature.