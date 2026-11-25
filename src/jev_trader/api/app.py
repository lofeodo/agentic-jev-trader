"""The API between the web app and everything else (spec appendix 8, sections 8.1 and 8.2).

It has no login, so it answers only the developer's own computer, checked twice:

- the connection must come from this computer;
- the address asked for must be this computer's. Without this, a web page open in the
  developer's browser could reach the API through a domain name pointed at 127.0.0.1.
"""

from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Annotated

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.middleware.trustedhost import TrustedHostMiddleware

from jev_trader.api import sim_page
from jev_trader.api.comparison import Comparison, comparison
from jev_trader.api.datasets import (
    DatasetBuilds,
    DatasetNotFound,
    DatasetPage,
    DatasetsList,
    DatasetStarted,
    DatasetToBuild,
    PriceChart,
)
from jev_trader.api.llm_names import model_label
from jev_trader.api.measurements import Measurements, measurements
from jev_trader.api.playbook import Playbook, playbook
from jev_trader.api.scorecard import Scorecard, Split, scorecard
from jev_trader.api.sim_jobs import (
    Jobs,
    Refusal,
    Refused,
    Resumption,
    SimCheck,
    SimToStart,
)
from jev_trader.api.sim_page import (
    Chart,
    LiveFigures,
    Moment,
    NoAssetKey,
    SimHeader,
    SimNotFound,
)
from jev_trader.api.sims_list import SimsList, sims_list
from jev_trader.api.spending import Spending, spending
from jev_trader.api.store import ApiStore
from jev_trader.api.trades import Filters, TradesTable, trades_table
from jev_trader.jobs import Builds, Launcher
from jev_trader.llm.models import load_model_settings
from jev_trader.sim.store import now

LOCAL_CLIENTS = frozenset({"127.0.0.1", "::1"})
LOCAL_HOSTS = ["localhost", "127.0.0.1", "[::1]"]


class Health(BaseModel):
    status: str


class Refusals(BaseModel):
    """Why a request to start, stop or resume was refused: every reason at once."""

    refusals: list[Refusal]


class SimsStarted(BaseModel):
    sim_ids: list[int]


REFUSED = {
    409: {"model": Refusals, "description": "Refused: the reasons, and how to fix each"}
}


class ModelOption(BaseModel):
    model: str  # as a sim names it, such as "claude-haiku-5-5"
    label: str  # as the developer reads it, such as "Claude Haiku"


class ModelChoice(BaseModel):
    """The LLMs a sim may name and the one a free sim uses unless the developer picks another
    (`config/llm.toml`)."""

    models: list[ModelOption]
    default_model: str


class SpendingTotal(BaseModel):
    """Real dollars paid to Jev and the LLM so far, and the most the project may pay."""

    spent_usd: float
    ceiling_usd: float


def create_app(
    store: ApiStore,
    spending_ceiling: float,
    not_responding_after: timedelta,
    launcher: Launcher,
    builds: Builds,
    clock: Callable[[], datetime] = now,
    moment_window_steps: int = 8,
) -> FastAPI:
    """`moment_window_steps`: how many steps either side of a moment count as "around then".

    `launcher` starts and kills the sims' jobs, `builds` the dataset builds' (both as the
    `JOB_LAUNCHER` setting says)."""
    app = FastAPI(title="Jev trader API", version="1")
    jobs = Jobs(store, launcher, spending_ceiling, not_responding_after)
    datasets = DatasetBuilds(store, builds)

    @app.middleware("http")
    async def only_this_computer(request: Request, call_next):
        if request.client is None or request.client.host not in LOCAL_CLIENTS:
            return JSONResponse(
                {"detail": "This API answers only its own computer."}, status_code=403
            )
        return await call_next(request)

    app.add_middleware(TrustedHostMiddleware, allowed_hosts=LOCAL_HOSTS)

    # A finished sim never changes, so its reports are worked out once and kept here, in memory
    # only (appendix 8, section 8.9). Nothing stores a finished report.
    reports: dict[tuple, BaseModel] = {}

    def kept[Report: BaseModel](
        key: tuple, sim_id: int, work: Callable[[], Report]
    ) -> Report:
        if key in reports:
            return reports[key]  # type: ignore[return-value]
        # Checked before the work: a sim that finishes meanwhile may be missing its last steps.
        finished = sim_page.never_changes(store, sim_id)
        report = work()
        if finished:
            reports[key] = report
        return report

    @app.get("/health", operation_id="health")
    def health() -> Health:
        return Health(status="up")

    @app.get("/sims", operation_id="listSims")
    def list_sims() -> SimsList:
        return sims_list(store, clock(), not_responding_after)

    @app.exception_handler(SimNotFound)
    def no_such_sim(request: Request, missing: SimNotFound):
        return JSONResponse({"detail": f"There is no sim {missing}."}, status_code=404)

    # Before `/sims/{sim_id}`, which would otherwise take "check" for a sim's ID.
    @app.get("/sims/check", operation_id="checkSim")
    def check_sim(wanted: Annotated[SimToStart, Query()]) -> SimCheck:
        """May this sim start, and what would it cost? Takes what starting a sim takes; stores
        nothing and starts nothing. The New trading sim form asks it as its choices change."""
        return jobs.check(wanted)

    @app.get("/sims/{sim_id}", operation_id="simHeader")
    def sim_header(sim_id: int) -> SimHeader:
        return sim_page.header(store, sim_id, clock(), not_responding_after)

    @app.get("/sims/{sim_id}/chart", operation_id="simChart")
    def sim_chart(sim_id: int) -> Chart:
        return sim_page.chart(store, sim_id, moment_window_steps)

    @app.get("/sims/{sim_id}/live", operation_id="simLive")
    def sim_live(sim_id: int, after_step: int | None = None) -> LiveFigures:
        """The quick figures, asked for every second while the sim is in progress.

        `after_step`: the last step the page has chart points for; only later ones are sent.
        """
        return sim_page.live(store, sim_id, clock(), not_responding_after, after_step)

    @app.get("/sims/{sim_id}/moment", operation_id="simMoment")
    def sim_moment(sim_id: int, at: datetime) -> Moment:
        """The account, its positions, and the trades around one moment.

        `at`: a real time, UTC. The moment is the step that ended at or just before it.
        """
        try:
            return sim_page.moment(store, sim_id, at, moment_window_steps)
        except NoAssetKey as missing:
            raise HTTPException(status_code=409, detail=str(missing)) from missing

    @app.get("/sims/{sim_id}/trades", operation_id="simTrades")
    def sim_trades(
        sim_id: int,
        lost_money: bool = False,
        trimmed: bool = False,
        stop_price: bool = False,
        overnight: bool = False,
        no_trade: bool = False,
        page: Annotated[int, Query(ge=1)] = 1,
        page_size: Annotated[int, Query(ge=1, le=500)] = 50,
    ) -> TradesTable:
        """The trades table, a page at a time, oldest first.

        Each of `lost_money`, `trimmed` (by a risk limit), `stop_price` (closed at it) and
        `overnight` (held past midnight UTC) keeps only the trades it names; `no_trade` adds the
        full evaluations that ended in no trade.
        """
        filters = Filters(lost_money, trimmed, stop_price, overnight, no_trade)
        return kept(
            ("trades", sim_id, filters, page, page_size),
            sim_id,
            lambda: trades_table(store, sim_id, filters, page, page_size),
        )

    @app.get("/sims/{sim_id}/measurements", operation_id="simMeasurements")
    def sim_measurements(sim_id: int) -> Measurements:
        """The six groups of measurements, each beside holding the five assets."""
        return kept(
            ("measurements", sim_id), sim_id, lambda: measurements(store, sim_id)
        )

    @app.get("/sims/{sim_id}/scorecard", operation_id="simScorecard")
    def sim_scorecard(
        sim_id: int, split: Annotated[list[Split] | None, Query()] = None
    ) -> Scorecard:
        """How the sim's closed trades did, by candle pattern, direction and asset class.

        `split` (repeatable): also split each line by trend, volume level or part of the day.
        """
        parts = sorted(set(split or []))
        return kept(
            ("scorecard", sim_id, tuple(parts)),
            sim_id,
            lambda: scorecard(store, sim_id, parts),
        )

    @app.get("/comparison", operation_id="comparison")
    def read_comparison() -> Comparison:
        """Per market and per LLM: did memory help, hurt, or can't we tell; both winners."""
        return comparison(store)

    @app.get("/playbook", operation_id="playbook")
    def read_playbook() -> Playbook:
        return playbook(store)

    @app.get("/spending", operation_id="spending")
    def read_spending() -> Spending:
        return spending(store, spending_ceiling)

    @app.get("/models", operation_id="modelChoice")
    def model_choice() -> ModelChoice:
        """The New trading sim form's Model choice: the models, and the default it pre-selects."""
        settings = load_model_settings()
        return ModelChoice(
            models=[
                ModelOption(model=m, label=model_label(m)) for m in settings.models
            ],
            default_model=settings.default_model,
        )

    @app.exception_handler(Refused)
    def refused(request: Request, refused: Refused):
        body = Refusals(refusals=refused.refusals)
        return JSONResponse(body.model_dump(), status_code=409)

    @app.post("/sims", operation_id="startSim", status_code=202, responses=REFUSED)
    def start_sim(wanted: SimToStart) -> SimsStarted:
        """Store the sim, then start its job. Practice and tuning sims start only from the
        command line."""
        return SimsStarted(sim_ids=jobs.start(wanted, clock()))

    @app.post("/sims/{sim_id}/stop", operation_id="stopSim", responses=REFUSED)
    def stop_sim(sim_id: int) -> SimHeader:
        """Kill the sim's job at once and mark it stopped by hand. Its half-done step is redone
        on resume."""
        jobs.stop(sim_id, clock())
        return sim_page.header(store, sim_id, clock(), not_responding_after)

    @app.post(
        "/sims/{sim_id}/resume",
        operation_id="resumeSim",
        status_code=202,
        responses=REFUSED,
    )
    def resume_sim(sim_id: int, wanted: Resumption) -> SimHeader:
        """Start a stopped or not responding sim again from its last stored step. A sim stopped
        by its spending cap needs a new cap."""
        jobs.resume(sim_id, wanted, clock())
        return sim_page.header(store, sim_id, clock(), not_responding_after)

    @app.exception_handler(DatasetNotFound)
    def no_such_dataset(request: Request, missing: DatasetNotFound):
        return JSONResponse(
            {"detail": f"There is no dataset {missing}."}, status_code=404
        )

    @app.get("/datasets", operation_id="listDatasets")
    def list_datasets() -> DatasetsList:
        return datasets.list()

    @app.post(
        "/datasets", operation_id="buildDataset", status_code=202, responses=REFUSED
    )
    def build_dataset(wanted: DatasetToBuild) -> DatasetStarted:
        """Add the dataset's row, being built, and start its build job. The check against
        the two limits is the build's first step."""
        return datasets.start(wanted, clock().date())

    @app.get("/datasets/{dataset_id}", operation_id="datasetPage")
    def dataset_page(dataset_id: int) -> DatasetPage:
        return datasets.page(dataset_id)

    @app.get("/datasets/{dataset_id}/bars", operation_id="datasetBars")
    def dataset_bars(dataset_id: int, ticker: str) -> PriceChart:
        """One asset's price chart: each day's close. `ticker`: the asset's real ticker."""
        return datasets.chart(dataset_id, ticker)

    @app.post(
        "/datasets/{dataset_id}/stop", operation_id="stopDataset", responses=REFUSED
    )
    def stop_dataset(dataset_id: int) -> DatasetPage:
        """Kill the build and mark it failed, stopped by hand."""
        return datasets.stop(dataset_id)

    @app.get("/spending/total", operation_id="spendingTotal")
    def spending_total() -> SpendingTotal:
        return SpendingTotal(
            spent_usd=store.total_spent(), ceiling_usd=spending_ceiling
        )

    return app
