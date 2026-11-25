"""The model setting: one setting naming provider and model (spec appendix 5, section 9).

`config/llm.toml` holds it as "provider:model", the form the API reads back from a sim's settings
(`SETTINGS.llm.model`, `jev_trader.api.llm_names`).
"""

import tomllib
from dataclasses import dataclass
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


def load_llm_settings(path: Path = LLM_SETTINGS_PATH) -> LlmSettings:
    with open(path, "rb") as file:
        return LlmSettings(**tomllib.load(file))
