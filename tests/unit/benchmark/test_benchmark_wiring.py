"""The LLM benchmark's frame, wired end to end with made-up parts (the slice's skeleton): the
command parses its switches, then asks the spend meter, runs each attempt and keeps it, in order,
and hands every attempt to the report. What each part does is tested with the slice's own tests.
"""

import pytest

from jev_trader.benchmark import NotBuilt, records, report, runner, spending
from jev_trader.benchmark import __main__ as command
from jev_trader.benchmark.moments import SavedMoment, saved_moments
from jev_trader.benchmark.runner import Attempt, Outcome, SelectionRunner
from jev_trader.llm.selection import ReviewedPosition, Situation
from jev_trader.memory.episodes import Standing
from jev_trader.memory.lookups import SearchResult

HAIKU, GLM = "anthropic:claude-haiku-5-5", "openai:glm-5.3-flash"


def moment(step: int, review: bool = False) -> SavedMoment:
    position = None
    if review:
        position = ReviewedPosition(
            Standing(
                direction="long",
                put_in=1000.0,
                bars_open=3,
                profit=4.0,
                percent=0.4,
                stop_distance=0.01,
                best=6.0,
                worst=-2.0,
            )
        )
    situation = Situation(
        asset="ASSET_A",
        asset_class="crypto",
        step=step,
        text="made-up situation",
        patterns=(),
        playbook={},
        position=position,
    )
    return SavedMoment(
        sim=12, situation=situation, first_search=SearchResult(episodes=[])
    )


MOMENTS = [moment(4410), moment(4420, review=True)]


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
def steps(monkeypatch, tmp_path) -> Steps:
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

    runs = [s for s in steps.seen if s[0] == "run"]
    assert [(model, n) for _, model, n, _ in runs[::2]] == [
        (HAIKU, 1),
        (HAIKU, 2),
        (HAIKU, 3),
        (GLM, 1),
        (GLM, 2),
        (GLM, 3),
    ]
    assert len(runs) == 2 * 3 * len(MOMENTS)
    first = MOMENTS[0].id
    assert steps.seen[:5] == [
        ("parts", 12, "TRADING_AGENT"),
        ("check",),
        ("run", HAIKU, 1, first),
        ("add", 0),
        ("keep", HAIKU, first),
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


def test_the_real_command_says_what_is_not_built(capsys, tmp_path):
    report_file = tmp_path / "report.md"
    assert command.main(["--sim", "12", "--report", str(report_file)]) == 2
    assert "not built yet" in capsys.readouterr().out
    assert not report_file.exists()


@pytest.mark.parametrize(
    "stub",
    [
        lambda: saved_moments(12, "TRADING_AGENT"),
        lambda: SelectionRunner(lambda context: None).run(MOMENTS[0], None, 1),
        lambda: spending.SpendMeter(1.5).spent_usd,
        lambda: spending.SpendMeter(1.5).check(),
        lambda: spending.SpendMeter(1.5).add(0.1),
        lambda: records.call_rows(None),
        lambda: records.SnowflakeAttemptLog(None).keep(None),
        lambda: report.report(runner.BenchmarkRun(())),
    ],
)
def test_each_stub_says_it_is_not_built(stub):
    with pytest.raises(NotBuilt, match="not built yet"):
        stub()
