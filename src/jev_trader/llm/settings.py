"""The model setting: one setting naming provider and model, and a small block of settings per
provider saying how it is called (spec appendix 5, section 9).

`config/llm.toml` holds the setting as "provider:model", the form the API reads back from a
sim's settings (`SETTINGS.llm.model`, `jev_trader.api.llm_names`), and one block per provider:
its key, its retries, how many calls it takes at once, its prices, and what LangChain's model is
built with.
"""

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

LLM_SETTINGS_PATH = Path(__file__).resolve().parents[3] / "config" / "llm.toml"
PROVIDERS = ("anthropic", "openai")


@dataclass(frozen=True)
class LlmSettings:
    model: str  # "anthropic:claude-haiku-5-5"

    def __post_init__(self):
        provider, _, name = self.model.partition(":")
        if provider not in PROVIDERS or not name:
            allowed = ", ".join(f'"{p}"' for p in PROVIDERS)
            raise ValueError(
                f'the LLM setting "{self.model}" must read "provider:model", '
                f"the provider one of {allowed}"
            )

    @property
    def provider(self) -> str:
        return self.model.partition(":")[0]

    @property
    def name(self) -> str:
        """The model without its provider: "claude-haiku-5-5"."""
        return self.model.partition(":")[2]


@dataclass(frozen=True)
class CallSettings:
    """How one provider is called: its block in `config/llm.toml`.

    `model` is handed to LangChain's `init_chat_model` as it is (thinking effort, caching, the
    provider's address). Prices are US dollars per million tokens; `cache_writes` is None where
    writing to the cache costs the input price.
    """

    service: str  # SIM.CALLS.SERVICE: "anthropic" or "zai"
    key_variable: str  # the variable in .env holding the key
    retries: int
    first_retry_wait_seconds: float
    dollars_per_million_tokens_in: float
    dollars_per_million_cached_tokens_in: float
    dollars_per_million_tokens_out: float
    dollars_per_million_cache_writes: float | None = None
    most_in_flight: int | None = None  # calls at once in this program; None: no cap
    model: dict = field(default_factory=dict)

    def cost_usd(
        self,
        tokens_in: int | None,
        cached: int | None,
        cache_writes: int | None,
        tokens_out: int | None,
    ) -> float:
        """What a call cost, from its tokens. `tokens_in` counts every token read, cached ones
        and those written to the cache included."""
        read, cached, written = tokens_in or 0, cached or 0, cache_writes or 0
        write_price = self.dollars_per_million_cache_writes
        if write_price is None:
            write_price = self.dollars_per_million_tokens_in
        dollars = (
            (read - cached - written) * self.dollars_per_million_tokens_in
            + cached * self.dollars_per_million_cached_tokens_in
            + written * write_price
            + (tokens_out or 0) * self.dollars_per_million_tokens_out
        )
        return dollars / 1e6


def load_llm_settings(path: Path = LLM_SETTINGS_PATH) -> LlmSettings:
    with open(path, "rb") as file:
        return LlmSettings(model=tomllib.load(file)["model"])


def load_call_settings(provider: str, path: Path = LLM_SETTINGS_PATH) -> CallSettings:
    """The block of `provider` ("anthropic" or "openai")."""
    with open(path, "rb") as file:
        return CallSettings(**tomllib.load(file)[provider])
