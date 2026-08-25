# Source Ledger

Status date: 2026-08-25. This is a research index, not an archive of licensed
or copyrighted source material. Summaries elsewhere in this directory are
original notes. Priority means expected value to the next technical decision.

## P0: PETEX behavior and Autogration boundary

| Source | Type | What it establishes | Status |
| --- | --- | --- | --- |
| [PETEX IPM suite](https://www.petex.com/pe-engineering/ipm-suite/) | Official product page | IPM component map; OpenServer/RESOLVE connect products and third-party software | Summarised |
| [GAP](https://www.petex.com/products/ipm-suite/gap/) | Official product page | Steady-state equation-based network, optimisation, rule-based forecasts | Summarised |
| [RESOLVE](https://www.petex.com/products/ipm-suite/resolve/) | Official product page | Coupling, scenarios, probabilistic studies, adaptive timesteps, multilevel optimisation | Summarised |
| [REVEAL](https://www.petex.com/products/ipm-suite/reveal/) | Official product page | Thermal finite-difference specialised reservoir simulation | Summarised |
| [GAP/RESOLVE runtime case study](https://www.petex.com/practical-solutions/case-studies/1-integrated-production-modelling/) | Official case study | Vendor description of Jacobian cost/density, parallelisation, PVT/flash, and formulation effects | Summarised as vendor evidence |
| [PROSPER](https://www.petex.com/products/ipm-suite/prosper/) | Official product page | IPR/VLP, multiphase well/pipeline and lift-response context | Summarised |
| [MBAL](https://www.petex.com/products/ipm-suite/mbal/) | Official product page | Analytical reservoir models and fast proxy-style calculations | Summarised |
| [OpenServer](https://www.petex.com/pe-engineering/ipm-suite/openserver/) | Official product page | `DoSet`, `DoCmd`, `DoGet`, external automation, and generic third-party wrapper positioning | Summarised; inspect licensed manuals for exact behavior |
| [GAP Transient](https://www.petex.com/pe-engineering/ipm-suite/gap-transient/) | Official product page | Separate transient multiphase/thermal/reservoir-response capability and time-scale distinction | Summarised |
| Official PETEX manuals, OpenServer help, release notes, training examples | Licensed/internal material | Exact supported API and observable engine behavior | Acquire lawfully; do not archive verbatim here |
| Autogration sibling repositories | Internal source | Current orchestration, scenario expansion, and OpenServer execution boundary | Initial review summarised |

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