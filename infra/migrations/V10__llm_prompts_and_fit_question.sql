-- What the agent with memory stores beyond V9 (spec appendix 5, section 8; appendix 4, section
-- 10). Access comes per schema from Terraform's future grants: the sim job reads and writes SIM
-- and MEMORY.

-- What every LLM exchange of one prompt version opens with, stored once: SYSTEM_PROMPT, the
-- standing instructions word for word, and TOOLS, the four tools as the first call offers them
-- (name, description, inputs). SIM.LLM_EXCHANGES keeps every message after these. The lookup
-- tools' lists of candle patterns come from the playbook of the dataset's TA-Lib version: the
-- row keeps the first sim's.
CREATE TABLE SIM.LLM_PROMPTS (
    PROMPT_VERSION VARCHAR NOT NULL PRIMARY KEY,
    SYSTEM_PROMPT VARCHAR NOT NULL,
    TOOLS VARIANT NOT NULL,
    CREATED_AT TIMESTAMP_NTZ
);

-- MEMORIES_RELEVANT: Jev's probability that the past episodes shown fit the current situation,
-- a recorded-only question asked in a full evaluation's request 1 when at least one episode is
-- shown; empty on every other row.
ALTER TABLE MEMORY.DECISIONS ADD COLUMN MEMORIES_RELEVANT FLOAT;
