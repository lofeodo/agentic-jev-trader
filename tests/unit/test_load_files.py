"""Reading a Snowflake save's files for `storage load`: carrying on part-way through a table,
and vectors sent as shorter text that gives back the same 4-byte numbers."""

import json

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

from jev_trader.storage.load import SavedTable, _short_vector, saved_rows


def made_up_table(folder, files=3, rows_per_file=5):
    """A saved table of `files` Parquet files, its rows numbered 0, 1, 2, ... in order."""
    table = SavedTable(
        "FEATURES",
        "SNAPSHOTS",
        files * rows_per_file,
        tuple(f"part-{n}.parquet" for n in range(files)),
        (("STEP", "NUMBER(38,0)"), ("EMBEDDING", "VECTOR(FLOAT, 3)")),
    )
    table.folder(folder).mkdir(parents=True)
    for n, file in enumerate(table.files):
        steps = range(n * rows_per_file, (n + 1) * rows_per_file)
        pq.write_table(
            pa.table(
                {
                    "STEP": [float(s) for s in steps],
                    "EMBEDDING": [json.dumps([s / 3, 0.1, -2.5e-07]) for s in steps],
                }
            ),
            table.folder(folder) / file,
        )
    return table


def steps(batches):
    return [int(row[0]) for batch in batches for row in batch]


def test_rows_carry_on_from_where_a_load_stopped(tmp_path):
    table = made_up_table(tmp_path)

    assert steps(saved_rows(tmp_path, table)) == list(range(15))
    assert steps(saved_rows(tmp_path, table, skip=7)) == list(range(7, 15))
    assert steps(saved_rows(tmp_path, table, skip=10)) == list(range(10, 15))
    assert steps(saved_rows(tmp_path, table, skip=15)) == []


def test_a_short_vector_gives_back_the_same_four_byte_numbers(tmp_path):
    saved = [
        float(np.float32(x)) for x in (1 / 3, 0.1, -2.5e-07, 6.966275162994862e-03)
    ]
    text = json.dumps(saved)

    short = _short_vector(text)

    assert len(short) < len(text)
    assert np.array_equal(
        np.asarray(json.loads(short), dtype=np.float32),
        np.asarray(saved, dtype=np.float32),
    )


def test_vectors_are_sent_short_and_other_columns_as_saved(tmp_path):
    table = made_up_table(tmp_path, files=1, rows_per_file=2)

    [batch] = saved_rows(tmp_path, table, short_vectors=True)

    assert batch[1] == (1, _short_vector(json.dumps([1 / 3, 0.1, -2.5e-07])))
