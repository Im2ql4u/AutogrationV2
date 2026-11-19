# Five WhitsonPVT-Enabled Maturity Approaches

Status: idea note, 2026-09-09. These are alternative product directions for
discussion, not a delivery commitment. They assume Autogration continues to use
PETEX/GAP/RESOLVE as the trusted integrated calculation path in the near term.

## Context

Autogration currently creates many PETEX/RESOLVE cases, applies assumptions,
runs the schedule, and collects results. It does not yet own a native network
solver, formal uncertainty model, or durable engineering-model dependency graph.

WhitsonPVT is relevant because it centralizes PVT reports, samples, QC, fluid
models, and derived model artifacts. It should not replace GAP or RESOLVE:

- GAP finds a feasible steady-state balance of wells, pipes, and facilities.
- RESOLVE coordinates linked models and schedules through time.
- WhitsonPVT establishes and checks what the fluid model means.
- Autogration decides which cases run and preserves the evidence for each one.

The common motivation is to turn PVT from a hidden file or static model setting
into a visible, traceable, and decision-relevant part of every study.

## 1. Verified Simulation Factory

**Idea:** Every Autogration case carries an immutable reference to its PVT
source, QC status, fluid-model revision, component mapping, and exported input
artifact.

**Motivation:** Today a result may be associated with a copied PETEX project,
but it can be difficult to establish exactly which lab evidence and fluid-model
judgement supported the PVT inputs. A completed simulation is not enough if its
fluid basis is unclear or later changes.

**WhitsonPVT contribution:** It provides the report/sample/model/QC identity;
Autogration snapshots that identity and records it in the case fingerprint.

**Result:** Faster review, reproducible reruns, safer reuse, and less time
spent resolving “which PVT did this forecast use?”

## 2. Model Change-Impact System

**Idea:** Build a dependency graph from source evidence through model artifacts,
PETEX models, cases, outcomes, and decision records.

```text
PVT report/sample -> fluid model -> exported artifact -> PETEX model
                  -> study case -> outcome -> decision evidence
```

**Motivation:** A corrected sample, changed QC result, retuned EOS, or new
fluid model can make previous results questionable. Without traceability, that
change is discovered manually and inconsistently.

**WhitsonPVT contribution:** It supplies stable domain objects at the bottom of
the graph: reports, samples, wells, fluid models, and their engineering context.

**Result:** Autogration can identify affected outputs, label them as requiring
review or requalification, and later apply the same mechanism to reservoir,
well, facility, and economics models.

## 3. Physics-Aware Uncertainty Factory

**Idea:** Use named, coherent PVT alternatives as study realizations rather
than multiplying independent arbitrary PVT factors into every run.

**Motivation:** PVT uncertainty can change deliverability, pressure loss, phase
split, and facility limits. It is often correlated: changing an EOS tuning case
without its compatible composition or viscosity assumptions can create a fluid
description that no engineer intended.

**WhitsonPVT contribution:** Saved characterization, EOS, viscosity, sample,
and model-validation cases offer natural, engineer-reviewable realization
packages.

**Result:** Autogration can select a limited set of defensible PVT cases, screen
them cheaply, and reserve full RESOLVE/GAP runs for alternatives likely to
change a constraint or decision. They only become probability realizations when
an engineer supplies valid weights.

## 4. Operating-Envelope Watchtower

**Idea:** Compare planned and simulated operating conditions to the chosen PVT
model's evidence and phase-behaviour envelope before expensive runs or before
publishing a conclusion.

**Motivation:** A model can converge while relying on a fluid simplification at
conditions where the fluid model is weak. This matters near phase boundaries,
near-critical conditions, retrograde condensation, or when a new sample differs
materially from the existing field model.

**WhitsonPVT contribution:** Phase envelopes, flash calculations, sample
conditions, QC evidence, and fluid-model validation provide the necessary
engineering context.

**Result:** Autogration can issue a visible preflight warning, require an
acknowledged exception, or escalate the case to a higher-fidelity model. It is a
quality signal, not a replacement for GAP's network solution or live production
surveillance.

## 5. Engine-Neutral Validation Lab

**Idea:** Use declared WhitsonPVT parent and child fluid models as controlled
reference artifacts for comparing PETEX, open simulators, and later native
Autogration compute.

**Motivation:** Replacing GAP outright is a large and risky goal. A more useful
first step is to prove that any proposed model agrees on basic fluid properties
and phase behaviour before trusting its network or decision results.

**WhitsonPVT contribution:** It can provide detailed EOS models, validated
black-oil tables, lumped models, and a documented evidence trail for comparison.

**Result:** Autogration can first build PVT-table parsing, validation,
interpolation, and explicit out-of-range refusal. A transparent native PVT or
network research engine then has a benchmark path instead of relying on solver
claims.

## What These Approaches Have In Common

They do not require GAP to call WhitsonPVT during its nonlinear solve. That
would make the solve slower and couple it to a remote service. Instead, a
WhitsonPVT-backed process produces a versioned local input or response contract
that GAP can use efficiently, while Autogration retains the source and
validation trail.

The most immediately valuable foundations are approaches 1 and 2. Approach 3
becomes valuable with DOE and uncertainty planning. Approaches 4 and 5 are the
longer-term differentiators for safer operating decisions and independent
technical capability.

## Feasibility Condition

WhitsonPVT documents a tenant-specific OAuth API, but its public documentation
only demonstrates a project-scoped well read. Before committing to a direct
integration, obtain a sandbox API contract confirming which reports, samples,
QC records, fluid models, model revisions, exports, and calculations are
available programmatically.