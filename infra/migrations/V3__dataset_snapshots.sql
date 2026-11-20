-- The tables a dataset build writes for its snapshots (spec appendix 6, sections 3.1, 3.3, 9).
-- A snapshot is everything code measures about one asset at the step a 15-minute bar ends:
-- its candle patterns, 58 measurements, the feature vector (58 standard scores), the situation
-- text (a paragraph written by code) and the text's embedding (768 numbers from the model
-- snowflake-arctic-embed-m-v1.5, so memory can find similar texts). All are worked out once,
-- when the dataset is built. Access comes from Terraform's future grants: the builder writes
-- REF and FEATURES; the sim and the memory server read them.

-- The settings behind the measurements and the situation text: bars and days each looks back
-- over, the pattern window, the volume word's cut-offs.
ALTER TABLE REF.DATASETS ADD COLUMN MEASUREMENT_SETTINGS VARIANT;

-- The warm-up period's average and spread of each measurement, frozen with the dataset and
-- shared by its assets. POSITION is the measurement's place in the feature vector (1 to 58).
-- AVERAGE and SPREAD are NULL for a measurement with no spread in the warm-up: it scores 0.
CREATE TABLE REF.WARMUP_STATS (
    DATASET NUMBER NOT NULL,
    POSITION NUMBER NOT NULL,
    MEASUREMENT VARCHAR NOT NULL,
    AVERAGE FLOAT,
    SPREAD FLOAT,
    PRIMARY KEY (DATASET, POSITION)
);

-- One row per candle pattern (a TA-Lib detector and a lean), for one TA-Lib version; shared by
-- every dataset built with it. PATTERN is TA-Lib's detector (CDLENGULFING), LEAN 'bullish',
-- 'bearish' or 'neutral', NAME what every reader sees ('bullish engulfing'), SHAPE the shape
-- in plain words from TA-Lib's source.
CREATE TABLE REF.PLAYBOOK (
    TALIB_VERSION VARCHAR NOT NULL,
    PATTERN VARCHAR NOT NULL,
    LEAN VARCHAR NOT NULL,
    NAME VARCHAR NOT NULL,
    SHAPE VARCHAR NOT NULL,
    PRIMARY KEY (TALIB_VERSION, PATTERN, LEAN)
);

-- A candle pattern recognised on a bar. BAR_SIZE is '15m', '1h' or '1d'; STEP the step at
-- which that bar ends (as in RAW.BARS); PATTERN the playbook's NAME.
CREATE TABLE FEATURES.PATTERNS (
    DATASET NUMBER NOT NULL,
    ASSET VARCHAR NOT NULL,
    BAR_SIZE VARCHAR NOT NULL,
    STEP NUMBER NOT NULL,
    PATTERN VARCHAR NOT NULL
);

-- One row per asset and step with a 15-minute bar. MEASUREMENTS holds the 58 numbers in the
-- order of REF.DATASETS.MEASUREMENTS, NULL where not available. A vector cannot be passed as a
-- bound parameter: the builder writes rows to SNAPSHOTS_LOADING as JSON text, and moves them
-- here with a cast, embedding each situation text with AI_EMBED on the way.
CREATE TABLE FEATURES.SNAPSHOTS (
    DATASET NUMBER NOT NULL,
    ASSET VARCHAR NOT NULL,
    STEP NUMBER NOT NULL,
    MEASUREMENTS ARRAY NOT NULL,
    FEATURE_VECTOR VECTOR(FLOAT, 58) NOT NULL,
    SITUATION_TEXT VARCHAR NOT NULL,
    EMBEDDING VECTOR(FLOAT, 768) NOT NULL,
    PRIMARY KEY (DATASET, ASSET, STEP)
);

-- Snapshots on their way into FEATURES.SNAPSHOTS, before their texts are embedded. Emptied
-- once a build ends or fails, but a build killed outright leaves its rows here: whatever
-- stops a build by hand must delete them. MEASUREMENTS and FEATURE_VECTOR are JSON lists as text.
CREATE TRANSIENT TABLE FEATURES.SNAPSHOTS_LOADING (
    DATASET NUMBER NOT NULL,
    ASSET VARCHAR NOT NULL,
    STEP NUMBER NOT NULL,
    MEASUREMENTS VARCHAR NOT NULL,
    FEATURE_VECTOR VARCHAR NOT NULL,
    SITUATION_TEXT VARCHAR NOT NULL
);
