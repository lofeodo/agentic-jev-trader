-- First numbered file. It creates nothing: applying it proves that schemachange logs in as
-- the migrations role and records a change in METADATA.CHANGE_HISTORY, on each database.
-- Later tickets add V2__..., V3__... with the tables of appendix 6. schemachange applies each
-- V file once, in version order, so a file is never edited after it has been applied.
-- Files name tables without a database (REF.DATASETS, not TRADING_AGENT.REF.DATASETS): the
-- same files build TRADING_AGENT and TRADING_AGENT_TEST.
SELECT CURRENT_DATABASE(), CURRENT_ROLE();
