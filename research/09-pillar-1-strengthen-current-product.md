# Pillar 1: Strengthen The Current Product

Status: vision branch. This is not a generic refactor or an execution backlog.
It defines what Autogration should become more reliable at before it tries to
become more statistically sophisticated, economically authoritative, adaptive,
or natively computational.

## Purpose

Autogration already has meaningful capability: it lets an engineer alter a
RESOLVE-linked model, generate cases, send them to PETEX compute nodes, execute
the schedule step by step, and recover results. Pillar 1 makes that existing
capability safe, reproducible, legible, and resistant to accidental waste.

The central promise is:

> A user can understand exactly what will run, why each case is distinct, what
> the run will cost operationally, and whether a saved or repeated study still
> means the same thing.

This pillar is the entrance ticket to every later branch. Uncertainty statistics,
economics, adaptive selection, and ML all become misleading if the current
case-generation and provenance behavior is ambiguous.

## What Pillar 1 Is And Is Not

| Pillar 1 is | Pillar 1 is not |
| --- | --- |
| Correctness and reproducibility work around the existing RESOLVE execution flow | A replacement solver or a RESOLVE rewrite |
| Better study safety, identity, previews, and auditability | A claim of probabilistic uncertainty or P10/P50/P90 results |
| A way to eliminate accidental and inactive runs | An excuse to silently alter engineering assumptions |
| A basis for later DOE and decision studies | A broad redesign of every current screen |

## Evidence Base

The immediate evidence is the August 2026 assumptions and simulation-expansion
audit in the sibling `autogration_frontend/ASSUMPTIONS_DESIGN_NOTES.md`, checked
against the current frontend and backend code. It found that a user can currently
expand assumptions, RESOLVE settings, and module settings into a Cartesian case
set, but several controls still depend on raw values or list position.

The issues below are not theoretical. They are currently relevant to how a study
is generated before PETEX receives it.

## The Pillar Branches

### 1. Case Meaning And Reproducibility

Every case needs a stable semantic identity. A case is not "row 37"; it is a
normalized set of assignments against a specific model/data/configuration
context.

The desired state is:

- semantically equivalent values are recognized as equivalent;
- a case has a deterministic fingerprint independent of UI sorting or preview
  position;
- exclusions and reruns target that fingerprint, not a list index;
- a repeated run makes explicit whether it is an exact repeat, a different
  execution attempt, or a changed study; and
- saved scenarios preserve all behavior relevant to their intended meaning.

This branch is primarily platform-owned. Engineers need to confirm units and
the equality semantics of unusual model values, but they should not have to
manually protect the product from formatting differences, list reordering, or
an incomplete saved scenario.

### 2. Run Admission And Operational Guardrails

The current product can create a very large Cartesian batch without a single
authoritative admission decision. Pillar 1 should make each launch deliberate.

The desired state is:

- one trustworthy case count before submission;
- an enforced backend budget, not only a frontend preview limit;
- a clear distinction between a warning, a blocked submission, and an approved
  exception;
- visible estimates of queue pressure, expected runtime range, and compute
  consumption when evidence exists; and
- an explanation of why the count is high and which dimensions multiply it.

The product can build count, dedupe, and audit behavior without engineering
input. Engineers and operations owners must define the practical run-budget
policy because a harmless 200-case study for one model can be reckless for a
large, slow, or license-constrained model.

### 3. Model-Aware Case Validity

Some combinations are structurally inactive or contradictory before RESOLVE ever
receives them. For example, a fixed-timestep selection can make an adaptive
maximum-timestep sweep irrelevant.

The desired state is:

- model/settings rules suppress inapplicable dimensions before expansion;
- the UI says which values are suppressed and why;
- no rule silently changes a user choice; it either suppresses it visibly or
  asks the user to resolve a conflict; and
- every rule is versioned, testable, and attributable to a technical source or
  engineer-approved behavior.

This branch is engineering-co-designed. Autogration can provide the declarative
rule machinery, validation, display, and audit trail. Reservoir, production, and
RESOLVE engineers must own the meaning of the rule and its exceptions.

### 4. Study Completeness And Reuse

A saved preset must say honestly what it preserves. Today an assumptions-only
preset can be useful, but it is not a complete simulation scenario when
RESOLVE settings, module settings, schedules, or structural operations were also
used.

The desired state is:

- a distinction between an assumptions library and a complete scenario/study
  definition;
- explicit partial-fidelity warnings when a conversion drops added nodes,
  schedules, or module configuration;
- compatibility markers when a saved item is loaded into a changed model; and
- a human-readable diff between baseline and saved configuration.

This needs a product decision about what a preset promises. The technical work is
straightforward only after that promise is made.

### 5. Operator-Focused Study Ergonomics

The current module-settings editing surface and simulation launch preview are
powerful but broad. Pillar 1 should reduce accidental scope rather than make the
interface more decorative.

The desired state is:

- row-level editing for a named module, element, and field where appropriate;
- structural operations isolated from routine value editing;
- previews that describe a case in engineering language rather than only raw
  index order;
- warnings attached to the action that causes the risk; and
- task results that remain reachable from the more meaningful study or scenario
  context later on.

Engineering input is useful for terminology and workflows, but product and UX
can progress through observation and usability testing without waiting for
solver-theory decisions.

## Verified Current-Product Issues To Review Together

The following items are drawn from the existing assumptions design audit and
checked against current code surfaces. They are a review catalogue, not a promise
that every item should be implemented immediately.

| Issue | Current risk | Desired state | Primary input needed |
| --- | --- | --- | --- |
| No backend run cap | A large batch can pass beyond the preview limit | Server-side admission with visible budget rationale | Product and operations policy |
| Index-based exclusions | Sorting/reordering can target the wrong case | Exclude semantic case fingerprints | Platform design; engineer review of fingerprint fields |
| Raw-value expansion | `100`, `100.0`, and string forms can multiply runs | Typed canonicalization and dedupe | Platform design; unit/value semantics review |
| String equality | Float and boolean comparisons are fragile | Typed equality with defined tolerance rules | Platform design; engineer tolerance input for sensitive fields |
| No constraint pruning | Inactive/contradictory settings still generate cases | Visible declarative pruning rules | RESOLVE and production-engineer rules |
| No cost/queue forecast | Users submit blind to operational effect | Evidence-based estimate with uncertainty label | Operations and infrastructure input |
| Cartesian-only expansion | Large studies scale wastefully | Explicit study modes with stated purpose | Product decision and engineer review |
| Broad module editor | A local edit opens unrelated configuration | Scoped editing and structural separation | UX observation and module-user feedback |
| Assumptions-only presets | Full scenario behavior can be lost on reuse | Clear preset promises and full-scenario option | Product decision |
| Silent lossy preset conversion | Added nodes/schedules can disappear without notice | Block or warn with a partial-fidelity record | Platform design; product choice on override |

## Engineering Partnership And Decision Rights

The product cannot be designed correctly by software work alone, but it also
does not need an engineer in every implementation detail. The distinction should
be explicit throughout the vision.

| Area | Autogration can define and build | Requires engineer co-design | Must remain human accountable |
| --- | --- | --- | --- |
| Case identity and audit | Hashing, versioning, diffs, retry lineage | Units and unusual equality semantics | Approval of meaning for material assumptions |
| Run budgets and visibility | Counting, warnings, queues, exception logging | Typical model cost and operational limits | Approval of exceptional compute spend |
| Pruning and validation | Rule engine, tests, explanation UI | Physical/RESOLVE applicability rules | Acceptance of rules that change available cases |
| Uncertainty inputs | Distribution capture, sampling, provenance | Ranges, weights, realization consistency, correlations | Declaring uncertainty suitable for decision use |
| Economic studies | Templates, cashflow engine, gates, evidence pack | KPI meaning and facility implications | Price/cost assumptions, economic approval, final decision |
| Adaptive selection | Candidate scoring, logging, stopping mechanics | Meaningful constraints and decision thresholds | Authorization to run expensive next cases and act on outcome |
| ML and AI | Data lineage, validation controls, recommendation display | Domain validity and failure interpretation | Any operational or investment conclusion |
| Subsystem/native physics | Benchmark harness, interfaces, diagnostics | Boundary conditions and acceptance criteria | Production use and engineering sign-off |

### When To Involve Engineers

Ask for engineering input at points where Autogration would otherwise be
inventing physics, value semantics, or acceptable risk:

- defining a range or distribution;
- declaring realization weights or relationships between variables;
- defining a valid pruning rule;
- choosing a technical KPI or constraint;
- deciding what constitutes an acceptable simulation warning/failure;
- creating a response-model validity envelope; and
- approving a decision interpretation.

Autogration can proceed without waiting for an engineer when it is preserving
meaning rather than deciding it: deterministic IDs, dedupe, warnings, complete
provenance, UI scope reduction, audit logging, and explicit status labels.

## How We Review And Patch This Pillar Together

Each known issue should be discussed as a product behavior, not merely a code
change. The shared review format is:

1. Reproduce the present behavior on a representative model or a small synthetic
   case.
2. State the engineering harm if it occurs in a real study.
3. Decide the desired user-visible behavior and whether an engineer-defined rule
   is involved.
4. Record the decision, ownership, and required evidence in the sibling
   `DECISIONS.md` and `JOURNAL.md` conventions when actual work begins.
5. Only then split the behavior into a scoped cross-repository change.

This gives us a way to patch the old product without losing sight of why each
patch matters to later uncertainty and decision work.

## Relationship To Later Vision Branches

Pillar 1 is intentionally first because it makes future claims possible:

- A probability distribution is not credible if cases are duplicated or a saved
  scenario omits settings.
- An economic comparison is not credible if it is unclear which technical case
  produced its cashflow.
- Adaptive selection is not credible if the candidate set has no stable identity
  or invalid combinations remain in it.
- ML training is not credible if its examples contain silent duplicates, missing
  context, or ambiguous values.

The pillar therefore improves the present product while creating the stable
ground that the other branches need.