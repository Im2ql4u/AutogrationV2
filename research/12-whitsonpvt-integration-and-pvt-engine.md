# WhitsonPVT Integration And A Native PVT Engine

Status date: 2026-09-08. This note assesses a potential WhitsonPVT connection
as a way to make richer studies feasible and trustworthy. Vendor claims and
documented public behaviour are not claims about the underlying implementation.

## Conclusion

WhitsonPVT is a strong candidate to become an authoritative **PVT data and
fluid-model provider** for Autogration. It is not a replacement for GAP,
RESOLVE, or a reservoir simulator. Its immediate value is eliminating a
frequent weak point in integrated studies: an untraceable, stale, inconsistent,
or physically questionable PVT model moving between reservoir, well, network,
and process calculations.

The first integration must be read-oriented, snapshot-based, and
engine-neutral. Autogration selects a declared PVT realization, preserves the
exact source/model/QC state, materializes an engine-specific artifact, and
executes it through a trusted adapter. Neither system should silently mutate
the other system's engineering model.

## Documented WhitsonPVT Capabilities

The public manual documents the following vendor-provided capabilities:

| Capability | Relevance to Autogration |
| --- | --- |
| Structured regions, wells, PVT reports, samples, sample conditions, compositions, and experiments | A more credible PVT evidence source than a detached spreadsheet or a copied correlation set |
| QC of recombination, composition, and experiments, including an explained user override | A usable quality gate and engineering-review artifact |
| Detailed fluid-model development: C7+ characterization, EOS tuning, viscosity modelling, and model QC | A controlled source for PVT model uncertainty and a candidate reference for a future PVT kernel |
| Import of Excel template, ECL300, PVTp, and PhazeComp EOS models | A practical migration/validation route for existing fluid models |
| Child models: black-oil tables and lumped EOS models | A route from a detailed parent model to a cheaper simulation input |
| Flash, saturation pressure, phase envelope, synthetic PVT experiments, and fluid-model validation | Low-cost PVT diagnostics that can screen a high-cost integrated study |
| External OAuth API available on request; documentation shows an authenticated `GET /api-external/v1/wells?project_id=...` call | A supported integration boundary, not UI automation |

The manual says that client-specific endpoint documentation is supplied when an
API connection is provisioned and that more endpoints can be implemented on
request. A phase-envelope article also says that a public Python SDK generated
an example. The public manual does not name, link, or specify that SDK, and the
published static API page only demonstrates a `wells` read. Do not assume that
fluid-model reads, exports, calculation jobs, writes, bulk access, webhooks,
rate limits, or version histories are included until a sandbox contract proves
them.

## The Product Boundary

```text
WhitsonPVT                         Autogration
-----------                        ------------
PVT reports, samples, QC      ->   PVT asset snapshot
Detailed parent EOS            ->   declared PVT realization
Black-oil/lumped child model   ->   engine-specific materialization
Phase/PVT calculations         ->   preflight and validation evidence
                                      |
                                      v
                                  RESOLVE / GAP / OPM / native response adapter
                                      |
                                      v
                                  outcomes, diagnostics, and decision evidence
```

Autogration should own the study revision, model-selection policy, case design,
resource budget, execution, cross-engine comparison, and decision record.
WhitsonPVT should remain the owner of its PVT source data, fluid-model
development, and associated engineering judgement.

This avoids two bad designs:

- copying live PVT values into every PETEX task without a durable identity; and
- treating a WhitsonPVT calculation or a saved tuning case as an independent
  probabilistic realization without a declared uncertainty model.

## Proposed Integration Contract

Introduce a PVT-provider adapter rather than embedding WhitsonPVT-specific
fields throughout the study model.

| Object | Minimum contents | Why it is immutable |
| --- | --- | --- |
| `PvtAssetSnapshot` | provider, tenant/project/region identifiers, source report/sample identifiers, acquisition time, API/schema version, raw-response hash, permissions scope | A later edit in WhitsonPVT must not rewrite an already-run case |
| `PvtModelRevision` | parent-model identifier, EOS and viscosity choices, parameter/case identifiers, QC status and override rationale, model/export hash | It identifies the scientific model used, not merely its display name |
| `PvtRealization` | one named, coherent uncertainty alternative, source/evidence, optional weight, validity conditions | It prevents independent sampling of mutually dependent PVT quantities |
| `PvtMaterialization` | simulator format, export settings, reservoir temperature, surface process, component map, artifact hash, validation status | A child model is conditional on these inputs and may not transfer verbatim between engines |

The ordinary case fingerprint must include the materialization hash. Exact reuse
is valid only when the PVT snapshot, model revision, materialization, target
engine/version, model artifact, settings, and requested output contract match.

## Highest-Value Uses

### 1. PVT provenance and release gates

The first useful feature is not a new solver. Before an expensive task is
opened, Autogration should show which PVT sample/model revision it will use and
block or require an acknowledged exception for:

- absent or failed source QC;
- a manual QC override without its rationale;
- component-map mismatch;
- imported EOS data lacking the required adjusted-composition validation;
- model/table outside its declared pressure-temperature-composition range; and
- a changed parent PVT model with no regenerated child model.

This directly supports the existing Pillar 1 goals of provenance, transparent
reuse, and run-budget protection.

### 2. PVT operating-envelope preflight

Use the selected PVT model to evaluate the planned reservoir, flowing-bottomhole,
wellbore, separator, compressor, and facility conditions before launching a
large study. The result is a warning/evidence artifact, not a replacement for a
coupled flow calculation.

Useful flags include a planned path crossing the phase envelope, proximity to a
critical or retrograde-condensation region, a pressure/temperature point outside
the fitted evidence range, and a black-oil-table limitation. This is especially
valuable where a small change in composition, pressure, or temperature may make
phase proportions and fluid properties change sharply.

### 3. PVT realization bundles for uncertainty studies

Treat PVT uncertainty as a small set of coherent, reviewable alternatives:

- alternative C7+ characterization cases;
- bounded EOS/viscosity parameter cases;
- sampling/recombination or contamination alternatives;
- detailed versus lumped EOS; and
- black-oil table variants with their specific reservoir/surface assumptions.

These are model-form and parameter alternatives, not automatically probability
samples. Weights require an engineering evidence basis. A PVT realization must
travel with compatible reservoir realization, composition, VLP/IPR, and surface
processing assumptions when those dependencies exist.

### 4. Multifidelity PVT screening

Do not multiply every reservoir, operating, and PVT alternative into a full
RESOLVE plan. Use a nested design:

1. Run PVT envelope, flash, table, and QC diagnostics for candidate PVT cases.
2. Discard only candidates that are demonstrably invalid or equivalent under the
   declared output contract.
3. Run a modest, space-filling cross-section of PVT and operating cases through
   the trusted integrated model.
4. Spend further full-model calls where PVT alternatives can change a phase,
   constraint, or decision boundary.
5. Confirm the final decision on representative, full-engine PVT realizations.

This aligns with the existing separation between learning samples and
probability samples. It reduces wasted calls without relabelling adaptive
selection as probability evidence.

### 5. Cross-engine PVT compatibility testing

WhitsonPVT's detailed parent model and child-model outputs offer a disciplined
test subject for an `ExecutionAdapter` contract. Compare declared PVT properties
and phase behaviour at fixed states before comparing full production forecasts.

The test order is:

1. composition and component mapping;
2. saturation pressure, density, viscosity, and phase split at selected states;
3. black-oil table continuity and interpolation behaviour;
4. one-well IPR/VLP response;
5. small network response; and
6. decision KPI agreement on a controlled study.

This is where hidden conversion errors, unsupported viscosity options, and
non-monotonic-table constraints become visible. It is also why a model name such
as "PR", "LBC", or "CSP" is insufficient as an interchange contract.

## A Better Native-Engine Direction

The attractive native-compute target is a **transparent PVT compatibility and
response engine**, not an immediate GAP clone.

| Stage | Capability | Position |
| --- | --- | --- |
| 1 | Parse, fingerprint, plot, interpolate, and validate approved black-oil/PVT artifacts | A low-risk native service with immediate study-quality value |
| 2 | Evaluate phase/property response against a stored, approved table plus explicit extrapolation refusal | Cheap screening component; no claim of a compositional simulator |
| 3 | Implement a transparent cubic-EOS flash/PVT research kernel using public theory and open references | Benchmark sandbox against measured data and approved WhitsonPVT/PETEX outputs |
| 4 | Produce validated child-model candidates and conduct cross-engine property tests | Only after stages 1-3 have acceptance tests and engineer ownership |
| 5 | Couple the validated PVT kernel to the future native network kernel | Long-term research; confirm critical decisions with trusted engines |

The black-oil table documentation is particularly useful because it makes the
assumptions explicit: fixed reservoir temperature and surface process, a tuned
EOS, and special handling of critical/extrapolated and non-monotonic behaviour.
It proves that a fast child model is not automatically valid for near-critical
fluids. The public methodology may inform independent benchmarks; it must not be
used to reverse engineer proprietary source or presented as an implementation
specification.

The relevant performance path is therefore:

```text
quality-controlled PVT source
  -> cacheable PVT materialization
  -> low-cost property/validity screening
  -> selected RESOLVE/GAP reference runs
  -> validated response reuse or native sandbox
```

That path may attack a significant cost before modifying a network nonlinear
solver. It also makes future native reservoir/network work more credible because
the fluid-physics boundary has a measured reference and a failure taxonomy.

## Feasibility Gate: Vendor Sandbox

This integration should not be scheduled until a short, read-only sandbox spike
answers the following questions with observed responses and an agreed support
contact:

1. Which endpoints retrieve regions, wells, reports, samples, experiments, QC
   results/overrides, fluid models, saved cases, and child-model exports?
2. Does an API identity expose immutable revisions, timestamps, authors, source
   attachments, and stable IDs, or only the current state?
3. Can the API request phase/flash/table calculations? If yes, are calls
   synchronous, rate-limited, cacheable, and versioned?
4. Which export formats and options are available programmatically, including
   black-oil, compositional, water/brine, and viscosity information?
5. What exact artifacts can GAP/RESOLVE consume through the organisation's
   licensed PETEX interfaces, and what comparison is required after import?
6. What are the tenant, data-residency, retention, least-privilege, audit, and
   credential-rotation rules?

The test passes only if an engineer can reproduce the same `PvtAssetSnapshot`
and materialized input from a stored study revision, and a three-case pilot
proves that the selected PVT variant reaches the intended target engine without
an unexplained property mismatch. Credentials belong in the deployment secret
store only, never in Autogration data, task archives, logs, or source control.

## First Pilot

Use the public Volve material provided in the WhitsonPVT manual, or an approved
non-sensitive internal analogue, to avoid beginning with a customer-critical
asset. Run three named conditions: a base condition, a condition near the phase
boundary, and one that exercises the expected pressure/temperature range.

For each condition, preserve the PVT source/model snapshot, QC evidence,
component map, export/materialization hash, target-engine result, and property
comparison. The pilot succeeds only when the native preflight and the target
engine agree on the accepted PVT range and the integration makes an engineer's
model choice more inspectable. Faster execution is a secondary metric until
that evidence exists.

## Sources

- [WhitsonPVT API](https://manual.pvt.whitson.com/api/), accessed 2026-09-08.
- [WhitsonPVT user manual](https://manual.pvt.whitson.com/), accessed
  2026-09-08.
- [WhitsonPVT EOS import](https://manual.pvt.whitson.com/tool_tips/EOS_Import/),
  accessed 2026-09-08.
- [WhitsonPVT black-oil table methodology](https://manual.pvt.whitson.com/methods/child_models/black_oil_tables/),
  accessed 2026-09-08.
- [WhitsonPVT phase-envelope deep dive](https://manual.pvt.whitson.com/deep_dives/phase_envelopes/),
  accessed 2026-09-08.