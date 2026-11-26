# Postgres on AWS RDS replaces Snowflake

Snowflake made the sims slow: a practice sim step took about 3.4 seconds when the sim ran alone and about 13 seconds when four sims shared the warehouse, while the paid calls to Jev in that step took only about 0.2 seconds (sims 501 and 602, 2026-11-26). Snowflake charges a fixed delay of a few hundred milliseconds or more on every statement, and each step makes several. So all data moves to PostgreSQL ("Postgres") on Amazon's managed service, RDS, and Snowflake is removed rather than kept alongside it. RDS runs at its smallest size in `ca-central-1`, the Montreal region Snowflake ran in, and is reachable only from the developer's home address. Each statement there takes about 0.05 seconds to travel from this computer to Montreal and back. The search over past episodes uses `pgvector`, a standard Postgres add-on for comparing lists of numbers, in place of Snowflake's built-in vector functions. The text-to-numbers model Snowflake ran for us (`snowflake-arctic-embed-m-v1.5`, an open model) runs on this computer instead.

## Considered options

- **Postgres in Docker on this computer**: free, and each statement takes about 1 millisecond. Rejected: the database is meant to live on AWS.
- **Postgres on a plain AWS server (EC2)**: a little cheaper than RDS, but the backups and updates would be ours to look after. Rejected for reliability: RDS is the standard tool used as it comes.
- **Keeping Snowflake beside Postgres**: two versions of every store to keep in step and to test. Rejected: one database at a time.

## Consequences

- **Cost.** RDS charges by the hour while it is switched on (about 1.8 cents an hour, about $13 a month if left on) and for its disk even when stopped (at least 20 GB, about $2.50 a month). So the database is stopped after each working session. Before any pause longer than a few days it is copied (a snapshot) and deleted, because AWS starts a stopped database again on its own after 7 days. An AWS budget alarm emails once a month's bill passes $5.
- **Keeping a copy.** `pg_dump` saves the whole database to one file on this computer, and `pg_restore` loads it into any Postgres, a new RDS included.
- **Tests.** The database tests now run in CI against a local Postgres, instead of only by hand.
