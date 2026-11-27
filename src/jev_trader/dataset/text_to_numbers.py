"""The text-to-numbers model on this computer (spec appendix 11, section 2).

Snowflake turned each situation text into 768 numbers with `AI_EMBED` and the open model
`snowflake-arctic-embed-m-v1.5`. The same model runs here, through `sentence-transformers` as
its model card shows: the texts are stored episodes, so no query prefix, and each list of
numbers is scaled to length 1, as Snowflake's are.

The model downloads once from Hugging Face (about 440 MB) into its usual cache, at the revision
pinned below, and is loaded once per process, on the NVIDIA card when there is one. The
libraries load only when `embed` is first called, so importing this module costs nothing.

`tests/postgres/test_text_to_numbers.py` checks the numbers against Snowflake's on saved
episodes (`--run-model`). Callers use `text_to_numbers.embed(...)` through the module, so tests
can swap in made-up numbers.
"""

from functools import cache

from jev_trader.dataset.snapshots import EMBEDDING_MODEL, EMBEDDING_SIZE

MODEL_ID = f"Snowflake/{EMBEDDING_MODEL}"
# The model's files at a fixed point, so a later upload cannot change the numbers.
MODEL_REVISION = "e58a8f756156a1293d763f17e3aae643474e9b8a"
BATCH_SIZE = 64


def embed(texts: list[str]) -> list[list[float]]:
    """Each text's 768 numbers, in the order the texts came."""
    if not texts:
        return []
    vectors = _model().encode(
        list(texts),
        batch_size=BATCH_SIZE,
        normalize_embeddings=True,
        convert_to_numpy=True,
        show_progress_bar=False,
    )
    numbers = vectors.tolist()
    if any(len(n) != EMBEDDING_SIZE for n in numbers):
        raise RuntimeError(
            f"{MODEL_ID} gave numbers of a size other than {EMBEDDING_SIZE}"
        )
    return numbers


@cache
def _model():
    import torch
    from sentence_transformers import SentenceTransformer

    device = "cuda" if torch.cuda.is_available() else "cpu"
    return SentenceTransformer(MODEL_ID, revision=MODEL_REVISION, device=device)
