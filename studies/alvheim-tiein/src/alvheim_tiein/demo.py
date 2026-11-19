"""A complete demo data folder built from synthetic data, to try the analysis today.

Results come from ``results-workbench/examples/data/example_study`` (synthetic GAP-like
runs). It becomes the project ``demo``: its infill wells (licences PL102 and PL201) play
the new reservoir and "Low sep" the baseline. Companies, shares, prices and tariffs are
the fictional files in ``examples/demo``. Nothing here describes Alvheim.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

import pandas as pd
import yaml

from alvheim_tiein.config import STUDY_ROOT
from alvheim_tiein.project import RunLog, Workspace

WORKBENCH_EXAMPLE = (
    STUDY_ROOT.parents[1] / "results-workbench" / "examples" / "data" / "example_study"
)
DEMO_REFERENCE = STUDY_ROOT / "examples" / "demo"
DEMO_SLUG = "demo"
DEMO_BASELINE = "Low sep"
DEMO_WITH = "Low sep + Infill wells"


def _case_name(label: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_")


def build_demo_data(target: Path, example: Path = WORKBENCH_EXAMPLE) -> Path:
    """Write ``target/reference`` and the project ``target/projects/demo``; return target."""
    cases = pd.read_csv(example / "cases.csv")
    if target.exists():
        shutil.rmtree(target)
    reference = target / "reference"
    reference.mkdir(parents=True)
    for name in ("licence_shares.csv", "prices.csv", "economics.yaml"):
        shutil.copyfile(DEMO_REFERENCE / name, reference / name)
    shutil.copyfile(example / "entities.csv", reference / "entities.csv")

    ws = Workspace(target)
    paths = ws.paths(DEMO_SLUG)
    paths.results.mkdir(parents=True)
    for task_id in cases["task_id"]:
        src = example / "results" / f"{task_id}.parquet"
        if src.exists():
            shutil.copyfile(src, paths.results / src.name)

    project_cases = []
    for r in cases.itertuples():
        is_baseline = r.case_name == DEMO_BASELINE
        project_cases.append(
            {
                "name": _case_name(r.case_name),
                "baseline": is_baseline,
                "switch": "on" if r.infill == "yes" else "off",
                "description": f"Synthetic: sep {r.sep_pressure} bar, gas lift {r.gas_lift}",
                "case_labels": {1: r.case_name},
            }
        )
    project = {
        "name": "DEMO (synthetic data, fictional economics)",
        "type": "case_comparison",
        "asset": "Demo",
        "model_id": "demo",
        "switch": {
            "label": "Infill wells",
            "off_from": "2025-01-01",
            "wells": [
                {"name": "A-P7", "path": "RESOLVE.MODULE[0].MOD[0].EQUIP[7]"},
                {"name": "B-P4", "path": "RESOLVE.MODULE[0].MOD[0].EQUIP[11]"},
            ],
        },
        "bookings": {"groups": [], "track_applied": False},
        "analysis": {"user_licenses": ["PL102", "PL201"]},
        "cases": project_cases,
    }
    paths.definition.write_text(yaml.safe_dump(project, sort_keys=False), encoding="utf-8")

    log = RunLog(paths.runs)
    for r in cases.itertuples():
        name = _case_name(r.case_name)
        log.record_submission(
            name,
            "demo",
            {"user_specified_name": f"{project['name']} | {name}"},
            {"assumption_group_id": f"demo-{r.run_number}", "case_count": 1},
            1,
        )
        log.record_tasks(name, [{"task_id": r.task_id, "assumption_case": 1, "status": r.status}])
    log.save()
    ws.use(DEMO_SLUG)
    return target
