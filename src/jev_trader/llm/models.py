"""Which LLMs a sim may use, and the default (spec appendix 8, section 4).

Both are settings in `config/llm.toml`. A measurement names both models (or one, if the LLM
benchmark left one out); a free sim names one, the default unless the developer picks the other.

The names are in lower case (the spec writes `GLM-5.3-Flash`), as a sim's settings store them
(`openai:glm-5.3-flash`) and `jev_trader.api.llm_names` reads them.
"""

import tomllib
from dataclasses import dataclass
from pathlib import Path

from jev_trader.broker.config import CONFIG_DIR


@dataclass(frozen=True)
class ModelSettings:
    models: tuple[str, ...]  # the models a sim may name, such as "claude-haiku-5-5"
    default_model: str


def load_model_settings(path: Path = CONFIG_DIR / "llm.toml") -> ModelSettings:
    with open(path, "rb") as file:
        settings = tomllib.load(file)
    return ModelSettings(
        models=tuple(settings["models"]), default_model=settings["default_model"]
    )
