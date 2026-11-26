"""The path-coverage check (spec appendix 10, section 8): every scenario names a path from the
written list in `paths.py`, and every path has a scenario.

A test of the service-failure paths, which run on hand-written fake answers, adds its scenarios
to `COVERING` too.
"""

import pytest

from tests.recorded import test_scenarios
from tests.recorded.paths import PATHS

COVERING = [*test_scenarios.SCENARIOS]


def test_the_list_names_each_path_once():
    assert len(set(PATHS)) == len(PATHS)


def test_every_scenario_names_a_path_from_the_list():
    unlisted = [(s.name, s.path) for s in COVERING if s.path not in PATHS]

    assert unlisted == []


def test_every_scenario_has_its_own_name():
    names = [s.name for s in COVERING]

    assert len(set(names)) == len(names)


@pytest.mark.dormant
def test_every_path_has_a_scenario():
    covered = {s.path for s in COVERING}

    assert [path for path in PATHS if path not in covered] == []
