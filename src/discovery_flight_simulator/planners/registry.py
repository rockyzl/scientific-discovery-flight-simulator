"""Public planner registry used by the CLI."""

from __future__ import annotations

from .baselines import ExpectedInformationGainPlanner, FixedGridPlanner, RandomValidPlanner


def default_planners() -> dict[str, type]:
    return {
        "random": RandomValidPlanner,
        "fixed_grid": FixedGridPlanner,
        "information_gain": ExpectedInformationGainPlanner,
    }
