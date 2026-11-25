"""Where the two LLM clients sit: Claude Haiku through Anthropic and GLM Flash through Z.ai,
both behind LangChain's model interface and picked by the one model setting (spec appendix 5,
section 9; appendix 10, section 2).

Not built yet: no sim calls an LLM until the agent with memory is built, and the checker
refuses a sim with memory until then.
"""

from langchain_core.language_models import BaseChatModel

from jev_trader.llm.settings import LlmSettings


def chat_model(settings: LlmSettings) -> BaseChatModel:
    """The chat model `settings` names, ready for the selection's tool loop."""
    raise NotImplementedError(f"the LLM client for {settings.model} is not built yet")
