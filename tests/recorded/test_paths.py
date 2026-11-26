"""The path-coverage check (spec appendix 10, section 8): every scenario names a path from the
written list in `paths.py`, and every path has a scenario.

The service-failure paths run on hand-written fake answers: their scenarios are in
`test_service_failures.py`. The paths the real models would not take on demand run on a recorded
scenario's answers with the deciding one written by hand: `test_hand_written_answers.py`. Both
are in `COVERING` too.
"""

from tests.recorded import (
    test_hand_written_answers,
    test_scenarios,
    test_service_failures,
)
from tests.recorded.paths import PATHS

COVERING = [
    *test_scenarios.SCENARIOS,
    *test_hand_written_answers.SCENARIOS,
    *test_service_failures.SCENARIOS,
]


def test_the_list_names_each_path_once():
    assert len(set(PATHS)) == len(PATHS)


def test_every_scenario_names_a_path_from_the_list():
    unlisted = [(s.name, s.path) for s in COVERING if s.path not in PATHS]

    assert unlisted == []


def test_every_scenario_has_its_own_name():
    names = [s.name for s in COVERING]

    assert len(set(names)) == len(names)


def test_every_path_has_a_scenario():
    covered = {s.path for s in COVERING}

    assert [path for path in PATHS if path not in covered] == []
