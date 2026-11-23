"""One call to Jev, with its retries and its figures (spec appendix 4, sections 11 and 12).

The official SDK does the calling and the retrying, as it comes. It reads the key from
`TYPESAFE_API_KEY`. Each call reports tokens, cost, time taken, retries and the version of Jev
that answered. A call still failing after its retries raises `JevFailed`, which stops the sim.

Choices the spec leaves to the build (appendix 4, "Not decided by any ticket"):

- Retried: what the SDK retries by default (rate limited, overloaded and other server errors,
  timeouts, lost connections). A request Jev refuses, such as one too long, fails at once.
- Requests go uncompressed, so the recorded-answer files stay readable and comparable.
- If Jev reports no token count, the cost is worked out from the estimated tokens, so the
  spending cap still counts the call.
"""

import json
import time
import tomllib
from dataclasses import dataclass
from pathlib import Path

import httpx2
from typesafe_sdk import RetryPolicy, TypeSafeClient, TypeSafeError
from typesafe_sdk.constants import DEFAULT_TIMEOUT

from jev_trader.jev.reading import JevRequest

JEV_SETTINGS_PATH = Path(__file__).resolve().parents[3] / "config" / "jev.toml"
_BACKOFF_SECONDS = 0.5


class JevFailed(Exception):
    """Jev could not answer: the sim stops, and can be resumed from its last completed step."""


@dataclass(frozen=True)
class JevSettings:
    model: str
    retries: int
    dollars_per_million_tokens_read: float
    background_token_cap: int
    characters_per_token: float


def load_jev_settings(path: Path = JEV_SETTINGS_PATH) -> JevSettings:
    with open(path, "rb") as file:
        return JevSettings(**tomllib.load(file))


@dataclass(frozen=True)
class JevReply:
    """Jev's answer, word for word in `body`, and what the call took."""

    body: str
    model: str  # the version of Jev that answered
    tokens_in: int | None
    tokens_out: int | None
    cost_usd: float
    latency_seconds: float
    retries: int

    def noul(self, question: str) -> float:
        """The probability of yes, from 0 to 1, for a yes-or-no question."""
        try:
            value = json.loads(self.body)["answers"][question]["noul"]
        except (KeyError, TypeError, ValueError) as error:
            raise JevFailed(f"Jev's reply has no answer to {question}") from error
        if (
            isinstance(value, bool)
            or not isinstance(value, int | float)
            or not 0 <= value <= 1
        ):
            raise JevFailed(f"Jev's answer to {question} is not from 0 to 1: {value}")
        return value


class JevClient:
    def __init__(
        self,
        settings: JevSettings,
        *,
        api_key: str | None = None,
        transport: httpx2.BaseTransport | None = None,
        backoff_seconds: float = _BACKOFF_SECONDS,
    ):
        self.settings = settings
        self._attempts = 0
        http_client = httpx2.Client(
            timeout=DEFAULT_TIMEOUT,
            transport=transport,
            event_hooks={"request": [self._count_attempt]},
        )
        try:
            self._client = TypeSafeClient(
                api_key=api_key,
                model=settings.model,
                retry=RetryPolicy(
                    max_retries=settings.retries, backoff_initial=backoff_seconds
                ),
                http_client=http_client,
                compression=False,
            )
        except TypeSafeError:
            http_client.close()
            raise

    def _count_attempt(self, _request: httpx2.Request) -> None:
        self._attempts += 1

    def ask(self, request: JevRequest) -> JevReply:
        estimated = len(request.background) / self.settings.characters_per_token
        if estimated > self.settings.background_token_cap:
            raise JevFailed(
                f"the background is about {estimated:,.0f} tokens, above the cap of "
                f"{self.settings.background_token_cap:,}"
            )
        self._attempts = 0
        began = time.monotonic()
        try:
            response = self._client.system_one(
                state=request.background, questions=request.questions
            )
        except TypeSafeError as error:
            raise JevFailed(
                f"Jev failed after {max(0, self._attempts - 1)} retries: "
                f"{type(error).__name__}: {error}"
            ) from error
        latency = time.monotonic() - began
        tokens_in = response.usage.input_tokens
        billed = estimated if tokens_in is None else tokens_in
        return JevReply(
            body=response.raw_http_response.text,
            model=response.model,
            tokens_in=tokens_in,
            tokens_out=response.usage.output_tokens,
            cost_usd=billed * self.settings.dollars_per_million_tokens_read / 1e6,
            latency_seconds=latency,
            retries=self._attempts - 1,
        )

    def close(self) -> None:
        self._client.close()
