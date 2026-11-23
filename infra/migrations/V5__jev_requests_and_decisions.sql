-- What the agent's screen stores (spec appendix 4, section 13; appendix 6, sections 3.5 and 8).
-- Jev is the hosted decision model: it reads a background (a page of text) and answers questions
-- with probabilities. The screen is its quick question: is a full evaluation of this asset worth
-- running now? Real names, prices and dates never appear here. Access comes per schema from
-- Terraform's future grants: the sim job reads and writes SIM and MEMORY.

-- The opening of Jev's background, the part that is the same in every request of a sim, stored
-- once per reading version (a fingerprint worked out from the wording).
CREATE TABLE SIM.JEV_READINGS (
    READING_VERSION VARCHAR NOT NULL PRIMARY KEY,
    OPENING VARCHAR NOT NULL,
    CREATED_AT TIMESTAMP_NTZ
);

-- Every Jev request and answer, word for word. ID: sim, step, asset and purpose.
-- The whole background is the reading version's OPENING, a blank line, and
-- BACKGROUND_AFTER_OPENING. QUESTIONS is as sent; ANSWER is Jev's reply exactly as received.
-- PURPOSE: 'screen' for now. JEV_VERSION: the version that answered ('jev-1.14.0').
CREATE TABLE SIM.JEV_REQUESTS (
    ID VARCHAR NOT NULL PRIMARY KEY,
    SIM NUMBER NOT NULL,
    STEP NUMBER NOT NULL,
    ASSET VARCHAR NOT NULL,
    DECISION VARCHAR NOT NULL,
    PURPOSE VARCHAR NOT NULL,
    READING_VERSION VARCHAR NOT NULL,
    BACKGROUND_AFTER_OPENING VARCHAR NOT NULL,
    QUESTIONS VARIANT NOT NULL,
    ANSWER VARCHAR NOT NULL,
    JEV_VERSION VARCHAR NOT NULL
);

-- One row per asset looked at, at one step. ID: sim, step and asset; it stays the same in a copy
-- of a memory. SIM is the memory the row belongs to, FIRST_WRITTEN_BY the sim that wrote it.
-- KIND: 'screen' for now. TIER: 0 is code alone (nothing was asked), 1 is a screen.
-- SCREEN_ANSWER: Jev's probability of yes, from 0 to 1; empty at tier 0.
-- SKIPPED_BECAUSE: the limit that meant no trade could open ('daily_loss', 'session_end', ...).
-- ACTION: what was done: 'nothing' for now. Later tickets add the columns of a full evaluation.
CREATE TABLE MEMORY.DECISIONS (
    ID VARCHAR NOT NULL,
    SIM NUMBER NOT NULL,
    FIRST_WRITTEN_BY NUMBER NOT NULL,
    DATASET NUMBER NOT NULL,
    ASSET VARCHAR NOT NULL,
    STEP NUMBER NOT NULL,
    KIND VARCHAR NOT NULL,
    TIER NUMBER NOT NULL,
    SCREEN_ANSWER FLOAT,
    SKIPPED_BECAUSE VARCHAR,
    JEV_VERSION VARCHAR,
    ACTION VARCHAR NOT NULL,
    PRIMARY KEY (SIM, ID)
);
