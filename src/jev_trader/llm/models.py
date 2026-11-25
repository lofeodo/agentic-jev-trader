"""Which LLMs a sim may use, and the default (spec appendix 8, section 4).

Both are settings in `config/llm.toml`. A measurement names both models (or one, if the LLM
benchmark left one out); a free sim names one, the default unless the developer picks the other.

The names are in lower case (the spec writes `GLM-5.3-Flash`), as a sim's settings store them
(`openai:glm-5.3-flash`) and `jev_trader.api.llm_names` reads them. A name given in other
capitals means the same model: a sim's model is put in lower case when the sim is planned
(`jev_trader.sim.runner.plan_sim`).
"""

import tomllib
from dataclasses import dataclass
from pathlib import Path

from jev_trader.broker.config import CONFIG_DIR


@dataclass(frozen=True)
class ModelSettings:
    providers: dict[str, str]  # each model a sim may name, with who serves it
    default_model: str

    @property
    def models(self) -> tuple[str, ...]:
        """The models a sim may name, such as "claude-haiku-5-5"."""
        return tuple(self.providers)

    def setting(self, model: str) -> str:
        """The one setting a sim's settings store for `model`: "anthropic:claude-haiku-5-5"."""
        return f"{self.providers[model]}:{model}"


def load_model_settings(path: Path = CONFIG_DIR / "llm.toml") -> ModelSettings:
    with open(path, "rb") as file:
        settings = tomllib.load(file)
    return ModelSettings(
        providers=dict(settings["models"]), default_model=settings["default_model"]
    )
