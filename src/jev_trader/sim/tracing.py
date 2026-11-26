"""Tracing a sample of full evaluations to LangSmith (spec appendix 9, section 14).

A trace is LangSmith's record of one full evaluation: its Jev requests and, with memory, the
LLM's selection step by step. It is for looking at examples; nothing reads it back. A sim's
records of every call (tokens, cost, time taken) are in our own database either way.

- Tracing runs only when the environment switches LangSmith's tracing on (`LANGSMITH_TRACING`)
  and holds its key (`LANGSMITH_API_KEY`). Otherwise, and in every test, nothing is sent. The
  project traces go to is LangSmith's own setting, `LANGSMITH_PROJECT`.
- One trace per full evaluation, never one for a check or a position review: the whole sim runs
  with tracing switched off, and only a full evaluation switches it on, inside its trace.
- The share traced is LangSmith's own sampling rate (`tracing_sampling_rate`), set by sim kind in
  `config/tracing.toml`: 1 for practice sims, 1/30 for measurement sims. LangSmith keeps or drops
  a whole trace by its ID, so a trace is never cut in part.
- Tracing never stops a sim. LangSmith sends from a thread of its own and only logs a refusal
  (HTTP 429 past the free plan's allowance) or an unreachable server; anything raised while a
  trace is opened or closed is logged and the full evaluation carries on untraced.

Choices the spec leaves to the build:

- Tuning, build-up and free sims trace 1 in 30, as measurement sims do.
- A full evaluation's trace starts after its screen said yes and holds the pick and the size
  (each Jev request a step of its own, with its background, questions and reply), and with
  memory the LLM's selection. Its result is the pick and what was done.
- No trace link is kept on an episode yet: no table has a column for it, and nothing reads it.
"""

import json
import logging
import os
import tomllib
from collections.abc import Iterator
from contextlib import AbstractContextManager, ExitStack, contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from langsmith import Client, get_current_run_tree, trace, tracing_context
from langsmith.utils import tracing_is_enabled

from jev_trader.broker.config import CONFIG_DIR

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TracingSettings:
    one_in: dict[str, int]  # 1 in N full evaluations traced, by sim kind

    def sampling_rate(self, kind: str) -> float:
        return 1 / self.one_in[kind]


def load_tracing_settings(path: Path = CONFIG_DIR / "tracing.toml") -> TracingSettings:
    with open(path, "rb") as file:
        return TracingSettings(**tomllib.load(file))


def switched_on(environ: dict[str, str] | None = None) -> bool:
    """LangSmith's own switch is on and its key is set."""
    environ = os.environ if environ is None else environ
    return bool(environ.get("LANGSMITH_API_KEY")) and tracing_is_enabled()


class Traced:
    """The open trace of one full evaluation, or nothing when it is not traced."""

    def __init__(self, run: Any = None):
        self._run = run

    def result(self, outputs: dict) -> None:
        """What the full evaluation came to, shown as the trace's result."""
        if self._run is not None:
            _quietly(self._run.add_outputs, outputs)


class Tracing:
    """Opens one trace per full evaluation through `client`; with no client, sends nothing."""

    def __init__(self, client: Client | None = None):
        self.client = client

    @classmethod
    def for_kind(cls, kind: str, settings: TracingSettings | None = None) -> "Tracing":
        """The tracing a sim of `kind` runs with: off unless the environment switches it on."""
        if not switched_on():
            return cls()
        rate = (settings or load_tracing_settings()).sampling_rate(kind)
        try:
            return cls(Client(tracing_sampling_rate=rate))
        except Exception:  # a bad setting must not stop the sim
            logger.exception("LangSmith tracing is off")
            return cls()

    def off(self) -> AbstractContextManager:
        """Tracing switched off, so checks, reviews and the steps around them send nothing."""
        return tracing_context(enabled=False)

    @contextmanager
    def full_evaluation(self, sim_id: int, step: int, asset: str) -> Iterator[Traced]:
        """One full evaluation's trace. LangSmith keeps it at the sim's sampling rate."""
        if self.client is None:
            yield Traced()
            return
        details = {"sim_id": sim_id, "step": step, "asset": asset}

        def open_trace(stack: ExitStack):
            stack.enter_context(tracing_context(enabled=True, client=self.client))
            return stack.enter_context(
                trace(
                    "full_evaluation",
                    run_type="chain",
                    inputs=details,
                    metadata=details,
                    client=self.client,
                )
            )

        with _guarded(open_trace) as run:
            yield Traced(run)

    @contextmanager
    def jev_request(
        self, purpose: str, background: str, questions: dict
    ) -> Iterator[Traced]:
        """One Jev request as a step of the open trace; nothing outside one."""
        if self.client is None or get_current_run_tree() is None:
            yield Traced()
            return
        with _guarded(
            lambda stack: stack.enter_context(
                trace(
                    f"jev_{purpose}",
                    run_type="llm",
                    inputs={"background": background, "questions": questions},
                )
            )
        ) as run:
            yield Traced(run)


def jev_reply_outputs(body: str) -> dict:
    """Jev's reply as the step's result: its JSON, or the text when it is not JSON."""
    try:
        return json.loads(body)
    except ValueError:
        return {"reply": body}


@contextmanager
def _guarded(open_trace) -> Iterator[Any]:
    """Open a trace with `open_trace(stack)`, run the body, then close it. A failure opening or
    closing it is logged and the body runs untraced; the body's own errors pass through."""
    stack = ExitStack()
    run = None
    try:
        run = open_trace(stack)
    except Exception:
        logger.exception("LangSmith trace not opened; the sim carries on")
        _quietly(stack.close)
        stack = ExitStack()
    try:
        yield run
    except BaseException as error:
        _quietly(stack.__exit__, type(error), error, error.__traceback__)
        raise
    else:
        _quietly(stack.close)


def _quietly(action, *args) -> None:
    try:
        action(*args)
    except Exception:
        logger.exception("LangSmith tracing step failed; the sim carries on")
