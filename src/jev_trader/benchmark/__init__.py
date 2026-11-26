"""The LLM benchmark: a one-off command-line check that hands both LLMs the same saved moments
and reports which one keeps messing up (spec appendix 9, section 8; appendix 8, section 12).

Nothing is traded and Jev is not asked: an attempt ends when the model names its episodes, so it
only spends LLM money. The parts, in the order the command uses them:

- `moments`: the saved moments the build-up sim left (`SavedMoment`, `saved_moments`);
- `runner`: one model's attempt at one moment (`ModelRunner`, `Attempt`), and the run over every
  model, pass and moment (`run_benchmark`);
- `spending`: the running dollar total checked before each attempt (`SpendMeter`);
- `records`: where each attempt is kept: its calls in `SIM.CALLS` with the purpose "benchmark"
  and no sim, its detail in a file (`AttemptLog`);
- `report`: the plain-words page made from every attempt (`report`);
- `__main__`: the command, `python -m jev_trader.benchmark`.
"""


class NotBuilt(NotImplementedError):
    """A part of the benchmark that is only a frame so far: its ticket builds it."""

    def __init__(self, what: str):
        super().__init__(f"not built yet: {what}")
