"""Workbench layout and source opening shared by the viewer, CLI and tests."""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from autogration_results.engine import ResultStore
    from autogration_results.measures import MeasureRegistry

SourceKind = Literal["example", "autogration", "gap"]


def root() -> Path:
    env = os.environ.get("AUTOGRATION_RESULTS_HOME")
    if env:
        return Path(env)
    here = Path(__file__).resolve().parents[2]
    return here if (here / "dashboards").exists() else Path.cwd()


def measures_dir() -> Path:
    return root() / "measures"


def dashboard_dirs() -> list[Path]:
    return [root() / "dashboards", root() / "dashboards" / "custom"]


def custom_dashboard_dir() -> Path:
    return root() / "dashboards" / "custom"


def health_config_path() -> Path:
    return root() / "config" / "health.yaml"


def example_dir() -> Path:
    return root() / "examples" / "data" / "example_study"


def registry() -> MeasureRegistry:
    from autogration_results.measures import MeasureRegistry

    return MeasureRegistry.load(measures_dir())


def open_store(kind: SourceKind, path: Path | None = None) -> ResultStore:
    from autogration_results.engine import ResultStore

    reg = registry()
    if kind == "example":
        from autogration_results.examples import ensure_example

        return ResultStore.from_folder(ensure_example(path or example_dir()), reg)
    if path is None:
        raise ValueError(f"source {kind} needs a path")
    if kind == "autogration":
        return ResultStore.from_folder(path, reg)
    if kind == "gap":
        from autogration_results.sources import load_gap_folder

        return load_gap_folder(path, reg)
    raise ValueError(f"unknown source {kind}")
