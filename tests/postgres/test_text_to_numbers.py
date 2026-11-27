"""The text-to-numbers model on this computer gives the numbers Snowflake gave (spec appendix 11,
section 2).

Snowflake turned each situation text into 768 numbers with `snowflake-arctic-embed-m-v1.5`; the
same model now runs here. Before the saved numbers are loaded into Postgres as they are, a
handful of saved episodes are turned into numbers again here and compared with Snowflake's.

`snowflake_numbers.json`, beside this file, holds those episodes, taken from a `storage save`
of Snowflake (no Snowflake call): a list of `{"situation_text": ..., "embedding": [768
numbers]}`. The model downloads once (about 440 MB, plus 1 to 2 GB of libraries), so this runs
only with `--run-model`.

**The tolerance**: each episode's two lists of numbers point the same way to within a cosine
similarity of 0.999 (1 is identical; the search compares texts by this same measure). Below
that, stop and ask the developer before loading the saved numbers.
"""

import json
import math
from pathlib import Path

import pytest

from jev_trader.dataset.snapshots import EMBEDDING_SIZE

pytestmark = pytest.mark.model

SAVED = Path(__file__).with_name("snowflake_numbers.json")
LEAST_SIMILARITY = 0.999
FEWEST_EPISODES = 5


def cosine(a, b) -> float:
    norms = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return sum(x * y for x, y in zip(a, b)) / norms


def test_the_local_model_gives_snowflakes_numbers():
    from jev_trader.dataset import text_to_numbers

    saved = json.loads(SAVED.read_text(encoding="utf-8"))
    assert len(saved) >= FEWEST_EPISODES

    local = text_to_numbers.embed([e["situation_text"] for e in saved])

    assert [len(n) for n in local] == [EMBEDDING_SIZE] * len(saved)
    similarities = [cosine(n, e["embedding"]) for n, e in zip(local, saved)]
    assert min(similarities) >= LEAST_SIMILARITY, (
        "The local model's numbers differ from Snowflake's: stop and ask the developer. "
        f"Similarities: {[round(s, 5) for s in similarities]}"
    )
