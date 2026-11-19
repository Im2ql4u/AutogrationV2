# Source Ledger

Status date: 2026-10-13. This is a research index, not an archive of licensed
or copyrighted source material. Summaries elsewhere in this directory are
original notes. Priority means expected value to the next technical decision.

## P0: PETEX behavior and Autogration boundary

| Source | Type | What it establishes | Status |
| --- | --- | --- | --- |
| [PETEX IPM suite](https://www.petex.com/products/integrated-production-modelling-suite/) | Official product page | IPM component map and positioning of reservoir, well, network, optimisation, and OpenServer integration | Summarised; capability boundary, not an algorithm specification |
| [GAP](https://www.petex.com/products/integrated-production-modelling-suite/gap/) | Official product page | Proprietary equation-based steady-state pressure/flow/temperature balance, nonlinear optimisation, and compositional/black-oil PVT support | Summarised 2026-09-10; no public setting or internal timing details |
| [RESOLVE](https://www.petex.com/products/integrated-production-modelling-suite/resolve/) | Official product page | Reusable Data Objects, multilevel optimisation, PVT lumping/delumping, parallel scenario workflows, and advertised clustering/hyperthreading | Summarised 2026-09-10; verify licence, installed-version support, configuration, scope, and diagnostics before experiment design |
| [REVEAL](https://www.petex.com/products/integrated-production-modelling-suite/reveal/) | Official product page | Thermal finite-difference specialised reservoir simulation | Summarised |
| [Former GAP/RESOLVE runtime case-study URL](https://www.petex.com/practical-solutions/case-studies/1-integrated-production-modelling/) | Historical vendor page, now unavailable | Indexed remnants point to Jacobian cost/density, parallelisation, PVT/flash, data reuse, and formulation effects | Original URL returns 404; no checked Wayback snapshot; portions of `344 -> 17.8` and `10.5 s -> 3.5 min optimisation` survive only as search-index fragments; `3.7 s` and the meaning of `0.5%` remain unverified; request the source through licensed PETEX channels |
| [PROSPER](https://www.petex.com/products/integrated-production-modelling-suite/prosper/) | Official product page | IPR/VLP, multiphase well/pipeline and lift-response context | Summarised |
| [MBAL](https://www.petex.com/products/integrated-production-modelling-suite/mbal/) | Official product page | Analytical reservoir models and fast proxy-style calculations | Summarised |
| [OpenServer](https://www.petex.com/products/integrated-production-modelling-suite/openserver/) | Official product page | `DoSet`, `DoCmd`, `DoGet`, external batch automation, generic third-party wrapper positioning, and RESOLVE visual workflows | Summarised 2026-09-10; does not publicly specify performance counters, cache/session semantics, or supported optimization tags |
| [GAP Transient](https://www.petex.com/products/integrated-production-modelling-suite/gap-transient/) | Official product page | Separate transient multiphase/thermal/reservoir-response capability and time-scale distinction | Summarised |
| Official PETEX manuals, OpenServer help, release notes, training examples | Licensed/internal material | Exact supported API and observable engine behavior | Acquire lawfully; do not archive verbatim here |
| Autogration sibling repositories | Internal source | Current orchestration, scenario expansion, and OpenServer execution boundary | Initial review summarised |
| [WhitsonPVT API](https://manual.pvt.whitson.com/api/) | Vendor documentation | OAuth external API is provisioned on request; static documentation shows a project-scoped wells read and says detailed endpoints are client specific | Summarised 2026-09-08; obtain sandbox contract before claiming endpoint support |
| [WhitsonPVT manual and black-oil methodology](https://manual.pvt.whitson.com/methods/child_models/black_oil_tables/) | Vendor documentation | PVT data/QC, parent EOS and child-model workflow, PVT calculations, and documented black-oil assumptions/failure cases | Summarised 2026-09-08; vendor behaviour, not a complete implementation specification |

## P0: governed run discovery and analysis

| Source | Type | What it establishes | Status |
| --- | --- | --- | --- |
| [Aker BP Goose](https://github.com/AkerBP/goose) | Open source application, revision `3faf39a` | Entra/CDF user-context authentication, governed MCP tools, reference-first datasets, sandboxed analysis, lineage-aware artifacts, and chat/client visualization patterns | Source inspected 2026-10-13; CDF surface retrieves known operational time-series IDs but does not discover Autogration simulation ensembles or runs |

## P0: inspectable numerical-simulation references

| Source | Type | What it establishes | Status |
| --- | --- | --- | --- |
| [OPM Flow](https://opm-project.org/?page_id=19) | Open project documentation | Fully implicit black-oil formulation, AD, Newton/NLDD, adaptive step control, CPR/ILU/multigrid families | Summarised |
| [OPM Flow reference manual](https://opm-project.org/?page_id=955) | Open manual | Current manual, input/output and simulator reference | Read next for selected benchmark topics |
| [OPM linear-solver guide](https://opm-project.org/?page_id=1798) | Open documentation | BiCGSTAB/CPR and tuning examples; case-dependent linear-solver behavior | Summarised |
| [MRST project](https://www.sintef.no/projectweb/mrst/) | Open research software | Research-oriented modular reservoir simulation and links to methods | Summarised |
| [MRST publications and books](https://www.sintef.no/projectweb/mrst/publications/) | Open books/papers index | Open-access introductory and advanced books, code/data examples, MRST-AD reference | Summarised |
| [MRST-AD paper](https://doi.org/10.2118/173317-MS) | Conference paper | Automatic-differentiation framework for reservoir simulation prototyping | Read alongside source when implementing |
| [Advanced Modelling with MRST](https://doi.org/10.1017/9781009019781) | Open-access book | Reproducible modern multiphase-flow methods and examples | P0 reading |

## P1: partitioning and coupling

| Source | Type | What it establishes | Status |
| --- | --- | --- | --- |
| [Gosselin and Thomas, domain decomposition](https://www.earthdoc.org/content/papers/10.3997/2214-4609.201411120) | Conference paper abstract | Interface pressures, saturations, and fluxes; iterative subdomain convergence and boundary-condition choices | Summarised |
| [Nacul, local grid refinement and domain decomposition](https://www.osti.gov/biblio/6087846) | Dissertation record/abstract | Dirichlet/Neumann interfaces, relaxation, overlap, and coarse-to-fine initial conditions | Summarised |
| OPM/MRST coupling and multiscale modules | Open software/docs | Reproducible code paths for advanced partition experiments | Triage after benchmark definition |
| PETEX RESOLVE coupling/visual-workflow manuals | Licensed/internal material | Actual supported coupling scope and control semantics | Acquire lawfully |

## P1: uncertainty, decisions, and surrogates

| Source | Type | What it establishes | Status |
| --- | --- | --- | --- |
| [Experimental Design in reservoir simulation](https://doi.org/10.1007/s13202-012-0023-0) | Peer-reviewed paper | DOE applied to uncertainty investigation in reservoir simulation | Obtain lawful full text; metadata identified |
| [Reservoir surrogate under uncertainty](https://jpt.spe.org/deep-learning-based-reservoir-surrogate-achieves-optimization-under-uncertainty-restricted) | SPE/JPT feature | Deep proxy use for constrained optimisation under geological uncertainty; high-fidelity cost motivation | Summarised; full primary paper is licensed |
| [Uncertainty Quantification in Reservoir Simulation Using Modern Data Analytics](https://www.mdpi.com/1996-1073/16/3/1153) | Open-access article | Candidate modern UQ case study | Access verification/review pending |
| SPE/OnePetro papers on history matching, ensemble methods, robust optimisation, and value of information | Professional literature | Decision-grade methodology and field-specific evidence | Build a licensed reading pack with reservoir engineers |

## P2: talks, courses, and ongoing discovery

| Source family | Purpose | Intake rule |
| --- | --- | --- |
| [OPM talks and publications](https://opm-project.org/?page_id=39) and OPM Summit material | Solver design, parallelism, open benchmarks | Prefer recordings/slides released by OPM |
| [MRST Symposium](https://www.sintef.no/projectweb/mrst/mrst-symposium-2023/) | Advanced modelling, workflows, and current methods | Capture session, speaker, date, and takeaways in an original note |
| SPE conferences and OnePetro | Reservoir engineering, uncertainty, coupled modelling, economics | Respect access rights; record citation and original summary only |
| Vendor user meetings and training | Practical GAP/RESOLVE/REVEAL behavior | Obtain through licence or customer relationship; do not ingest restricted materials into source control |

## Intake standard for every new source

Record the source URL/citation, access date, authority, license/access status,
the exact question it answers, a short original summary, confidence level, and
one action or falsifiable hypothesis it creates. Keep supplier claims explicitly
labeled. A source is not "read" until it has changed a benchmark, design
decision, or research question.