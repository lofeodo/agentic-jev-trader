"""The two LLM clients behind the one model setting: Claude Haiku through Anthropic and GLM Flash
through Z.ai, both built by LangChain's `init_chat_model` (spec appendix 5, sections 7 and 9;
appendix 9, section 11).

`chat_model` builds the model the setting names, with its provider's block from
`config/llm.toml`: `"anthropic:..."` is LangChain's Anthropic model, with thinking effort low and
prompt caching on; `"openai:..."` is `ChatOpenAI` pointed at Z.ai's address, with
`reasoning_effort` low. The key is read from the variable the block names and passed to the
model.

`LlmClient.call` makes one call: it offers the tools (never forcing one), holds calls to the
provider's most at once, retries, and measures the call (`LlmCall`) the way Jev's calls are
measured. A call still failing after its retries raises `LlmFailed`, which stops the sim; the
error carries the failed call's figures so it can be recorded too.

A reply's content is read by type, never by position: Haiku's reply may begin with a thinking
block, and the reply goes back in the conversation as it came, thinking blocks unchanged.

Choices the spec leaves to the build:

- Code does the retrying, not the providers' own clients, so each call's retries are counted the
  same way for both and the wait is long enough for Z.ai (whose client gives up after about 1.5
  seconds). Retried: lost connections, timeouts, and what a provider asks to be retried (408,
  409, 429 and server errors), and a refusal. Any other refusal of the request fails at once.
- The cap on calls at once holds within one program (a sim's job). Two GLM sims stay inside
  Z.ai's 4 as long as each makes one call at a time, which is the tool loop's to keep.
- When the provider names no model in its reply, the call records the model the setting names.
- A failed call's figures ride on `LlmFailed`, but the stopped step's records are not written,
  as with Jev: its stop reason and error are on the sim's row.
"""

import os
import threading
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass

import anthropic
import openai
from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage

from jev_trader.llm.settings import CallSettings, LlmSettings, load_call_settings

# Errors a provider may answer differently a moment later.
RETRIED_STATUS = (408, 409, 429)
# The finish reasons of a safety refusal.
REFUSAL_REASONS = ("refusal", "content_filter", "sensitive")


@dataclass(frozen=True)
class LlmCall:
    """What one call to the LLM took: the row it gets in SIM.CALLS.

    `model` is the model the provider says answered. Token counts are None where the provider
    reported none; `tokens_in` counts every token read, cached ones included, and `tokens_out`
    every token written, thinking included where the provider counts it so.
    """

    service: str
    model: str
    tokens_in: int | None
    cached_tokens: int | None
    tokens_out: int | None
    thinking_tokens: int | None
    cost_usd: float
    latency_seconds: float
    retries: int
    error: str | None = None


@dataclass(frozen=True)
class LlmReply:
    """The LLM's reply to one call, and what the call took."""

    message: AIMessage  # as it came: goes back in the conversation unchanged
    call: LlmCall

    @property
    def text(self) -> str:
        return reply_text(self.message)


class LlmFailed(Exception):
    """The LLM could not be used: a call still failing after its retries, or the third failed
    reply in one evaluation. It stops the sim, which can be resumed (stop reason "LLM failed").

    `call` holds the failed call's figures, its error included, when a call failed. Raised out
    of a selection (`jev_trader.llm.selection.LlmSelector.select`), it also carries what the
    evaluation had made by then: `calls`, every call to the LLM in order (the failed one last,
    when a call failed), `failed_replies` word for word, and `exchange`, every message after the
    standing instructions."""

    def __init__(self, message: str, call: LlmCall | None = None):
        super().__init__(message)
        self.call = call
        self.calls: tuple[LlmCall, ...] = () if call is None else (call,)
        self.failed_replies: tuple[str, ...] = ()
        self.exchange: tuple[dict, ...] = ()


class _Refused(Exception):
    """The provider's safety filter declined the request: a failed try."""


def chat_model(
    settings: LlmSettings, calling: CallSettings | None = None
) -> BaseChatModel:
    """The chat model `settings` names, ready for the selection's tool loop."""
    calling = calling or load_call_settings(settings.provider)
    key = os.environ.get(calling.key_variable)
    if not key:
        raise ValueError(
            f"{calling.key_variable} is not set: {settings.model} needs its key in .env"
        )
    return init_chat_model(
        settings.model,
        api_key=key,
        max_retries=0,  # code retries (`LlmClient.call`)
        **calling.model,
    )


_in_flight: dict[str, threading.BoundedSemaphore] = {}
_in_flight_lock = threading.Lock()


def _gate(model: str, most: int | None) -> threading.BoundedSemaphore | None:
    """The one gate per model that holds this program's calls to `most` at once."""
    if most is None:
        return None
    with _in_flight_lock:
        return _in_flight.setdefault(model, threading.BoundedSemaphore(most))


class LlmClient:
    """Calls to the model `settings` names, or to `model` when given (a fake in tests).

    `now` reads the time for each call's latency; `sleep` waits between tries.
    """

    def __init__(
        self,
        settings: LlmSettings,
        model: BaseChatModel | None = None,
        *,
        calling: CallSettings | None = None,
        now: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.settings = settings
        self.calling = calling or load_call_settings(settings.provider)
        self.model = model or chat_model(settings, self.calling)
        self._now, self._sleep = now, sleep
        self._gate = _gate(settings.model, self.calling.most_in_flight)

    def call(self, messages: Sequence[BaseMessage], tools: Sequence = ()) -> LlmReply:
        """One call: `messages` sent with `tools` on offer, none forced.

        Raises `LlmFailed` once the call has failed its first try and every retry.
        """
        runnable = self.model.bind_tools(list(tools)) if tools else self.model
        began = self._now()
        retries = 0
        while True:
            try:
                message = self._invoke(runnable, list(messages))
                return LlmReply(message, self._measured(message, began, retries))
            except (anthropic.APIError, openai.APIError, _Refused) as error:
                if not _worth_retrying(error) or retries == self.calling.retries:
                    call = self._failed(error, began, retries)
                    raise LlmFailed(
                        f"the LLM failed after {retries} retries: {call.error}", call
                    ) from error
                self._sleep(self.calling.first_retry_wait_seconds * 2**retries)
                retries += 1

    def _invoke(self, runnable, messages: list[BaseMessage]) -> AIMessage:
        if self._gate is None:
            message = runnable.invoke(messages)
        else:
            with self._gate:
                message = runnable.invoke(messages)
        metadata = message.response_metadata or {}
        reasons = (
            metadata.get("normalized_finish_reason"),
            metadata.get("finish_reason"),
        )
        if any(reason in REFUSAL_REASONS for reason in reasons):
            raise _Refused(f"the provider refused the request ({reasons[1]})")
        return message

    def _measured(self, message: AIMessage, began: float, retries: int) -> LlmCall:
        usage = message.usage_metadata or {}
        read = usage.get("input_token_details") or {}
        written = usage.get("output_token_details") or {}
        metadata = message.response_metadata or {}
        tokens_in, tokens_out = usage.get("input_tokens"), usage.get("output_tokens")
        cached = read.get("cache_read")
        return LlmCall(
            service=self.calling.service,
            model=metadata.get("model_name")
            or metadata.get("model")
            or self.settings.name,
            tokens_in=tokens_in,
            cached_tokens=cached,
            tokens_out=tokens_out,
            thinking_tokens=written.get("reasoning"),
            cost_usd=self.calling.cost_usd(
                tokens_in, cached, read.get("cache_creation"), tokens_out
            ),
            latency_seconds=self._now() - began,
            retries=retries,
        )

    def _failed(self, error: Exception, began: float, retries: int) -> LlmCall:
        return LlmCall(
            service=self.calling.service,
            model=self.settings.name,
            tokens_in=None,
            cached_tokens=None,
            tokens_out=None,
            thinking_tokens=None,
            cost_usd=0.0,
            latency_seconds=self._now() - began,
            retries=retries,
            error=f"{type(error).__name__}: {error}",
        )


def _worth_retrying(error: Exception) -> bool:
    if isinstance(
        error, _Refused | anthropic.APIConnectionError | openai.APIConnectionError
    ):
        return True
    status = getattr(error, "status_code", None)
    return status is not None and (status in RETRIED_STATUS or status >= 500)


def reply_text(message: BaseMessage) -> str:
    """The reply's text, read from its text blocks by type: thinking and tool calls left out."""
    if isinstance(message.content, str):
        return message.content
    return "".join(
        block if isinstance(block, str) else block.get("text", "")
        for block in message.content
        if isinstance(block, str) or block.get("type") == "text"
    )
