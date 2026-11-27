"""Today's tables, as Snowflake's numbered files V1 to V11 left them (spec appendix 11, section 1).

The first Alembic file: it makes every table from nothing, in its final shape, so the column
notes of V2 to V11 (removed with Snowflake; in git history) are gathered here, table by table. It runs as the setup
login, which owns every table; the other four logins get what they need through the grants at
the end of `upgrade`, the same split as Snowflake's was. Those
four roles must exist first: the local Postgres's `init.sql` makes them, Terraform does on RDS.

How Snowflake's types are written here:

- `NUMBER` (whole numbers: IDs, steps, counts) is `bigint`; `FLOAT` is `double precision`.
- `VARCHAR` is `text COLLATE "C"`: compared and sorted byte by byte, as Snowflake does. Postgres's
  usual sorting skips `-`, which would put episode `1-100-ASSET_01` before `1-10-ASSET_04`.
- `VARIANT` (flexible JSON) is `jsonb`.
- `ARRAY` (a list) is `jsonb` too, as Snowflake keeps it: a list of measurements mixes whole
  numbers, fractions and empty places, which psycopg will not send as a typed Postgres list.
- `VECTOR(FLOAT, n)` is pgvector's `vector(n)`.
- `TIMESTAMP_NTZ` (a time with no time zone) is `timestamp`.
- The two sequences stay sequences, each belonging to its ID column (emptying the table with
  `TRUNCATE ... RESTART IDENTITY` starts it again at 1).
- Snowflake's `TRANSIENT` table (no recovery copy kept) is `UNLOGGED` (no crash log kept).
- Primary keys are enforced now; Snowflake only recorded them.

Snowflake's names were unquoted upper case, so here they are unquoted and stored lower case:
`SELECT ... FROM MEMORY.DECISIONS` reads the same table.
"""

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

SCHEMAS = ("ref", "keys", "raw", "features", "sim", "memory")

TEXT = 'text COLLATE "C"'

# Who reads and writes which schema (as Snowflake's logins did). Reading is
# SELECT on its tables; writing adds INSERT, UPDATE, DELETE and TRUNCATE. `usage_only` opens the
# schema and no table in it: the table-by-table exceptions are in TABLE_GRANTS.
LOGINS = {
    "builder": {
        "read": ("ref", "keys", "raw", "features"),
        "write": ("ref", "keys", "raw", "features"),
        "usage_only": (),
    },
    "sim": {
        "read": ("ref", "raw", "features", "sim", "memory"),
        "write": ("sim", "memory"),
        "usage_only": (),
    },
    # The memory server only reads (ADR 0006).
    "memory": {
        "read": ("ref", "features", "memory"),
        "write": (),
        "usage_only": ("sim",),
    },
    "api": {
        "read": ("ref", "keys", "raw", "features", "sim", "memory"),
        "write": (),
        "usage_only": (),
    },
}

WRITE = "INSERT, UPDATE, DELETE, TRUNCATE"

TABLE_GRANTS = [
    # The API adds a build or a sim it is asked for, marks a stopped one, records a new cap.
    "GRANT INSERT, UPDATE ON ref.datasets TO trading_agent_api",
    "GRANT INSERT, UPDATE ON sim.sims TO trading_agent_api",
    # The memory server reads a sim's settings.
    "GRANT SELECT ON sim.sims TO trading_agent_memory",
    # A dataset's ID is taken by the builder, or by the API for a build it is asked for; a
    # sim's by the sim job when started from the command line, or by the API.
    "GRANT USAGE ON SEQUENCE ref.dataset_ids TO trading_agent_builder, trading_agent_api",
    "GRANT USAGE ON SEQUENCE sim.sim_ids TO trading_agent_sim, trading_agent_api",
]

TABLES = f"""
-- The dataset tables (spec appendix 6, sections 3.1 to 3.3). A dataset is a fixed pile of market
-- history every sim replays. Real names, prices and dates live only in KEYS.ASSET_KEY; every
-- other table uses masked IDs (ASSET_01) and step numbers.

-- One row per dataset. STATUS is 'being built', 'published' or 'failed'. A failed build keeps
-- this row, with its reason, and loses every other row it wrote. Shares are fractions: 0.005
-- is 0.5%. CHECK_RESULT holds the check's measured value per asset and its verdict.
-- MEASUREMENT_SETTINGS: the settings behind the measurements and the situation text (bars and
-- days each looks back over, the pattern window, the volume word's cut-offs).
CREATE TABLE ref.datasets (
    id bigint NOT NULL PRIMARY KEY,
    name {TEXT} NOT NULL,
    version bigint NOT NULL,
    status {TEXT} NOT NULL,
    published_without_check boolean NOT NULL DEFAULT false,
    failure_reason {TEXT},
    first_step bigint,
    last_step bigint,
    data_providers jsonb,
    talib_version {TEXT},
    embedding_model {TEXT},
    measurements jsonb,
    partial_volume_share_of_usual double precision,
    partial_volume_sessions bigint,
    limit_other_missing double precision,
    limit_partial_volume_days double precision,
    check_result jsonb,
    price_decimals bigint,
    build_stage {TEXT},
    build_progress double precision,
    started_at timestamp,
    built_at timestamp,
    published_at timestamp,
    measurement_settings jsonb
);
CREATE SEQUENCE ref.dataset_ids OWNED BY ref.datasets.id;

-- KIND is 'warm-up' or 'test'; the test period is one row per stretch ('falling market').
CREATE TABLE ref.dataset_periods (
    dataset bigint NOT NULL,
    kind {TEXT} NOT NULL,
    name {TEXT} NOT NULL,
    first_step bigint NOT NULL,
    last_step bigint NOT NULL
);

-- ASSET_CLASS is 'stock' or 'crypto'.
CREATE TABLE ref.assets (
    dataset bigint NOT NULL,
    masked_id {TEXT} NOT NULL,
    asset_class {TEXT} NOT NULL,
    PRIMARY KEY (dataset, masked_id)
);

-- The tradable form of an asset: one 'spot' instrument per asset in version 1.
CREATE TABLE ref.instruments (
    dataset bigint NOT NULL,
    instrument_id {TEXT} NOT NULL,
    asset {TEXT} NOT NULL,
    type {TEXT} NOT NULL,
    PRIMARY KEY (dataset, instrument_id)
);

-- The quality report, part 1. STEP is the step at which the missing bar would have ended.
-- REASON is 'not supplied', 'zero volume' or 'partial-volume day'.
CREATE TABLE ref.missing_bars (
    dataset bigint NOT NULL,
    asset {TEXT} NOT NULL,
    step bigint NOT NULL,
    reason {TEXT} NOT NULL
);

-- The quality report, part 2. DAY is the day number (1 is the dataset's first day). TEST is
-- 'a zero-volume bar' or 'volume under its share of usual'. SHARE_OF_USUAL: 0.08 is 8% of the
-- stock's usual volume per bar.
CREATE TABLE ref.partial_volume_days (
    dataset bigint NOT NULL,
    asset {TEXT} NOT NULL,
    day bigint NOT NULL,
    test {TEXT} NOT NULL,
    share_of_usual double precision
);

-- The warm-up period's average and spread of each measurement, frozen with the dataset and
-- shared by its assets. POSITION is the measurement's place in the feature vector (1 to 58).
-- AVERAGE and SPREAD are empty for a measurement with no spread in the warm-up: it scores 0.
CREATE TABLE ref.warmup_stats (
    dataset bigint NOT NULL,
    position bigint NOT NULL,
    measurement {TEXT} NOT NULL,
    average double precision,
    spread double precision,
    PRIMARY KEY (dataset, position)
);

-- One row per candle pattern (a TA-Lib detector and a lean), for one TA-Lib version; shared by
-- every dataset built with it. PATTERN is TA-Lib's detector (CDLENGULFING), LEAN 'bullish',
-- 'bearish' or 'neutral', NAME what every reader sees ('bullish engulfing'), SHAPE the shape
-- in plain words from TA-Lib's source.
CREATE TABLE ref.playbook (
    talib_version {TEXT} NOT NULL,
    pattern {TEXT} NOT NULL,
    lean {TEXT} NOT NULL,
    name {TEXT} NOT NULL,
    shape {TEXT} NOT NULL,
    PRIMARY KEY (talib_version, pattern, lean)
);

-- The asset key: the only table with real names, prices and dates. A real price is the stored
-- price divided by PRICE_SCALE; real volume is stored volume divided by VOLUME_SCALE. FIRST_DAY
-- is the real (UTC) date of step 1.
CREATE TABLE keys.asset_key (
    dataset bigint NOT NULL,
    masked_id {TEXT} NOT NULL,
    ticker {TEXT} NOT NULL,
    provider_symbol {TEXT} NOT NULL,
    name {TEXT} NOT NULL,
    price_scale double precision NOT NULL,
    volume_scale double precision NOT NULL,
    first_day date NOT NULL,
    PRIMARY KEY (dataset, masked_id)
);

-- Rescaled bars. BAR_SIZE is '15m', '1h' or '1d'. STEP is the step at which the bar ends.
-- BAR_NUMBER counts from 1 in the stock's session or the crypto's UTC day; BARS_LEFT is the
-- bars left in the session (0 on the last one), and empty for crypto, which has no session.
CREATE TABLE raw.bars (
    dataset bigint NOT NULL,
    asset {TEXT} NOT NULL,
    bar_size {TEXT} NOT NULL,
    step bigint NOT NULL,
    day bigint NOT NULL,
    bar_number bigint NOT NULL,
    bars_left bigint,
    open double precision NOT NULL,
    high double precision NOT NULL,
    low double precision NOT NULL,
    close double precision NOT NULL,
    volume double precision NOT NULL,
    PRIMARY KEY (dataset, asset, bar_size, step)
);

-- A candle pattern recognised on a bar. BAR_SIZE is '15m', '1h' or '1d'; STEP the step at
-- which that bar ends (as in RAW.BARS); PATTERN the playbook's NAME.
CREATE TABLE features.patterns (
    dataset bigint NOT NULL,
    asset {TEXT} NOT NULL,
    bar_size {TEXT} NOT NULL,
    step bigint NOT NULL,
    pattern {TEXT} NOT NULL
);

-- A snapshot: everything code measures about one asset at the step a 15-minute bar ends. One
-- row per asset and step with a 15-minute bar. MEASUREMENTS holds the 58 numbers in the order
-- of REF.DATASETS.MEASUREMENTS, empty where not available; FEATURE_VECTOR their 58 standard
-- scores; SITUATION_TEXT the paragraph code writes; EMBEDDING the text's 768 numbers from the
-- text-to-numbers model, so memory can find similar texts.
CREATE TABLE features.snapshots (
    dataset bigint NOT NULL,
    asset {TEXT} NOT NULL,
    step bigint NOT NULL,
    measurements jsonb NOT NULL,
    feature_vector vector(58) NOT NULL,
    situation_text {TEXT} NOT NULL,
    embedding vector(768) NOT NULL,
    PRIMARY KEY (dataset, asset, step)
);

-- Snapshots on their way into FEATURES.SNAPSHOTS, before their texts are turned into numbers.
-- Emptied once a build ends or fails, but a build killed outright leaves its rows here:
-- whatever stops a build by hand must delete them. MEASUREMENTS and FEATURE_VECTOR are JSON
-- lists as text.
CREATE UNLOGGED TABLE features.snapshots_loading (
    dataset bigint NOT NULL,
    asset {TEXT} NOT NULL,
    step bigint NOT NULL,
    measurements {TEXT} NOT NULL,
    feature_vector {TEXT} NOT NULL,
    situation_text {TEXT} NOT NULL
);

-- The SIM group: a sim's bookkeeping (spec appendix 6, section 3.4), written by the sim's job.
-- A sim is one replay of the agent, or of the holding comparison, over a stretch of a dataset's
-- steps with pretend money. Everything a step stores goes in one transaction with
-- SIMS.LAST_COMPLETED_STEP moving from N-1 to N, and the write goes through only if it still
-- reads N-1 and the sim is running. Every record carries an ID built from what it describes
-- (sim, step, asset).

-- One row per sim.
-- KIND: 'practice', 'tuning', 'build-up', 'measurement' or 'free'.
-- VARIANT: 'buy_hold', 'memory_off' or 'memory_on'.
-- MARKET: the test period's name for a measurement sim ('falling market').
-- SETTINGS: every setting the sim runs with, as one document; a resumed sim reads them here.
-- STATUS: 'created', 'running', 'stopped', 'finished' or 'failed'.
-- STOP_REASON: 'finished', 'spending cap', 'Jev failed', 'LLM failed', 'account at zero' or
--   'stopped by hand'. FAILURE_REASON: what went wrong, for a failed sim.
-- LAST_COMPLETED_STEP: the last step stored; empty until the first step is stored.
-- ACCOUNT_STATE: the account as it stood after that step (cash, open positions, orders still
--   waiting, last prices, the day's starting value, and 'agent': each open position's
--   situation at entry and its journal), so a restarted sim carries on from it (ADR 0013).
-- RUNNING_ON: where the job runs ('pid 1234' on the developer's machine, or a cluster Job).
-- LAST_WRITTEN_AT: when LAST_COMPLETED_STEP last moved; a running sim quiet for 7 minutes is
--   shown as not responding.
CREATE TABLE sim.sims (
    id bigint NOT NULL PRIMARY KEY,
    dataset bigint NOT NULL,
    kind {TEXT} NOT NULL,
    variant {TEXT} NOT NULL,
    repeat_number bigint,
    market {TEXT},
    first_step bigint NOT NULL,
    last_step bigint NOT NULL,
    starting_value double precision NOT NULL,
    random_seed bigint NOT NULL DEFAULT 0,
    settings jsonb NOT NULL,
    code_version {TEXT},
    memory_from_sim bigint,
    estimated_cost double precision,
    spending_cap double precision,
    stopped_by_cap boolean NOT NULL DEFAULT false,
    status {TEXT} NOT NULL,
    stop_reason {TEXT},
    failure_reason {TEXT},
    last_completed_step bigint,
    account_state jsonb,
    running_on {TEXT},
    created_at timestamp,
    started_at timestamp,
    last_written_at timestamp,
    ended_at timestamp
);
CREATE SEQUENCE sim.sim_ids OWNED BY sim.sims.id;

-- One row per buy or sell. ID: sim, step decided, asset and the broker's number for the order.
-- An order's row is rewritten (same ID) as it goes from waiting to carried out or cancelled.
-- POSITION: the broker's number for the position (empty for an entry still waiting).
-- INSTRUMENT: REF.INSTRUMENTS.INSTRUMENT_ID ('ASSET_01_SPOT'). DECISION: the decision behind
--   it (MEMORY.DECISIONS), empty for the holding sim and for code's own closes.
-- KIND: 'entry', 'add', 'reduce' or 'close'. SIDE: 'buy' or 'sell'.
-- REASON: 'jev', 'stop_price', 'forced_close', 'sim_ended', or 'buy_hold' for the holding
--   sim's purchases. STATUS: 'waiting', 'carried out' or 'cancelled'.
-- Dollars: VALUE is units times PRICE (slippage inside the price); COMMISSION_OR_TRADING_FEE
--   comes on top. AMOUNT_CHOSEN is the size Jev chose, AMOUNT_AFTER_TRIMMING the size after
--   the risk limits, LIMITED_BY the limit that trimmed it ('trade_risk', 'position', ...).
CREATE TABLE sim.orders (
    id {TEXT} NOT NULL PRIMARY KEY,
    sim bigint NOT NULL,
    position bigint,
    instrument {TEXT} NOT NULL,
    decision {TEXT},
    kind {TEXT} NOT NULL,
    reason {TEXT} NOT NULL,
    side {TEXT},
    step_decided bigint NOT NULL,
    step_carried_out bigint,
    status {TEXT} NOT NULL,
    units double precision,
    price_before_slippage double precision,
    price double precision,
    value double precision,
    slippage_cost double precision,
    commission_or_trading_fee double precision,
    amount_chosen double precision,
    amount_after_trimming double precision,
    limited_by {TEXT}
);

-- The account at each step the sim looked at. ID: sim and step. LOAN is what the account owes
-- for positions bought beyond its own cash; EXPOSURE all positions added together, a short
-- counted like a long; START_OF_DAY_VALUE the account value at the last midnight UTC.
CREATE TABLE sim.account_steps (
    id {TEXT} NOT NULL PRIMARY KEY,
    sim bigint NOT NULL,
    step bigint NOT NULL,
    cash double precision NOT NULL,
    loan double precision NOT NULL,
    exposure double precision NOT NULL,
    account_value double precision NOT NULL,
    start_of_day_value double precision NOT NULL,
    daily_loss_reached boolean NOT NULL
);

-- Nightly charges at midnight UTC. STEP is the step that ends at that midnight (96 for the
-- first). KIND: 'borrow_fee' (a short's, POSITION set) or 'loan_interest' (POSITION empty).
-- CHARGED_ON: the short's value or the loan, in dollars; YEARLY_RATE: 0.05 is 5% a year.
CREATE TABLE sim.charges (
    id {TEXT} NOT NULL PRIMARY KEY,
    sim bigint NOT NULL,
    step bigint NOT NULL,
    kind {TEXT} NOT NULL,
    position bigint,
    charged_on double precision NOT NULL,
    yearly_rate double precision NOT NULL,
    amount double precision NOT NULL
);

-- Notable moments, for the live sim screen. KIND: 'restarted', 'forced close', 'daily loss
-- limit tripped', 'spending cap reached', 'stopped', 'an LLM limit hit', 'an unknown episode ID
-- dropped', 'a failed reply'.
CREATE TABLE sim.sim_events (
    id {TEXT} NOT NULL PRIMARY KEY,
    sim bigint NOT NULL,
    step bigint NOT NULL,
    kind {TEXT} NOT NULL,
    details jsonb
);

-- Paid Jev and LLM calls. SIM is empty for a call made outside a sim (the LLM benchmark, saving
-- answers for tests). The holding sim makes none. PURPOSE: 'screen', 'pick', 'size',
-- 'position_screen', 'action', 'reduce', 'add', 'select', 'benchmark'. SERVICE: Jev's, or
-- 'anthropic' or 'zai' for the LLM.
CREATE TABLE sim.calls (
    id {TEXT} NOT NULL PRIMARY KEY,
    sim bigint,
    purpose {TEXT} NOT NULL,
    step bigint,
    asset {TEXT},
    decision {TEXT},
    service {TEXT} NOT NULL,
    model {TEXT},
    tokens_in bigint,
    cached_tokens bigint,
    tokens_out bigint,
    thinking_tokens bigint,
    cost_usd double precision,
    latency_seconds double precision,
    retries bigint,
    error {TEXT},
    called_at timestamp
);

-- The opening of Jev's background, the part that is the same in every request of a sim, stored
-- once per reading version (a fingerprint worked out from the wording).
CREATE TABLE sim.jev_readings (
    reading_version {TEXT} NOT NULL PRIMARY KEY,
    opening {TEXT} NOT NULL,
    created_at timestamp
);

-- Every Jev request and answer, word for word. ID: sim, step, asset and purpose.
-- The whole background is the reading version's OPENING, a blank line, and
-- BACKGROUND_AFTER_OPENING. QUESTIONS is as sent; ANSWER is Jev's reply exactly as received.
-- PURPOSE: as in SIM.CALLS. JEV_VERSION: the version that answered ('jev-1.14.0').
CREATE TABLE sim.jev_requests (
    id {TEXT} NOT NULL PRIMARY KEY,
    sim bigint NOT NULL,
    step bigint NOT NULL,
    asset {TEXT} NOT NULL,
    decision {TEXT} NOT NULL,
    purpose {TEXT} NOT NULL,
    reading_version {TEXT} NOT NULL,
    background_after_opening {TEXT} NOT NULL,
    questions jsonb NOT NULL,
    answer {TEXT} NOT NULL,
    jev_version {TEXT} NOT NULL
);

-- What every LLM exchange of one prompt version opens with, stored once. SYSTEM_PROMPT: JSON
-- text with one key per job, 'full_evaluation' and 'position_review', each that job's standing
-- instructions word for word (a prompt version from before the position review's selection
-- has 'full_evaluation' alone). TOOLS: an object with the same keys, each that job's tools as
-- its first call offers them (name, description, inputs). The lookup tools' lists of candle
-- patterns and the numbers in the instructions are not part of the prompt version, so the row
-- keeps the first sim's.
CREATE TABLE sim.llm_prompts (
    prompt_version {TEXT} NOT NULL PRIMARY KEY,
    system_prompt {TEXT} NOT NULL,
    tools jsonb NOT NULL,
    created_at timestamp
);

-- The LLM's exchange in one full evaluation or position review in which it was asked, word for
-- word. ID: the decision's ID.
-- MESSAGES: every message after the standing instructions of the decision's job, as sent and
--   received (LangChain's message records).
-- FAILED_REPLIES: each reply code could not use, word for word.
-- SLIPS: each smaller slip carried on from ('repeated episode IDs removed', ...).
CREATE TABLE sim.llm_exchanges (
    id {TEXT} NOT NULL PRIMARY KEY,
    sim bigint NOT NULL,
    step bigint NOT NULL,
    asset {TEXT} NOT NULL,
    decision {TEXT} NOT NULL,
    prompt_version {TEXT} NOT NULL,
    messages jsonb NOT NULL,
    failed_replies jsonb NOT NULL,
    slips jsonb NOT NULL
);

-- The memory (spec appendix 4, section 13; appendix 5; appendix 6, sections 3.5, 4 and 8).

-- One row per asset looked at, at one step. ID: sim, step and asset; it stays the same in a
-- copy of a memory. SIM is the memory the row belongs to, FIRST_WRITTEN_BY the sim that wrote it.
-- KIND: 'screen', 'full_evaluation', 'position_screen' or 'position_review'.
-- TIER: 0 is code alone (nothing was asked), 1 a screen, 2 a full evaluation or a review.
-- SCREEN_ANSWER: Jev's probability of yes, from 0 to 1 (the position screen's on a review);
--   empty at tier 0 and on an end-of-session review.
-- SKIPPED_BECAUSE: the limit that meant no trade could open ('daily_loss', 'session_end',
--   'no_typical_move', ...).
-- ACTION: what was done: 'nothing', 'entry', 'close', 'reduce' or 'add'.
-- A full evaluation's columns:
-- CANDIDATE_TRADES: the six trades code listed, each with its name ('long_tight_stop'),
--   direction, stop price and the stop price's distance as a share of the price.
-- ANSWERS: Jev's probabilities question by question, every copy ('pick_1' to 'pick_5',
--   'size_small_first', 'size_large_first', 'rating'; on a review 'action_1' to 'action_5',
--   'thesis_intact', and the reduce or add sizes).
-- PICK: the option code read from the pick ('long_tight_stop', ..., 'no_trade'), or on a review
--   the action decided ('hold', 'close', 'reduce', 'add').
-- RATING: how strong Jev rated the case, 0 to 4. Recorded only: it never moves money.
-- SIZE_CHOSEN: Jev's size in dollars; SIZE_AFTER_TRIMMING what the risk limits left of it
--   (0 if nothing); LIMITED_BY the limit that trimmed it.
-- A position's columns, empty on the rows of an asset with no position:
-- POSITION: the broker's ID for the position looked at, as in SIM.ORDERS.POSITION.
-- STANDING: how the position stood at a review (direction, dollars put in, bars open, profit
--   or loss so far, the stop price's distance, its best and worst point so far).
-- END_OF_SESSION: whether the review was an end-of-session review.
-- THESIS_INTACT: Jev's probability that the reason for opening still holds. Recorded only.
-- REDUCE_SHARE: the share of the position closed after a reduce, from 0 to 1.
-- OUTCOMES_KNOWN_FROM: the step from which all of an episode's outcomes are known; empty until
--   then, and on every row that is not an episode.
-- The LLM's selection, on a full evaluation or a review in which the LLM was asked:
-- LLM_MODEL: the model the provider says answered. PROMPT_VERSION: the fingerprint of the
--   LLM's wording. SELECTED: the episodes selected, as stored decision IDs, most useful first;
--   [] for none. LLM_NOTE: its one-line note, cut at 200 characters; Jev never reads it.
--   LIMIT_HIT: 'lookups' or 'time', if it reached one. EPISODES_SHOWN: every episode shown,
--   with its label, ranks, and whether it was opened in full. LOOKUPS: each lookup in order.
-- MEMORIES_RELEVANT: Jev's probability that the past episodes shown fit the current situation,
--   asked when at least one episode is shown. Recorded only.
CREATE TABLE memory.decisions (
    id {TEXT} NOT NULL,
    sim bigint NOT NULL,
    first_written_by bigint NOT NULL,
    dataset bigint NOT NULL,
    asset {TEXT} NOT NULL,
    step bigint NOT NULL,
    kind {TEXT} NOT NULL,
    tier bigint NOT NULL,
    screen_answer double precision,
    skipped_because {TEXT},
    jev_version {TEXT},
    action {TEXT} NOT NULL,
    candidate_trades jsonb,
    answers jsonb,
    pick {TEXT},
    rating double precision,
    size_chosen double precision,
    size_after_trimming double precision,
    limited_by {TEXT},
    position bigint,
    standing jsonb,
    end_of_session boolean,
    thesis_intact double precision,
    reduce_share double precision,
    outcomes_known_from bigint,
    llm_model {TEXT},
    prompt_version {TEXT},
    selected jsonb,
    llm_note {TEXT},
    limit_hit {TEXT},
    episodes_shown jsonb,
    lookups jsonb,
    memories_relevant double precision,
    PRIMARY KEY (sim, id)
);

-- One row per fact about how a decision turned out (appendix 5, section 1; ADR 0001), recorded
-- by code as bars pass and trades close. ID: the decision's ID and the kind; it stays the same
-- in a copy of a memory. SIM and FIRST_WRITTEN_BY as in MEMORY.DECISIONS.
-- KIND and VALUE:
--   'price_after_1_bar', 'price_after_4_bars', 'price_at_end_of_day': the asset's close then
--     and its change from the decision's close, as a share ({{"price": 100.2, "change": 0.002}});
--   'order_carried_out': a traded full evaluation's entry ({{"carried_out": true, "price": ...,
--     "value": ...}}, or {{"carried_out": false}} when it was cancelled);
--   'position_closed': how the trade ended ({{"closing_reason", "step_closed", "bars_after",
--     "profit", "trading_costs"}}, and for a position review "closed_at_this_review").
-- KNOWN_FROM: the step from which memory may show the fact.
CREATE TABLE memory.outcomes (
    id {TEXT} NOT NULL,
    sim bigint NOT NULL,
    first_written_by bigint NOT NULL,
    decision {TEXT} NOT NULL,
    kind {TEXT} NOT NULL,
    value jsonb NOT NULL,
    known_from bigint NOT NULL,
    PRIMARY KEY (sim, id)
);
"""


def _access_statements() -> list[str]:
    """Each login's way into its schemas, and the tables made in them from now on (the setup
    login's default privileges, as Snowflake's future grants)."""
    statements = []
    for login, access in LOGINS.items():
        role = f"trading_agent_{login}"
        for schema in SCHEMAS:
            reads = schema in access["read"]
            if reads or schema in access["usage_only"]:
                statements.append(f"GRANT USAGE ON SCHEMA {schema} TO {role}")
            if reads:
                privileges = "SELECT" + (
                    f", {WRITE}" if schema in access["write"] else ""
                )
                statements.append(
                    f"ALTER DEFAULT PRIVILEGES IN SCHEMA {schema} "
                    f"GRANT {privileges} ON TABLES TO {role}"
                )
    return statements


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    for schema in SCHEMAS:
        op.execute(f"CREATE SCHEMA {schema}")
    for statement in _access_statements():
        op.execute(statement)
    op.execute(TABLES)
    for statement in TABLE_GRANTS:
        op.execute(statement)


def downgrade() -> None:
    for login in LOGINS:
        for schema in SCHEMAS:
            op.execute(
                f"ALTER DEFAULT PRIVILEGES IN SCHEMA {schema} "
                f"REVOKE ALL ON TABLES FROM trading_agent_{login}"
            )
    for schema in reversed(SCHEMAS):
        op.execute(f"DROP SCHEMA {schema} CASCADE")
