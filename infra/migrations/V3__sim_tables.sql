-- The SIM group: a sim's bookkeeping (spec appendix 6, section 3.4), written by the sim's job.
-- A sim (trading sim) is one replay of the agent, or of the holding comparison, over a stretch
-- of a dataset's steps with pretend money. Real names, prices and dates never appear here:
-- assets are masked IDs (ASSET_01), time is step numbers.
--
-- How a step is written (appendix 6, section 6): everything a step stores goes in one
-- transaction with SIMS.LAST_COMPLETED_STEP moving from N-1 to N, and the write goes through
-- only if it still reads N-1 and the sim is running. Snowflake does not enforce
-- PRIMARY KEY, so every record carries an ID built from what it describes (sim, step, asset),
-- and every sim ends by counting duplicate IDs and expecting none.
--
-- Access comes per schema from Terraform's future grants: the sim job reads and writes SIM;
-- the API reads it. The per-table grants below are the exceptions Terraform leaves to this file.

-- Sim IDs. The sim job takes one when a sim is started from the command line; the API will too.
CREATE SEQUENCE SIM.SIM_IDS START = 1 INCREMENT = 1;
GRANT USAGE ON SEQUENCE SIM.SIM_IDS TO ROLE TRADING_AGENT_SIM;
GRANT USAGE ON SEQUENCE SIM.SIM_IDS TO ROLE TRADING_AGENT_API;

-- One row per sim.
-- KIND: 'practice', 'tuning', 'build-up', 'measurement' or 'free'.
-- VARIANT: 'buy_hold', 'memory_off' or 'memory_on'.
-- MARKET: the test period's name for a measurement sim ('falling market').
-- SETTINGS: every setting the sim runs with, as one document (trading costs, stop prices, the
--   risk profile, and later the LLM and search settings); a resumed sim reads them from here.
-- STATUS: 'created', 'running', 'stopped', 'finished' or 'failed'.
-- STOP_REASON: 'finished', 'spending cap', 'Jev failed', 'LLM failed', 'account at zero' or
--   'stopped by hand'. FAILURE_REASON: what went wrong, for a failed sim.
-- LAST_COMPLETED_STEP: the last step stored; NULL until the first step is stored.
-- ACCOUNT_STATE: the account as it stood after that step (cash, open positions, orders still
--   waiting, last prices, the day's starting value), so a restarted sim carries on from it
--   (ADR 0013).
-- RUNNING_ON: where the job runs ('pid 1234' on the developer's machine, or a cluster Job).
-- LAST_WRITTEN_AT: when LAST_COMPLETED_STEP last moved; a running sim quiet for 7 minutes is shown as
--   not responding.
CREATE TABLE SIM.SIMS (
    ID NUMBER NOT NULL PRIMARY KEY,
    DATASET NUMBER NOT NULL,
    KIND VARCHAR NOT NULL,
    VARIANT VARCHAR NOT NULL,
    REPEAT_NUMBER NUMBER,
    MARKET VARCHAR,
    FIRST_STEP NUMBER NOT NULL,
    LAST_STEP NUMBER NOT NULL,
    STARTING_VALUE FLOAT NOT NULL,
    RANDOM_SEED NUMBER NOT NULL DEFAULT 0,
    SETTINGS VARIANT NOT NULL,
    CODE_VERSION VARCHAR,
    MEMORY_FROM_SIM NUMBER,
    ESTIMATED_COST FLOAT,
    SPENDING_CAP FLOAT,
    STOPPED_BY_CAP BOOLEAN NOT NULL DEFAULT FALSE,
    STATUS VARCHAR NOT NULL,
    STOP_REASON VARCHAR,
    FAILURE_REASON VARCHAR,
    LAST_COMPLETED_STEP NUMBER,
    ACCOUNT_STATE VARIANT,
    RUNNING_ON VARCHAR,
    CREATED_AT TIMESTAMP_NTZ,
    STARTED_AT TIMESTAMP_NTZ,
    LAST_WRITTEN_AT TIMESTAMP_NTZ,
    ENDED_AT TIMESTAMP_NTZ
);
-- The API adds a sim request, marks a killed sim 'stopped by hand' and records a new cap.
GRANT INSERT, UPDATE ON TABLE SIM.SIMS TO ROLE TRADING_AGENT_API;
-- The memory server reads a sim's settings.
GRANT SELECT ON TABLE SIM.SIMS TO ROLE TRADING_AGENT_MEMORY;

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
CREATE TABLE SIM.ORDERS (
    ID VARCHAR NOT NULL PRIMARY KEY,
    SIM NUMBER NOT NULL,
    POSITION NUMBER,
    INSTRUMENT VARCHAR NOT NULL,
    DECISION VARCHAR,
    KIND VARCHAR NOT NULL,
    REASON VARCHAR NOT NULL,
    SIDE VARCHAR,
    STEP_DECIDED NUMBER NOT NULL,
    STEP_CARRIED_OUT NUMBER,
    STATUS VARCHAR NOT NULL,
    UNITS FLOAT,
    PRICE_BEFORE_SLIPPAGE FLOAT,
    PRICE FLOAT,
    VALUE FLOAT,
    SLIPPAGE_COST FLOAT,
    COMMISSION_OR_TRADING_FEE FLOAT,
    AMOUNT_CHOSEN FLOAT,
    AMOUNT_AFTER_TRIMMING FLOAT,
    LIMITED_BY VARCHAR
);

-- The account at each step the sim looked at. ID: sim and step. LOAN is what the account owes
-- for positions bought beyond its own cash; EXPOSURE all positions added together, a short
-- counted like a long; START_OF_DAY_VALUE the account value at the last midnight UTC.
CREATE TABLE SIM.ACCOUNT_STEPS (
    ID VARCHAR NOT NULL PRIMARY KEY,
    SIM NUMBER NOT NULL,
    STEP NUMBER NOT NULL,
    CASH FLOAT NOT NULL,
    LOAN FLOAT NOT NULL,
    EXPOSURE FLOAT NOT NULL,
    ACCOUNT_VALUE FLOAT NOT NULL,
    START_OF_DAY_VALUE FLOAT NOT NULL,
    DAILY_LOSS_REACHED BOOLEAN NOT NULL
);

-- Nightly charges at midnight UTC. STEP is the step that ends at that midnight (96 for the
-- first). KIND: 'borrow_fee' (a short's, POSITION set) or 'loan_interest' (POSITION empty).
-- CHARGED_ON: the short's value or the loan, in dollars; YEARLY_RATE: 0.05 is 5% a year.
CREATE TABLE SIM.CHARGES (
    ID VARCHAR NOT NULL PRIMARY KEY,
    SIM NUMBER NOT NULL,
    STEP NUMBER NOT NULL,
    KIND VARCHAR NOT NULL,
    POSITION NUMBER,
    CHARGED_ON FLOAT NOT NULL,
    YEARLY_RATE FLOAT NOT NULL,
    AMOUNT FLOAT NOT NULL
);

-- Notable moments, for the live sim screen. KIND: 'restarted', and later 'forced close',
-- 'daily loss limit tripped', 'spending cap reached', 'stopped', 'an LLM limit hit',
-- 'an unknown episode ID dropped', 'a failed reply'.
CREATE TABLE SIM.SIM_EVENTS (
    ID VARCHAR NOT NULL PRIMARY KEY,
    SIM NUMBER NOT NULL,
    STEP NUMBER NOT NULL,
    KIND VARCHAR NOT NULL,
    DETAILS VARIANT
);

-- Paid Jev and LLM calls. SIM is empty for a call made outside a sim (the LLM benchmark, saving
-- answers for tests). The holding sim makes none.
CREATE TABLE SIM.CALLS (
    ID VARCHAR NOT NULL PRIMARY KEY,
    SIM NUMBER,
    PURPOSE VARCHAR NOT NULL,
    STEP NUMBER,
    ASSET VARCHAR,
    DECISION VARCHAR,
    SERVICE VARCHAR NOT NULL,
    MODEL VARCHAR,
    TOKENS_IN NUMBER,
    CACHED_TOKENS NUMBER,
    TOKENS_OUT NUMBER,
    THINKING_TOKENS NUMBER,
    COST_USD FLOAT,
    LATENCY_SECONDS FLOAT,
    RETRIES NUMBER,
    ERROR VARCHAR,
    CALLED_AT TIMESTAMP_NTZ
);
