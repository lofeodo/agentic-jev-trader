"""Which LLM a sim with memory uses, and the name the developer reads for it.

A sim's settings hold one setting naming provider and model (spec appendix 5, section 2;
appendix 6, section 3.4): `"anthropic:claude-haiku-5-5"` or `"openai:glm-5.3-flash"`. The spec
does not name its place in the settings document; it is read from `SETTINGS.llm.model`, where
the agent with memory must write it.
"""

MODEL_LABELS = {"claude-haiku-5-5": "Claude Haiku", "glm-5.3-flash": "GLM Flash"}


def llm_model_of(settings: dict | None) -> str | None:
    """The model a sim's settings name, without the provider (`claude-haiku-5-5`); None if
    unset."""
    named = ((settings or {}).get("llm") or {}).get("model")
    return named.split(":", 1)[-1].lower() if named else None


def llm_model(sim: dict) -> str | None:
    """A sim row's LLM: `LLM_MODEL` in the list of every sim, from the settings on one sim's
    whole row."""
    if "LLM_MODEL" in sim:
        return sim["LLM_MODEL"]
    return llm_model_of(sim.get("SETTINGS"))


def model_label(model: str | None) -> str:
    """The name the developer reads: "Claude Haiku" for `claude-haiku-5-5`."""
    if model is None:
        return "Unknown model"
    return MODEL_LABELS.get(model, model)


VARIANT_LABELS = {"memory_on": "With memory", "memory_off": "Without memory"}


def variant_label(sim: dict) -> str:
    """ "With memory / GLM Flash", "Without memory": a sim beside others of its repeat; a sim
    with memory is told apart by its LLM, when its settings name one."""
    label = VARIANT_LABELS.get(sim["VARIANT"], sim["VARIANT"])
    if sim["VARIANT"] == "memory_on" and llm_model(sim):
        label = f"{label} / {model_label(llm_model(sim))}"
    return label
