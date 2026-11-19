"""Write the study notebooks (00, 01, 03) for projects. Run with the study's .venv."""

from __future__ import annotations

from pathlib import Path

import nbformat
from nbformat.v4 import new_code_cell, new_markdown_cell, new_notebook

ROOT = Path(__file__).resolve().parent
KERNEL = {
    "kernelspec": {
        "name": "alvheim-tiein",
        "display_name": "alvheim-tiein (study .venv)",
        "language": "python",
    },
    "language_info": {"name": "python"},
}
KERNEL_NOTE = (
    "Kernel: **alvheim-tiein (study .venv)** (`studies/alvheim-tiein/.venv`; "
    "`uv sync` there first). The repo's own environment lacks pandas and the study package."
)


def md(text: str):
    return new_markdown_cell(text.strip("\n"))


def code(text: str):
    return new_code_cell(text.strip("\n"))


def write(name: str, cells: list) -> None:
    nb = new_notebook(cells=cells, metadata=KERNEL)
    nbformat.validate(nb)
    path = ROOT / name
    nbformat.write(nb, path)
    print("wrote", path)


SETUP = """
import pandas as pd
import plotly.express as px

from alvheim_tiein import report
from alvheim_tiein.client import AutogrationClient, step_results_frame
from alvheim_tiein.config import Settings
from alvheim_tiein.project import RunLog, Workspace

settings = Settings.from_env()
ws = Workspace(settings.data_dir)
api = AutogrationClient.from_env(settings)
print(settings.api_url, "| auth:", settings.resolved_auth())
api.me()
"""

write(
    "00_access_and_monitoring.ipynb",
    [
        md(f"""
# Access, projects and run monitoring

{KERNEL_NOTE}

Runs that are compared belong to a **project** (`tiein project new`): a type, an
environment, a baseline case and the cases compared against it, including runs made
elsewhere (`tiein project add-run`). Projects are optional: one-off runs use `tiein run`.
This notebook only reads; runs are started deliberately with `tiein submit <case>`, which
refuses more than the project's run limit (at most 50 at once).
"""),
        code(SETUP),
        md("## Projects"),
        code("""
listing = []
for slug in ws.slugs():
    p, _, log = ws.load(slug)
    statuses = [r["status"] for r in log.rows(p)]
    listing.append({"project": slug, "current": slug == ws.current(), "name": p.name,
                    "type": p.type.value, "baseline": p.baseline_case.name,
                    "cases": len(p.cases), "runs": len(statuses),
                    "completed": statuses.count("Completed")})
pd.DataFrame(listing)
"""),
        code("""
PROJECT = None  # project slug; None = the current one (`tiein project use <slug>`)
data = report.load_project(ws, PROJECT)
p = data.project
api = AutogrationClient.from_env(settings.for_environment(p.environment))  # the project's runs live there
print(f"{p.name} [{data.slug}, {p.type.value}, {p.environment or 'default'}] model {p.model_id}")
if p.switch:
    print(f"switch: {p.switch.label} ({', '.join(w.name for w in p.switch.wells)}) off from {p.switch.off_from}")
print(f"baseline: {p.baseline_case.name}; booking groups: {', '.join(p.bookings.groups)}")
data.runs
"""),
        md("""
## Run status

Same as `tiein status` (VS Code task **Study: status (watch)**), without updating the run log.
"""),
        code("""
log = RunLog(data.paths.runs)
for case, entry in log.cases.items():
    role = " (baseline)" if case == p.baseline_case.name else " (imported)" if entry.get("imported") else ""
    if entry.get("assumption_group_id") and not entry.get("imported"):
        progress = api.group_progress(entry["assumption_group_id"]).summary()
    else:
        progress = ", ".join(t["status"] for t in entry["tasks"].values())
    print(f"{case + role:<32} {progress}")
"""),
        md("""
### Tracked variables of a run

The project's `tracked_variables` and, with `bookings.track_applied`, the booking limits
the model applies are recorded at every solver step, so constraint pressure is visible
while the case runs.
"""),
        code("""
CASE, RUN = None, 1  # e.g. "baseline"; RUN numbers the runs of a sweep
if CASE:
    task_id = data.runs.loc[data.runs["case"] == CASE, "task_id"].iloc[RUN - 1]
    steps = step_results_frame(api.step_results(task_id))
    steps["short"] = steps["variable"].str.replace(r"^resolve\\.module\\[0\\]\\.MOD\\[\\{\\w+\\}\\]\\.", "", regex=True)
    px.line(steps, x="time", y="value", color="short", title=f"{CASE} run {RUN}").show()
"""),
        md("## Registered models and simulations on the asset"),
        code("""
ASSET = p.asset
models = pd.DataFrame(api.registered_models(asset=ASSET))
models[["task_id", "user_specified_name", "created_at"]] if not models.empty else models
"""),
        code("""
sims = pd.DataFrame(api.task_page(asset=ASSET, task_type="petex_compute", limit=200)["items"])
if sims.empty:
    print("no simulations on", ASSET)
else:
    display(sims.groupby(["user_specified_name", "status"]).size().unstack(fill_value=0))
"""),
        md("""
## Explore the project's model

Equipment, RESOLVE settings and the optimiser's objective, controls and constraints. The
booking levers of each well (gas-lift injection, production choke dP) are listed by
`tiein project levers`.
"""),
        code("""
MODEL_ID = p.model_id
display(api.browse(MODEL_ID, search="FL1"))
pd.DataFrame(api.resolve_settings(MODEL_ID)).head(50)
"""),
    ],
)

write(
    "01_with_without_settlement.ipynb",
    [
        md(f"""
# Baseline vs a case: production, value and who pays whom

{KERNEL_NOTE}

Pick a **project** and a case to compare with its baseline. With `DEMO = True` this runs on
**synthetic results and fictional economics** (the `demo` project: `results-workbench`'s
example study, whose infill wells play the new reservoir; companies, shares, prices and
tariffs from `examples/demo`).
"""),
        code("""
DEMO = True
PROJECT = None   # project slug; None = the current one
CASE = None      # case to compare with the baseline; None = the first switched-on (else other) case
UNCAPPED = None  # optional: the case with facility limits relaxed (e.g. "tie_in_uncapped")
"""),
        code("""
import pandas as pd
import plotly.express as px

from alvheim_tiein import report
from alvheim_tiein import settlement as s
from alvheim_tiein.config import Settings
from alvheim_tiein.demo import DEMO_WITH, build_demo_data
from alvheim_tiein.economics import Reference, value_volumes
from alvheim_tiein.project import Workspace
from alvheim_tiein.results import (
    export_workbench_folder,
    load_task_results,
    period_volumes,
    volume_convention_check,
)

settings = Settings.from_env()
ws = Workspace(build_demo_data(settings.data_dir / "demo") if DEMO else settings.data_dir)
data = report.load_project(ws, "demo" if DEMO else PROJECT)
cases = data.runs
done = data.completed()
BASE = data.baseline_name
switched_on = done.loc[done["switch"] == "on", "case_name"].tolist()
others = [c for c in done["case_name"] if c != BASE]
ALT = DEMO_WITH if DEMO else (CASE or (switched_on or others or [None])[0])
USERS = data.project.analysis.user_licenses
banner = "DEMO: synthetic results, fictional economics\\n" if DEMO else ""
print(f"{banner}{data.project.name}: {BASE!r} -> {ALT!r}; paying licence(s) {USERS}")
cases
"""),
        code("""
results = load_task_results(done.to_dict("records"), data.paths.results)
volume_convention_check(results)
"""),
        md("""
The check compares volumes from rates with cumulative-oil increments. Volumes below use the
`forward` convention (a timestep's rate holds until the next timestep). If `backward` fits a
real model clearly better, change `period_volumes` before trusting the numbers.
"""),
        code("""
ref = Reference.load(ws.reference_dir(data.paths))
valued = value_volumes(period_volumes(results), ref)
CUR = ref.economics.currency
valued.groupby("case_name")[["oil_sm3", "gas_sm3", "water_sm3", "pv"]].sum().round(0)
"""),
        md("## 1. What changes, well by well"),
        code("""
wells = s.compare(valued, BASE, ALT, by=("field", "license", "identifier"))
wells["delta_oil_ksm3"] = wells["delta_oil_sm3"] / 1e3
px.bar(
    wells.sort_values("delta_oil_sm3"), x="identifier", y="delta_oil_ksm3", color="license",
    title=f"Oil, {ALT} minus {BASE} (kSm3)",
).show()
wells[["field", "license", "identifier", "delta_oil_sm3", "delta_gas_sm3", "delta_water_sm3", "delta_pv"]].round(0)
"""),
        code("""
monthly = s.totals(valued[valued["case_name"].isin([BASE, ALT])], by=("license", "period"), values=("oil_sm3",))
wide = monthly.pivot_table(index=["license", "period"], columns="case_name", values="oil_sm3").reset_index()
wide["delta_oil_sm3"] = wide[ALT] - wide[BASE]
px.line(
    wide, x="period", y="delta_oil_sm3", color="license",
    title="Monthly oil change per licence (Sm3). Deferral = a dip later recovered; loss = never recovered",
).show()
"""),
        code("""
lic = s.compare(valued, BASE, ALT, by=("license",))
lic[["license", "delta_oe_sm3", "delta_cash_flow", "delta_pv"]].round(0)
"""),
        md("""
`delta_cash_flow` is undiscounted, `delta_pv` discounted. A licence whose undiscounted change is
near zero but whose PV falls had production **deferred**; if both fall, production was **lost**
within the simulated horizon. Volumes deferred past the end of the simulation look lost, so
the horizon must run to the end of field life for this distinction to hold.
"""),
        code("""
if UNCAPPED and UNCAPPED in set(done["case_name"]):
    display(s.decompose(valued, BASE, ALT, UNCAPPED, by=("license",)).round(0))
else:
    print("No uncapped case: the back-pressure vs capacity-displacement split needs one (set UNCAPPED)")
"""),
        md("""
## 2. Who pays whom

First-model rules (see `settlement.py`): the paying licence(s) compensate every other licence
for its lost value (PV), and pay the change in tariffs. Licence flows are spread over both
sides' company shares. The diagonal of the matrix is a company paying itself through
different licences.
"""),
        code("""
st = s.settle(valued, ref, BASE, ALT, USERS)
st.licence_flows.round(0)
"""),
        code("""
print(f"payer (rows) -> payee (columns), million {CUR}")
(st.company_matrix / 1e6).round(2)
"""),
        code("""
net = st.net.rename_axis("company").reset_index()
px.bar(net, x="company", y="net_received", title=f"Net received from settlement ({CUR}; negative = pays)").show()
net.round(0)
"""),
        md("""
## 3. Hub value vs company value

Settlement payments cancel out in total hub value, so the hub's best case does not depend on
them; each company's best case can. The price of conflict is what the hub loses if one
company's preferred case were chosen.
"""),
        code("""
table = s.objective_table(valued, ref)
value_cols = ["hub", *[c for c in ref.companies() if c in table]]
display((table[value_cols] / 1e6).round(1))
table[[f"rank_{c}" for c in value_cols]]
"""),
        code("""
pd.DataFrame({c: s.price_of_conflict(table, c) for c in value_cols if c != "hub"}).T
"""),
        md("## 4. Inspect in results-workbench"),
        code("""
wb = export_workbench_folder(
    cases.to_dict("records"), data.paths.results, data.paths.workbench,
    baseline=BASE, entities_csv=ws.reference_dir(data.paths) / "entities.csv",
)
print("Run the VS Code task 'Study: results viewer', choose 'Autogration export folder' and paste:", wb)
"""),
    ],
)

write(
    "03_project_bookings.ipynb",
    [
        md(f"""
# Bookings: baseline vs cases, per group and per company

{KERNEL_NOTE}

The model books FPSO capacity per tie-back group (Boyla+Frosk, Volund, Vilje+Skogul,
Tyrving) and limits each group's rates to its booking every timestep. The question, in
order:

1. **Baseline** (new reservoir off): are the bookings met?
2. **Tuned baseline**: where they are not, adjust each well's gas-lift injection and
   production choke dP (a case `based_on: baseline` in `project.yaml`; current values with
   `tiein project levers`) until they are.
3. **Tie-in** (`based_on` the tuned baseline, switched on): how the system changes.
4. **Compare**: produced minus booked per group and company, and how that moves when the
   reservoir comes on; should the bookings change?

Booked rates are what the model applied when the run tracked them
(`bookings.track_applied`), otherwise the booking tables. Per company, a group's booking
is split by its wells' licence shares, weighted by what each well produced. The new
reservoir has no booking, so it shows as an unbooked group. Rates in Sm3/d (gas too).
"""),
        code("""
PROJECT = None  # project slug; None = the current one
CASE = None     # case to look at against the baseline; None = the first switched-on (else other) case
PHASE = "gas"   # oil, gas, water (booked to 2027-09) or liquid (booked after)
OFFLINE = False # True: only cached model data (no sign-in)
"""),
        code("""
import pandas as pd
import plotly.express as px

from alvheim_tiein import report
from alvheim_tiein.client import AutogrationClient
from alvheim_tiein.config import Settings
from alvheim_tiein.project import Workspace

settings = Settings.from_env()
ws = Workspace(settings.data_dir)
data = report.load_project(ws, PROJECT)
api = None if OFFLINE else AutogrationClient.from_env(settings.for_environment(data.project.environment))
done = data.completed()
BASE = data.baseline_name
switched_on = done.loc[done["switch"] == "on", "case_name"].tolist()
others = [c for c in done["case_name"] if c != BASE]
FOCUS = CASE or (switched_on or others or [None])[0]
print(f"{data.project.name} [{data.slug}]: baseline {BASE!r}, looking at {FOCUS!r}")
data.runs
"""),
        code("""
if done.empty:
    raise SystemExit("no completed runs yet: `tiein status`, then `tiein fetch`")
rep = report.booking_report(ws, data, api)
display(rep.sources)
violations = rep.violations()
if not violations.empty:
    print(f"{len(violations)} group-periods more than 2 % above the applied limit (GAP not honouring it; "
          "gas only checked when lift gas is tracked):")
    display(violations.head(20))
summary = rep.summary()
summary.round({"booked_sm3d": 0, "produced_sm3d": 0, "delta_sm3d": 0, "below_booking": 2, "at_booking": 2, "above_booking": 2})
"""),
        md("""
## 1. Baseline: are the bookings met?

Utilisation = produced / booked per group and month. Below 1 the group produced less than
it booked; at 1 the booking binds; above 1 the model let it produce more than the table.
"""),
        code("""
sat = rep.satisfaction()
base = sat[(sat["case_name"] == BASE) & sat["booked_sm3d"].notna()]
fig = px.line(
    base, x="period", y=["produced_sm3d", "booked_sm3d"], facet_row="group", facet_col="phase",
    title=f"{BASE}: produced vs booked (Sm3/d)", height=900,
)
fig.update_yaxes(matches=None)
fig.show()
heat = base[base["phase"] == PHASE].pivot_table(index="group", columns="period", values="utilisation")
px.imshow(heat, color_continuous_scale="RdBu", color_continuous_midpoint=1.0, aspect="auto",
          title=f"{BASE}: {PHASE} utilisation of booking").show()
"""),
        md("""
## 2. Produced minus booked, per company: baseline vs each case

Each company's share of its groups' production minus its share of the booking.
"""),
        code("""
cd = rep.company_delta()
cd = cd[(cd["phase"] == PHASE) & cd["booked_sm3d"].notna()]
fig = px.line(
    cd, x="period", y="delta_sm3d", color="company", line_dash="case_name", facet_row="group",
    title=f"{PHASE}: produced - booked per company (Sm3/d)", height=900,
)
fig.update_yaxes(matches=None)
fig.add_hline(y=0, line_color="grey")
fig.show()
"""),
        md("""
## 3. What changes when the reservoir comes on

The change in each company's delta from the baseline: negative means a company produces
further below (or less above) its booking because of the case.
"""),
        code("""
ch = rep.change_vs_baseline()
ch = ch[ch["phase"] == PHASE].copy()
ch["year"] = pd.to_datetime(ch["period"]).dt.year
yearly = ch.groupby(["case_name", "group", "company", "year"], as_index=False)[
    ["change_in_delta_sm3d", "change_in_produced_sm3d"]
].mean()
fig = px.bar(
    yearly, x="year", y="change_in_produced_sm3d", color="company", facet_row="group",
    facet_col="case_name", barmode="relative", height=900,
    title=f"{PHASE}: change in production vs {BASE}, per company (yearly mean, Sm3/d)",
)
fig.update_yaxes(matches=None)
fig.show()
yearly[yearly["case_name"] == FOCUS].pivot_table(
    index=["group", "company"], columns="year", values="change_in_delta_sm3d"
).round(0)
"""),
        md("""
## 4. The wells behind each group

Each well's production per company in the focus case, against the group's booking.
"""),
        code("""
wc = rep.well_contributions()
wc = wc[(wc["case_name"] == FOCUS) & (wc["phase"] == PHASE)]
per_well = wc.groupby(["group", "identifier", "period"], as_index=False)["produced_sm3d"].sum()
fig = px.area(per_well, x="period", y="produced_sm3d", color="identifier", facet_row="group",
              title=f"{FOCUS}: {PHASE} per well (Sm3/d)", height=900)
fig.update_yaxes(matches=None)
booked = sat[(sat["case_name"] == FOCUS) & (sat["phase"] == PHASE) & sat["booked_sm3d"].notna()]
for i, group in enumerate(reversed(per_well["group"].unique().tolist()), start=1):
    line = booked[booked["group"] == group]
    fig.add_scatter(x=line["period"], y=line["booked_sm3d"], mode="lines", name=f"{group} booked",
                    line={"color": "black", "dash": "dot"}, row=i, col=1)
fig.show()
"""),
        md("""
## 5. Should the bookings change?

Volume each company is short of (negative) or over (positive) its booking over the
forecast, baseline and each case: integrate the delta over each period's days.
"""),
        code("""
d = rep.company_delta()
d = d[d["booked_sm3d"].notna()].sort_values("period")
days = (
    d[["case_name", "period"]].drop_duplicates().sort_values(["case_name", "period"])
    .assign(days=lambda f: f.groupby("case_name")["period"].diff().shift(-1).dt.days)
)
d = d.merge(days, on=["case_name", "period"])
d["delta_ksm3"] = d["delta_sm3d"] * d["days"].fillna(30) / 1e3
d.pivot_table(index=["group", "company"], columns=["phase", "case_name"], values="delta_ksm3", aggfunc="sum").round(0)
"""),
        md("""
Groups whose production stays below the booking once the reservoir comes on, while the
baseline met it, carry booked capacity the tie-in takes: the volumes above are the input
to who pays whom (notebook 01) and to whether the bookings should be redistributed.
Bookings could also be changed per case through `dataobject_tables` changes on
`Bookings_*` cells and run again.
"""),
    ],
)
