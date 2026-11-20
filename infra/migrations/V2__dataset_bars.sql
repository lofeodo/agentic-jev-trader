-- The tables a dataset build writes up to its bars (spec appendix 6, sections 3.1 to 3.3).
-- A dataset is a fixed pile of market history every sim replays. Real names, prices and dates
-- live only in KEYS.ASSET_KEY; every other table uses masked IDs (ASSET_01) and step numbers.
-- Read and write access comes per schema from Terraform's future grants: the builder writes
-- REF, KEYS and RAW; only the builder and the API read KEYS. The snapshot tables (patterns,
-- measurements, embeddings), WARMUP_STATS and PLAYBOOK come in later files.

-- Dataset IDs. The builder takes one per build; the API will too, for a build it is asked for.
CREATE SEQUENCE REF.DATASET_IDS START = 1 INCREMENT = 1;
GRANT USAGE ON SEQUENCE REF.DATASET_IDS TO ROLE TRADING_AGENT_BUILDER;
GRANT USAGE ON SEQUENCE REF.DATASET_IDS TO ROLE TRADING_AGENT_API;

-- One row per dataset. STATUS is 'being built', 'published' or 'failed'. A failed build keeps
-- this row, with its reason, and loses every other row it wrote. Shares are fractions: 0.005
-- is 0.5%. CHECK_RESULT holds the check's measured value per asset and its verdict.
CREATE TABLE REF.DATASETS (
    ID NUMBER NOT NULL PRIMARY KEY,
    NAME VARCHAR NOT NULL,
    VERSION NUMBER NOT NULL,
    STATUS VARCHAR NOT NULL,
    PUBLISHED_WITHOUT_CHECK BOOLEAN NOT NULL DEFAULT FALSE,
    FAILURE_REASON VARCHAR,
    FIRST_STEP NUMBER,
    LAST_STEP NUMBER,
    DATA_PROVIDERS ARRAY,
    TALIB_VERSION VARCHAR,
    EMBEDDING_MODEL VARCHAR,
    MEASUREMENTS ARRAY,
    PARTIAL_VOLUME_SHARE_OF_USUAL FLOAT,
    PARTIAL_VOLUME_SESSIONS NUMBER,
    LIMIT_OTHER_MISSING FLOAT,
    LIMIT_PARTIAL_VOLUME_DAYS FLOAT,
    CHECK_RESULT VARIANT,
    PRICE_DECIMALS NUMBER,
    BUILD_STAGE VARCHAR,
    BUILD_PROGRESS FLOAT,
    STARTED_AT TIMESTAMP_NTZ,
    BUILT_AT TIMESTAMP_NTZ,
    PUBLISHED_AT TIMESTAMP_NTZ
);
-- The API adds a build request and marks a stopped build failed.
GRANT INSERT, UPDATE ON TABLE REF.DATASETS TO ROLE TRADING_AGENT_API;

-- KIND is 'warm-up' or 'test'; the test period is one row per stretch ('falling market').
CREATE TABLE REF.DATASET_PERIODS (
    DATASET NUMBER NOT NULL,
    KIND VARCHAR NOT NULL,
    NAME VARCHAR NOT NULL,
    FIRST_STEP NUMBER NOT NULL,
    LAST_STEP NUMBER NOT NULL
);

-- ASSET_CLASS is 'stock' or 'crypto'.
CREATE TABLE REF.ASSETS (
    DATASET NUMBER NOT NULL,
    MASKED_ID VARCHAR NOT NULL,
    ASSET_CLASS VARCHAR NOT NULL,
    PRIMARY KEY (DATASET, MASKED_ID)
);

-- The tradable form of an asset: one 'spot' instrument per asset in version 1.
CREATE TABLE REF.INSTRUMENTS (
    DATASET NUMBER NOT NULL,
    INSTRUMENT_ID VARCHAR NOT NULL,
    ASSET VARCHAR NOT NULL,
    TYPE VARCHAR NOT NULL,
    PRIMARY KEY (DATASET, INSTRUMENT_ID)
);

-- The quality report, part 1. STEP is the step at which the missing bar would have ended.
-- REASON is 'not supplied', 'zero volume' or 'partial-volume day'.
CREATE TABLE REF.MISSING_BARS (
    DATASET NUMBER NOT NULL,
    ASSET VARCHAR NOT NULL,
    STEP NUMBER NOT NULL,
    REASON VARCHAR NOT NULL
);

-- The quality report, part 2. DAY is the day number (1 is the dataset's first day). TEST is
-- 'a zero-volume bar' or 'volume under a quarter of usual'. SHARE_OF_USUAL: 0.08 is 8% of the
-- stock's usual volume per bar.
CREATE TABLE REF.PARTIAL_VOLUME_DAYS (
    DATASET NUMBER NOT NULL,
    ASSET VARCHAR NOT NULL,
    DAY NUMBER NOT NULL,
    TEST VARCHAR NOT NULL,
    SHARE_OF_USUAL FLOAT
);

-- The asset key: the only table with real names, prices and dates. A real price is the stored
-- price divided by PRICE_SCALE; real volume is stored volume divided by VOLUME_SCALE. FIRST_DAY
-- is the real (UTC) date of step 1.
CREATE TABLE KEYS.ASSET_KEY (
    DATASET NUMBER NOT NULL,
    MASKED_ID VARCHAR NOT NULL,
    TICKER VARCHAR NOT NULL,
    PROVIDER_SYMBOL VARCHAR NOT NULL,
    NAME VARCHAR NOT NULL,
    PRICE_SCALE FLOAT NOT NULL,
    VOLUME_SCALE FLOAT NOT NULL,
    FIRST_DAY DATE NOT NULL,
    PRIMARY KEY (DATASET, MASKED_ID)
);

-- Rescaled bars. BAR_SIZE is '15m', '1h' or '1d'. STEP is the step at which the bar ends.
-- BAR_NUMBER counts from 1 in the stock's session or the crypto's UTC day; BARS_LEFT is the
-- bars left in the session (0 on the last one), and NULL for crypto, which has no session.
CREATE TABLE RAW.BARS (
    DATASET NUMBER NOT NULL,
    ASSET VARCHAR NOT NULL,
    BAR_SIZE VARCHAR NOT NULL,
    STEP NUMBER NOT NULL,
    DAY NUMBER NOT NULL,
    BAR_NUMBER NUMBER NOT NULL,
    BARS_LEFT NUMBER,
    OPEN FLOAT NOT NULL,
    HIGH FLOAT NOT NULL,
    LOW FLOAT NOT NULL,
    CLOSE FLOAT NOT NULL,
    VOLUME FLOAT NOT NULL,
    PRIMARY KEY (DATASET, ASSET, BAR_SIZE, STEP)
);
