"""The LLM benchmark's frame, wired end to end with made-up parts (the slice's skeleton): the
command parses its switches, then asks the spend meter, runs each attempt and keeps it, in order,
and hands every attempt to the report. What each part does is tested with the slice's own tests.
"""

import pytest

from jev_trader.benchmark import NotBuilt, report, runner, spending
from jev_trader.benchmark import __main__ as command
from jev_trader.benchmark.attempts import Attempt, Outcome
from jev_trader.benchmark.made_up import made_up_moments

HAIKU, GLM = "anthropic:claude-haiku-5-5", "openai:glm-5.3-flash"
MOMENTS = made_up_moments()[1:3]  # a full evaluation and a position review


class Steps:
    """Every part's calls, in order."""

    def __init__(self):
        self.seen: list[tuple] = []


class FakeRunner:
    def __init__(self, steps: Steps):
        self.steps = steps

    def run(self, moment, model, pass_number) -> Attempt:
        self.steps.seen.append(("run", model.model, pass_number, moment.id))
        return Attempt(moment, model.model, pass_number, Outcome.FINE, (), ())


class FakeMeter(spending.SpendMeter):
    def __init__(self, steps: Steps):
        super().__init__(cap_usd=1.5)
        self.steps = steps

    def check(self) -> None:
        self.steps.seen.append(("check",))

    def add(self, cost_usd: float) -> None:
        self.steps.seen.append(("add", cost_usd))


class FakeLog:
    def __init__(self, steps: Steps):
        self.steps = steps

    def keep(self, attempt) -> None:
        self.steps.seen.append(("keep", attempt.model, attempt.moment.id))


@pytest.fixture
def steps(monkeypatch) -> Steps:
    steps = Steps()
    monkeypatch.setattr(command, "SpendMeter", lambda cap: FakeMeter(steps))

    def fake_report(run) -> str:
        steps.seen.append(("report", len(run.attempts)))
        return "made-up report\n"

    monkeypatch.setattr(command, "report", fake_report)
    return steps


def run_command(steps: Steps, tmp_path, *switches: str) -> int:
    def parts_for(args, held):
        steps.seen.append(("parts", args.sim, args.database))
        return command.Parts(MOMENTS, FakeRunner(steps), FakeLog(steps))

    argv = ["--sim", "12", "--report", str(tmp_path / "report.md"), *switches]
    return command.main(argv, parts_for=parts_for)


def test_the_command_calls_each_part_in_order(steps, tmp_path):
    assert run_command(steps, tmp_path) == 0

    runs = [s[1:] for s in steps.seen if s[0] == "run"]
    full, review = (m.id for m in MOMENTS)
    assert runs[:4] == [
        (HAIKU, 1, full),
        (GLM, 1, full),
        (HAIKU, 1, review),
        (GLM, 1, review),
    ]
    assert [n for _, n, _ in runs] == [1] * 4 + [2] * 4 + [3] * 4
    assert steps.seen[:5] == [
        ("parts", 12, "TRADING_AGENT"),
        ("check",),
        ("run", HAIKU, 1, full),
        ("add", 0),
        ("keep", HAIKU, full),
    ]
    assert steps.seen[-1] == ("report", 12)
    assert (tmp_path / "report.md").read_text(encoding="utf-8") == "made-up report\n"


def test_one_model_alone(steps, tmp_path):
    assert run_command(steps, tmp_path, "--model", "glm-5.3-flash") == 0

    models = {s[1] for s in steps.seen if s[0] == "run"}
    assert models == {GLM}


def test_the_meter_stops_the_run_and_the_report_still_gets_what_ran(
    steps, tmp_path, monkeypatch
):
    class StopsAtOnce(FakeMeter):
        def check(self) -> None:
            raise spending.CapReached("made-up stop")

    monkeypatch.setattr(command, "SpendMeter", lambda cap: StopsAtOnce(steps))

    assert run_command(steps, tmp_path) == 0
    assert [s for s in steps.seen if s[0] == "run"] == []
    assert steps.seen[-1] == ("report", 0)


def test_made_up_moments_reach_the_report_with_no_outside_part(capsys, tmp_path):
    report_file = tmp_path / "report.md"
    assert command.main(["--made-up", "--report", str(report_file)]) == 2
    assert (
        "not built yet: the benchmark's plain-words report" in capsys.readouterr().out
    )
    assert not report_file.exists()


@pytest.mark.parametrize(
    "stub",
    [
        lambda: report.report(runner.BenchmarkRun(())),
    ],
)
def test_each_stub_says_it_is_not_built(stub):
    with pytest.raises(NotBuilt, match="not built yet"):
        stub()
