"""The API between the web app and everything else (spec appendix 8, sections 8.1 and 8.2).

It has no login, so it answers only the developer's own computer, checked twice:

- the connection must come from this computer;
- the address asked for must be this computer's. Without this, a web page open in the
  developer's browser could reach the API through a domain name pointed at 127.0.0.1.
"""

from collections.abc import Callable
from datetime import datetime, timedelta

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.middleware.trustedhost import TrustedHostMiddleware

from jev_trader.api.sims_list import SimsList, sims_list
from jev_trader.api.store import ApiStore
from jev_trader.sim.store import now

LOCAL_CLIENTS = frozenset({"127.0.0.1", "::1"})
LOCAL_HOSTS = ["localhost", "127.0.0.1", "[::1]"]


class Health(BaseModel):
    status: str


class SpendingTotal(BaseModel):
    """Real dollars paid to Jev and the LLM so far, and the most the project may pay."""

    spent_usd: float
    ceiling_usd: float


def create_app(
    store: ApiStore,
    spending_ceiling: float,
    not_responding_after: timedelta = timedelta(minutes=7),
    clock: Callable[[], datetime] = now,
) -> FastAPI:
    app = FastAPI(title="Jev trader API", version="1")

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

    @app.get("/spending/total", operation_id="spendingTotal")
    def spending_total() -> SpendingTotal:
        return SpendingTotal(
            spent_usd=store.total_spent(), ceiling_usd=spending_ceiling
        )

    return app
