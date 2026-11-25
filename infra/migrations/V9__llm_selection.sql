-- How the LLM selected the past episodes Jev read in a full evaluation of the agent with memory
-- (spec appendix 5, section 6; appendix 6, sections 3.5 and 8). The LLM (Claude Haiku or GLM
-- Flash) is shown past episodes as one-line summaries, may look further through memory (a
-- lookup: search again, read episodes in full, or read the track record), and answers with up to
-- 5 episodes and a one-line note. Access comes per schema from Terraform's future grants: the sim
-- job reads and writes SIM and MEMORY.
--
-- MEMORY.DECISIONS gains, empty on every row but a full evaluation in which the LLM was asked:
-- LLM_MODEL: the model the provider says answered ('claude-haiku-5-5').
-- PROMPT_VERSION: the fingerprint of the LLM's wording (prompts/llm_selection.toml and
--   prompts/llm_tools.toml).
-- SELECTED: the episodes selected, as stored decision IDs, most useful first; [] for none.
-- LLM_NOTE: the LLM's one-line note, cut at 200 characters. Jev never reads it.
-- LIMIT_HIT: 'lookups' (6 used) or 'time' (60 seconds up), if the LLM reached one.
-- EPISODES_SHOWN: every episode shown: its decision ID, the label the LLM saw ('E1'), its rank by
--   feature vector, by text and merged, whether the automatic first search found it, and whether
--   it was opened in full.
-- LOOKUPS: each lookup in order: the tool, the LLM's inputs, the episode IDs it returned, how
--   long it took, and why it was refused if it was ('lookups', 'time', or the value not allowed).
-- MEMORIES_RELEVANT: Jev's probability that the past episodes shown fit the current situation
--   (a recorded-only question, asked in request 1 when at least one episode is shown).
--
-- The tables appendix 6 sketches for the last two (DECISION_EPISODES, TOOL_CALLS) are columns of
-- the decision instead: they are read only with it.
--
-- SIM.CALLS gains rows with SERVICE 'anthropic' or 'zai' and PURPOSE 'select', one per call to
-- the LLM. SIM.SIM_EVENTS gains the kinds 'an LLM limit hit', 'a failed reply' and 'an unknown
-- episode ID dropped'.
ALTER TABLE MEMORY.DECISIONS ADD COLUMN
    LLM_MODEL VARCHAR,
    PROMPT_VERSION VARCHAR,
    SELECTED VARIANT,
    LLM_NOTE VARCHAR,
    LIMIT_HIT VARCHAR,
    EPISODES_SHOWN VARIANT,
    LOOKUPS VARIANT,
    MEMORIES_RELEVANT FLOAT;

-- What every exchange of one prompt version opens with, stored once (spec appendix 5, section
-- 8): SYSTEM_PROMPT, the standing instructions word for word, and TOOLS, the four tools as the
-- first call offers them (name, description, inputs). The lookup tools' lists of candle
-- patterns come from the playbook of the dataset's TA-Lib version: the row keeps the first sim's.
CREATE TABLE SIM.LLM_PROMPTS (
    PROMPT_VERSION VARCHAR NOT NULL PRIMARY KEY,
    SYSTEM_PROMPT VARCHAR NOT NULL,
    TOOLS VARIANT NOT NULL,
    CREATED_AT TIMESTAMP_NTZ
);

-- The LLM's exchange in one full evaluation, word for word. ID: the decision's ID.
-- MESSAGES: every message after the standing instructions, as sent and received (LangChain's
--   message records: the first message, each reply with its tool calls, each tool result and
--   fixed message). The standing instructions and tools are in SIM.LLM_PROMPTS, once per
--   PROMPT_VERSION.
-- FAILED_REPLIES: each reply code could not use, word for word.
-- SLIPS: each smaller slip carried on from ('repeated episode IDs removed', ...).
CREATE TABLE SIM.LLM_EXCHANGES (
    ID VARCHAR NOT NULL PRIMARY KEY,
    SIM NUMBER NOT NULL,
    STEP NUMBER NOT NULL,
    ASSET VARCHAR NOT NULL,
    DECISION VARCHAR NOT NULL,
    PROMPT_VERSION VARCHAR NOT NULL,
    MESSAGES VARIANT NOT NULL,
    FAILED_REPLIES VARIANT NOT NULL,
    SLIPS VARIANT NOT NULL
);
