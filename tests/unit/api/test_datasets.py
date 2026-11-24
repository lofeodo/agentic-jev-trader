"""The Datasets and Dataset screens' endpoints, and builds through the API (spec appendix 8,
section 8.11; appendix 7, section 9).

Builds are real `build_dataset` runs on made-up providers into the in-memory store; the jobs
that would run them are stand-ins noting what they were asked. The real job is tested in
`tests/unit/test_jobs.py`.
"""

from datetime import date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from jev_trader.api.app import create_app
from jev_trader.api.store import InMemoryApiStore
from jev_trader.dataset.build import build_dataset
from jev_trader.dataset.settings import load_settings
from jev_trader.dataset.store import InMemoryStore
from jev_trader.sim.store import InMemorySimStore
from tests.unit.api.conftest import StandInBuilds, StandInLauncher
from tests.unit.dataset.test_build import BUILD_DAY, FakeCrypto, FakeStocks, settings

NOW = datetime(2026, 11, 24, 12, 0)


@pytest.fixture
def datasets():
    return InMemoryStore()


@pytest.fixture
def builds():
    return StandInBuilds()


@pytest.fixture
def api(datasets, builds):
    app = create_app(
        InMemoryApiStore(InMemorySimStore(), [], datasets=datasets),
        spending_ceiling=75.0,
        not_responding_after=timedelta(minutes=7),
        clock=lambda: NOW,
        launcher=StandInLauncher(),
        builds=builds,
    )
    return TestClient(app, base_url="http://localhost", client=("127.0.0.1", 50000))


def run_build(datasets, dataset_id=None, stocks=None, check=True, **changes):
    """Run the build the job would run, into the API's store."""
    build_dataset(
        settings(**changes),
        stocks=stocks or FakeStocks(),
        crypto=FakeCrypto(),
        store=datasets,
        today=BUILD_DAY,
        check=check,
        report=lambda line: None,
        dataset_id=dataset_id,
    )


FORM = {
    "tickers": ["xyz", "BTC"],
    "first_day": "2023-01-03",
    "last_day": "2023-07-07",
    "test_periods": [
        {"name": "falling market", "first_day": "2023-07-06", "last_day": "2023-07-07"}
    ],
}


def test_asking_for_a_build_adds_its_row_and_starts_its_job_on_the_typed_tickers(
    api, builds, tmp_path
):
    answer = api.post("/datasets", json=FORM)

    assert answer.status_code == 202
    dataset_id = answer.json()["dataset_id"]
    [(started, text, check)] = builds.started
    assert (started, check) == (dataset_id, True)
    path = tmp_path / "asked.toml"
    path.write_text(text, encoding="utf-8")
    asked = load_settings(path)
    assert [a.ticker for a in asked.assets] == ["XYZ", "BTC"]
    assert asked.limits.partial_volume_days == 0.03
    assert asked.limits.other_missing == 0.005
    assert [p.name for p in asked.test_periods] == ["falling market"]

    [line] = api.get("/datasets").json()["datasets"]
    assert line["id"] == dataset_id
    assert line["status"] == "being built"
    assert line["progress"] == 0.0
    assert line["tickers"] == ["XYZ", "BTC"]
    assert (line["first_day"], line["last_day"]) == ("2023-01-03", "2023-07-07")


def test_the_check_switch_off_starts_the_build_without_the_check(api, builds):
    api.post("/datasets", json={**FORM, "check": False})
    [(_, _, check)] = builds.started
    assert check is False


def test_a_bad_request_is_refused_with_every_reason_at_once(api, builds):
    answer = api.post(
        "/datasets",
        json={
            "tickers": [" "],
            "first_day": "2026-11-20",
            "last_day": "2026-11-24",
            "limit_partial_volume_days": 1.5,
            "test_periods": [
                {
                    "name": "rising market",
                    "first_day": "2026-12-01",
                    "last_day": "2026-12-02",
                }
            ],
        },
    )

    assert answer.status_code == 409
    codes = {r["code"] for r in answer.json()["refusals"]}
    assert codes == {
        "no_tickers",
        "last_day_too_recent",
        "limit_out_of_range",
        "period_outside",
    }
    assert not builds.started


def test_a_test_period_inside_the_warm_up_is_refused(api):
    """The first three months no sim trades, so no sim could be measured there."""
    answer = api.post(
        "/datasets",
        json={
            **FORM,
            "test_periods": [
                {
                    "name": "falling market",
                    "first_day": "2023-02-01",
                    "last_day": "2023-02-10",
                }
            ],
        },
    )
    assert answer.status_code == 409
    [refusal] = answer.json()["refusals"]
    assert refusal["code"] == "period_in_warm_up"


def test_one_build_at_a_time(api, builds):
    api.post("/datasets", json=FORM)
    answer = api.post("/datasets", json=FORM)
    assert answer.status_code == 409
    assert [r["code"] for r in answer.json()["refusals"]] == ["build_in_progress"]


def test_a_published_dataset_shows_its_check_quality_report_and_asset_key(
    api, datasets
):
    run_build(
        datasets, stocks=FakeStocks(zero_volume_on=[date(2023, 7, 5)]), check=False
    )
    [dataset_id] = datasets.datasets

    page = api.get(f"/datasets/{dataset_id}").json()

    assert page["status"] == "published"
    assert page["published_without_check"] is True
    assert page["progress"] == 1.0
    assert page["stages"][0] == {"name": "Start and check", "starts_at": 0.0}
    check = page["check"]
    assert check["passed"] is False  # one of four sessions is a partial-volume day
    stock = check["assets"][0]
    assert stock["asset"] == {"name": "Made-up Corp", "masked_id": "ASSET_01"}
    assert stock["partial_volume_share"] == pytest.approx(0.25)
    assert stock["over"] == ["partial-volume days"]

    assert [(k["ticker"], k["name"], k["asset_class"]) for k in page["asset_key"]] == [
        ("XYZ", "Made-up Corp", "stock"),
        ("COIN", "Made-up Coin", "crypto"),
    ]
    assert {
        "name": "falling market",
        "kind": "test",
        "first_day": "2023-07-06",
        "last_day": "2023-07-07",
    } in page["periods"]

    [day] = page["partial_volume_days"]
    assert day["asset"]["name"] == "Made-up Corp"
    assert day["day"] == "2023-07-05"
    assert day["test"] == "a zero-volume bar"
    missing = page["missing_bars"]
    assert len(missing) == 26  # the whole day
    assert {m["reason"] for m in missing} == {"partial-volume day"}
    # The first bar of 5 July opens at 13:30 UTC (9:30 New York time) and ends at 13:45.
    assert missing[0]["ends_at"] == "2023-07-05T13:45:00"


def test_a_dataset_over_a_limit_says_which_asset_by_its_typed_ticker(api, datasets):
    form = {**FORM, "tickers": ["xyz"]}
    dataset_id = api.post("/datasets", json=form).json()["dataset_id"]
    run_build(
        datasets,
        dataset_id=dataset_id,
        stocks=FakeStocks(zero_volume_on=[date(2023, 7, 5)]),
        assets=settings().assets[:1],
    )

    page = api.get(f"/datasets/{dataset_id}").json()

    assert page["status"] == "failed"
    assert page["check"]["assets"][0]["asset"] == {
        "name": "XYZ",
        "masked_id": "ASSET_01",
    }
    assert "XYZ" in page["failure_reason"]
    assert "ASSET_01" not in page["failure_reason"]
    assert page["asset_key"] == []


def test_the_price_chart_is_each_days_close_in_real_dollars(api, datasets):
    run_build(datasets)
    [dataset_id] = datasets.datasets

    chart = api.get(f"/datasets/{dataset_id}/bars", params={"ticker": "xyz"}).json()

    assert chart["asset"] == {"name": "Made-up Corp", "masked_id": "ASSET_01"}
    # 3 July closes early at $63.50 (14th bar); 4 July is a holiday; 5 July closes at $75.50.
    assert chart["points"][:2] == [
        {"day": "2023-07-03", "close": {"real": 63.5, "rescaled": 127.0}},
        {"day": "2023-07-05", "close": {"real": 75.5, "rescaled": 151.0}},
    ]
    assert (
        api.get(f"/datasets/{dataset_id}/bars", params={"ticker": "ABC"}).status_code
        == 404
    )


def test_stop_kills_the_build_and_marks_it_failed_stopped_by_hand(
    api, builds, datasets
):
    dataset_id = api.post("/datasets", json=FORM).json()["dataset_id"]

    answer = api.post(f"/datasets/{dataset_id}/stop")

    assert answer.status_code == 200
    assert builds.stopped == [dataset_id]
    assert answer.json()["status"] == "failed"
    assert answer.json()["failure_reason"] == "stopped by hand"
    assert datasets.datasets[dataset_id]["FAILURE_REASON"] == "stopped by hand"


def test_a_build_whose_job_will_not_die_is_left_as_it_was(api, builds, datasets):
    dataset_id = api.post("/datasets", json=FORM).json()["dataset_id"]
    builds.will_not_die = True

    answer = api.post(f"/datasets/{dataset_id}/stop")

    assert answer.status_code == 409
    assert [r["code"] for r in answer.json()["refusals"]] == ["job_not_killed"]
    assert datasets.datasets[dataset_id]["STATUS"] == "being built"


def test_only_a_build_in_progress_can_be_stopped(api, datasets):
    run_build(datasets)
    [dataset_id] = datasets.datasets
    answer = api.post(f"/datasets/{dataset_id}/stop")
    assert answer.status_code == 409
    assert [r["code"] for r in answer.json()["refusals"]] == ["nothing_to_stop"]
    assert api.post("/datasets/99/stop").status_code == 404
    assert api.get("/datasets/99").status_code == 404
