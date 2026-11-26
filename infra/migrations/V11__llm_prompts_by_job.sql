-- SIM.LLM_PROMPTS by job (spec appendix 5, section 8). Since the position review got its own
-- selection (the LLM's second job), one prompt version covers both jobs, and a row stores both:
--
-- SYSTEM_PROMPT: JSON text with one key per job, 'full_evaluation' and 'position_review', each
--   that job's standing instructions word for word. Read one with
--   PARSE_JSON(SYSTEM_PROMPT):position_review::VARCHAR.
-- TOOLS: an object with the same keys, each that job's tools as its first call offers them
--   (name, description, inputs).
--
-- Rows stored before this held only the full evaluation's: SYSTEM_PROMPT as plain text and TOOLS
-- as a list. This rewrites them to the same shape, under 'full_evaluation' alone, so every row
-- reads one way. A row already by job has TOOLS as an object and is left as it is.
UPDATE SIM.LLM_PROMPTS
SET
    SYSTEM_PROMPT = TO_JSON(OBJECT_CONSTRUCT('full_evaluation', SYSTEM_PROMPT)),
    TOOLS = OBJECT_CONSTRUCT('full_evaluation', TOOLS)
WHERE IS_ARRAY(TOOLS);

-- Notes that V9 and V10 wrote for full evaluations only, now that a position review with memory
-- asks the LLM too:
--
-- MEMORY.DECISIONS: LLM_MODEL, PROMPT_VERSION, SELECTED, LLM_NOTE, LIMIT_HIT, EPISODES_SHOWN and
--   LOOKUPS are filled on a full evaluation's row and on a position review's row whenever the LLM
--   was asked. A review's selection is its fresh memory; the entry memory the position was opened
--   on stays on the full evaluation's row that opened it (reached through SIM.ORDERS).
-- MEMORY.DECISIONS.MEMORIES_RELEVANT: also asked in a position review when at least one past
--   episode is shown.
-- SIM.LLM_EXCHANGES: one row per full evaluation or position review in which the LLM was asked;
--   ID is that decision's ID.
