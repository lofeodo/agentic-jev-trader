"""The API between the web app and everything else (spec appendix 8, sections 8.1 and 8.2).

It has no login, so it answers only the developer's own computer, checked twice:

- the connection must come from this computer;
- the address asked for must be this computer's. Without this, a web page open in the
  developer's browser could reach the API through a domain name pointed at 127.0.0.1.
"""

from collections.abc import Callable
from datetime import datetime, timedelta

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.middleware.trustedhost import TrustedHostMiddleware

from jev_trader.api import sim_page
from jev_trader.api.sim_jobs import Jobs, Refusal, Refused, Resumption, SimToStart
from jev_trader.api.sim_page import (
    Chart,
    LiveFigures,
    Moment,
    NoAssetKey,
    SimHeader,
    SimNotFound,
)
from jev_trader.api.sims_list import SimsList, sims_list
from jev_trader.api.store import ApiStore
from jev_trader.jobs import Launcher
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


class SpendingTotal(BaseModel):
    """Real dollars paid to Jev and the LLM so far, and the most the project may pay."""

    spent_usd: float
    ceiling_usd: float


def create_app(
    store: ApiStore,
    spending_ceiling: float,
    not_responding_after: timedelta,
    launcher: Launcher,
    clock: Callable[[], datetime] = now,
    moment_window_steps: int = 8,
) -> FastAPI:
    """`moment_window_steps`: how many steps either side of a moment count as "around then".

    `launcher` starts and kills the sims' jobs (the `JOB_LAUNCHER` setting)."""
    app = FastAPI(title="Jev trader API", version="1")
    jobs = Jobs(store, launcher, spending_ceiling, not_responding_after)

    @app.middleware("http")
    async def only_this_computer(request: Request, call_next):
        if request.client is None or request.client.host not in LOCAL_CLIENTS:
            return JSONResponse(
                {"detail": "This API answers only its own computer."}, status_code=403
            )
        return await call_next(request)

    app.add_middleware(TrustedHostMiddleware, allowed_hosts=LOCAL_HOSTS)

    @app.get("/health", operation_id="health")
    def health() -> Health:
        return Health(status="up")

    @app.get("/sims", operation_id="listSims")
    def list_sims() -> SimsList:
        return sims_list(store, clock(), not_responding_after)

    @app.exception_handler(SimNotFound)
    def no_such_sim(request: Request, missing: SimNotFound):
        return JSONResponse({"detail": f"There is no sim {missing}."}, status_code=404)

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

    @app.get("/spending/total", operation_id="spendingTotal")
    def spending_total() -> SpendingTotal:
        return SpendingTotal(
            spent_usd=store.total_spent(), ceiling_usd=spending_ceiling
        )

    return app
