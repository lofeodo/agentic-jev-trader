-- The local Postgres's first start (compose.yaml): what Terraform makes on RDS, with the local
-- passwords the database tests use (tests/postgres/helpers.py, LOCAL_ENV). Run once, as the
-- container's own superuser, before the tables exist; Alembic then makes the tables as the
-- setup login (CLAUDE.md, the database tests under Commands).

-- The five logins (spec appendix 11, section 1). What each may read and write is granted by
-- Alembic's first file, as it makes the tables.
CREATE ROLE trading_agent_builder LOGIN PASSWORD 'local-builder';
CREATE ROLE trading_agent_sim LOGIN PASSWORD 'local-sim';
CREATE ROLE trading_agent_memory LOGIN PASSWORD 'local-memory';
CREATE ROLE trading_agent_api LOGIN PASSWORD 'local-api';
CREATE ROLE trading_agent_setup LOGIN PASSWORD 'local-setup';

-- The two databases, as on RDS, both owned by the setup login, which makes the tables.
CREATE DATABASE trading_agent OWNER trading_agent_setup;
CREATE DATABASE trading_agent_test OWNER trading_agent_setup;

-- pgvector, for the lists of numbers memory compares. Only a superuser may add it.
\connect trading_agent
CREATE EXTENSION vector;
\connect trading_agent_test
CREATE EXTENSION vector;
