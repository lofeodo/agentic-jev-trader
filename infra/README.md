# infra: the Snowflake setup

Snowflake is the hosted database that stores everything. This folder sets it up in a
repeatable way:

- `terraform/` creates the cloud pieces from files: the database `TRADING_AGENT`, the test
  database `TRADING_AGENT_TEST` (same tables, for the hand-run tests), seven schemas in
  each, the warehouse `TRADING_AGENT_WH` (the computer that runs queries), five roles, five
  service users and the grants between them.
- `migrations/` holds the numbered SQL files that create the tables. `schemachange` applies
  each file once, in order, to both databases, and records it in `METADATA.CHANGE_HISTORY`.
  A new table means a new file (`V2__...sql`); an applied file is never edited.
- `snowflake_admin.py` runs all of it with the settings from `.env`.

## The five logins

Each program logs in as its own service user (a login for a program, not a person) with its
own role, limited to its job (spec, appendix 6 section 10):

| Login | Role | Reads | Writes |
|---|---|---|---|
| Dataset builder | `TRADING_AGENT_BUILDER` | `REF`, `KEYS`, `RAW`, `FEATURES` | the same; the only role allowed to embed text |
| Sim | `TRADING_AGENT_SIM` | everything except `KEYS` | `SIM`, `MEMORY` |
| Memory server | `TRADING_AGENT_MEMORY` | `MEMORY`, `FEATURES`, `REF` (+ the sims table) | nothing |
| API | `TRADING_AGENT_API` | everything, `KEYS` included | single tables (below) |
| Migrations | `TRADING_AGENT_MIGRATIONS` | | creates and owns the tables |

Grants per table, such as the memory server reading `SIM.SIMS` or the API adding rows to
`REF.DATASETS`, go in the numbered SQL file that creates that table. Users are named after
their role with `_SVC` added (`TRADING_AGENT_MEMORY_SVC`).

Service users cannot use passwords. Each logs in with a key pair: a private key kept on this
machine (encrypted with `SNOWFLAKE_PRIVATE_KEY_FILE_PWD`) and a public key stored on the
Snowflake user. The private keys and Terraform's state file live in `SNOWFLAKE_LOCAL_DIR`
(default `.agentic-jev-trader/snowflake` in your home folder), never in the repo: a git
worktree is deleted when its work ends, and keys must never be committed.

## First-time setup

1. Fill in `SNOWFLAKE_ACCOUNT` and `SNOWFLAKE_PRIVATE_KEY_FILE_PWD` in `.env` (see
   `.env.example`). `SNOWFLAKE_LOCAL_DIR` is optional; `SNOWFLAKE_USER` and
   `SNOWFLAKE_PRIVATE_KEY_FILE` name the login the hand-run tests use, once it exists.
2. Make the key pairs. This also prints the SQL for step 3 and saves it as
   `create_terraform_user.sql` in the keys' folder:

   ```
   conda run -n agentic-jev-trader python infra/snowflake_admin.py keys
   ```

3. **Once, by hand:** open a SQL worksheet in Snowsight as `ACCOUNTADMIN` and run that SQL. It
   creates `TRADING_AGENT_TERRAFORM_SVC`, the login Terraform uses. It needs `ACCOUNTADMIN`
   because granting the embedding model to a role does.
4. See what Terraform would create, then create it:

   ```
   conda run -n agentic-jev-trader python infra/snowflake_admin.py terraform plan
   conda run -n agentic-jev-trader python infra/snowflake_admin.py terraform apply
   ```

5. Apply the numbered SQL files to both databases (test database first):

   ```
   conda run -n agentic-jev-trader python infra/snowflake_admin.py migrate
   ```

6. Check the result live: the builder's role can embed text, another role cannot, the
   memory server's role can only read, and both databases recorded the SQL files:

   ```
   conda run -n agentic-jev-trader python infra/snowflake_admin.py check
   ```

## The embedding model permission

Embedding turns a paragraph into a fixed list of 768 numbers, so that paragraphs describing
similar market moments get similar lists and memory can find past situations like the
current one. Snowflake runs the model and bills a little credit for each call.

Snowflake controls its built-in models by role. The builder's role gets two grants: the
database role `SNOWFLAKE.CORTEX_EMBED_USER` (use of the embedding feature) and the per-model
application role `CORTEX-MODEL-ROLE-SNOWFLAKE-ARCTIC-EMBED-M-V1.5` (use of that one model).
If Terraform's `snowflake_grant_application_role` fails on that Snowflake-owned role, switch
to the fallback, which runs the `GRANT` statement directly:

```
conda run -n agentic-jev-trader python infra/snowflake_admin.py terraform apply -var=embedding_grant_method=execute
```

A new account opens every AI model to every role. Terraform closes two of those defaults
for the whole account, with the developer's agreement: it takes `SNOWFLAKE.CORTEX_USER`
away from `PUBLIC` (the role every login has) and sets `CORTEX_MODELS_ALLOWLIST` to
`None`. Since then, of our five logins, only the builder can embed text. People's roles above it
(`ACCOUNTADMIN`, and `SYSADMIN`, which every project role sits under) can too. A person's own
role loses Snowflake's AI features too, unless given them the same way. `terraform destroy`
puts both defaults back.

A third default cannot be closed: Snowflake's own application role `SNOWFLAKE.PUBLIC`
holds the all-models role, and even `ACCOUNTADMIN` may not revoke it. So the builder can
use other models too, and `check` warns about it; the per-model grant is in place but
cannot be shown to work on its own on this account.

## The kind cluster

The same code can also run in a local kind cluster (a small Kubernetes cluster inside Docker,
which runs and restarts programs). Its pieces sit beside the Snowflake setup, apart from it:

- `kind-cluster.yaml` is the cluster's own settings: `kind create cluster --config
  infra/kind-cluster.yaml` makes the cluster `jev-trader`, which opens two ports to this
  computer only (127.0.0.1): the web app at http://127.0.0.1:8080 and the API at
  http://127.0.0.1:8081. The memory server is reached from inside the cluster only.
- `terraform/kubernetes/` is Terraform's Kubernetes part, a root of its own with its own
  state, kept outside the repo like the Snowflake part's (`-backend-config=path=...`). One
  apply puts the memory server, the API and the web app in the namespace `jev-trader` (a
  named compartment of the cluster that permissions can be limited to), each
  from the images tagged `image_tag`, and waits until each answers its health address. It also
  makes what the jobs need: one secret (a value the cluster stores and hands only to the
  programs named to receive it) per Snowflake login (`snowflake-api`, `snowflake-memory`,
  `snowflake-sim`, `snowflake-builder`, each holding the account, the passphrase and that
  login's key only), `models` (the Jev and LLM keys, for sims) and `twelve-data` (for builds),
  and the API's permission (a Role) to create, read and delete Jobs (and the ConfigMaps, small
  stored files, that carry a build's settings) in that namespace only. Each service reads its own login's secret only.
  The values come in as environment variables named `TF_VAR_<variable>` (the names in
  `terraform/kubernetes/variables.tf`) plus the keys folder (`snowflake_keys_dir`), and are
  sent to the cluster without Terraform keeping a copy (write-only attributes), so its state
  file never holds them. After changing a secret's value, raise
  `secrets_revision` by one, or Terraform does not send it. The ZAI key (the benchmark, on this
  computer only) and the LangSmith key (optional tracing) do not enter the cluster. `deploy.py`
  runs this part with the real values from `.env`, the images of the current commit and the
  keys folder, keeping the state as `kubernetes.tfstate` in `SNOWFLAKE_LOCAL_DIR` (`apply` puts
  real keys into the cluster):

  ```
  conda run -n agentic-jev-trader python infra/deploy.py plan
  conda run -n agentic-jev-trader python infra/deploy.py apply -auto-approve
  ```

- `images.py` builds the two images (an image is a packed copy of a program with everything
  it needs to run; recipes `Dockerfile` and `web/Dockerfile`), tags both with the git commit
  and copies them into kind straight from this computer, with no image registry (an online
  store of images the cluster would otherwise download from). It needs Docker running, the
  cluster created (`kind create cluster --config infra/kind-cluster.yaml`) and every change
  committed, since the tag names the commit:

  ```
  conda run -n agentic-jev-trader python infra/images.py build
  ```

  The Python image holds the code, `config/`, `prompts/`, `datasets/` and the pinned
  dependencies, never `.env`, a key or saved tables; each piece is started by its own command
  (`python -m jev_trader.memory serve`, `... api serve`, `... sim resume <id>`,
  `... dataset build <file>`). The web image serves the built web app on port 80 and hands its
  `/api/...` requests to the API at `API_URL` (`http://api:8000`, the cluster's API service,
  which must exist when the web app starts). In the cluster both servers run with
  `--in-cluster`: they listen on every address of their container, the API answers any caller
  on the cluster's private network (not only this computer), and both log in to Snowflake on
  first use rather than at start, so they report healthy even with dummy logins.
- `wait_healthy.py` waits until the memory server, the API and the web app each answer their
  health address, and names any that never did (the deployment check's wait; the docstring
  has the command to run it by hand against your own cluster).

The API in the cluster starts each sim or dataset build as a Kubernetes Job (a one-off run
inside the cluster, `JOB_LAUNCHER=kubernetes`), from its own image, running the same command
as on this computer. A sim's Job is named `sim-<id>-<6 random characters>` (a fresh one each time the sim
starts or resumes) and reads the `snowflake-sim` and `models` secrets; a build's Job is
`dataset-<id>-<database>` (such as `dataset-3-trading-agent`) and reads `snowflake-builder` and `twelve-data`, with its settings file in the
ConfigMap of the same name. Neither gets a way to reach the cluster itself. A Job that ended
is kept, so its output stays readable (Stop removes the Job and its output with it):

```
kubectl logs job/sim-12-a1b2c3 -n jev-trader
```

An API run on this computer with `JOB_LAUNCHER=kubernetes` in `.env` starts Jobs in the same
cluster (the entry `kind-jev-trader` in this computer's cluster settings, `~/.kube/config`),
from the image of the checkout's commit.

CI's `deployment-check` job does all of this in a throwaway kind cluster on every pull request,
with dummy secrets (placeholders, no real key): it builds and loads both images, applies
Terraform's Kubernetes part, runs `wait_healthy.py` from a pod (one running container in the
cluster) inside the cluster, then has the API's launcher start a sim's Job and checks the Job
ran. The Job fails at its Snowflake login, as expected, because the dummy key is not a key:
its output says `Unable to load PEM file` (PEM is the text format a private key is saved in),
before any network call. When a step fails, the job prints the pods' logs.

## Postgres on AWS RDS

Postgres on Amazon's hosted database service, RDS, replaces Snowflake (spec appendix 11,
ADR 0018). `infra/rds.py` runs everything here; AWS is reached with the AWS CLI's login on this
computer (the `default` profile, set up once with `aws configure sso`), so no AWS key goes in
`.env` or the repo. The login lasts 8 hours: when a command says it has run out, run
`aws sso login` and try again.

Two Terraform roots, each with its state in `~/.agentic-jev-trader/rds`, outside the repo:

- `terraform/rds/`: the database (Postgres 17, the smallest size `db.t4g.micro`, one zone, in
  Montreal `ca-central-1`, a 20 GB encrypted disk, one day of automatic backups), the network rule
  that lets in only this computer's home internet address on the Postgres port (asked afresh on
  each run, so re-running `apply` after the address changes moves the rule), encrypted
  connections only, and a budget alarm that emails `AWS_BUDGET_EMAIL` once a month's whole AWS
  bill passes $5 (a warning only: it switches nothing off).
- `terraform/rds/postgres/`: inside the database, the same as `local-postgres/init.sql` makes in
  the local Postgres the tests use: the five logins as Postgres roles (`trading_agent_builder`,
  `_sim`, `_memory`, `_api`, `_setup`) with no rights of their own, the two databases
  `trading_agent` and `trading_agent_test` owned by the setup login, and `pgvector` in each (only
  the admin login may add it; it is the Postgres add-on that compares the lists of numbers memory
search uses). What each login may read and write, the memory login reading only,
  is granted by Alembic's first file as it makes the tables.

Passwords: the admin login's (`POSTGRES_ADMIN_PASSWORD`) and each login's
(`POSTGRES_<LOGIN>_PASSWORD`) stay in `.env`. They reach Terraform as `TF_VAR_*` environment
variables and go to AWS and Postgres write-only, so neither state file, nor any output, holds
them. After changing one, pass `-var=admin_password_version=2` (the admin's) or
`-var=passwords_version=2` (a login's) to `apply`, one more than the last, or Terraform does not
send it.

What it costs: about 2.3 cents an hour while the database is on (1.8 for the database, about
$13 a month if left on, and 0.5 for its internet address), and about $2.50 a month for its disk
even while stopped. A parked database (below) costs only
its snapshot, cents a month for a few GB.

### The commands

Each but `status` and `plan` costs money or changes the AWS account: Claude Code asks before each.

```
conda run -n agentic-jev-trader python infra/rds.py status
conda run -n agentic-jev-trader python infra/rds.py plan
conda run -n agentic-jev-trader python infra/rds.py apply -auto-approve
conda run -n agentic-jev-trader python infra/rds.py start
conda run -n agentic-jev-trader python infra/rds.py stop
conda run -n agentic-jev-trader python infra/rds.py snapshot-and-delete
conda run -n agentic-jev-trader python infra/rds.py restore
```

- `status` says whether the database is on, stopped, parked or not made yet, and its address.
- `plan` shows what `apply` would change, in both roots. Before the database exists, the logins'
  part is planned against a made-up address.
- `apply` makes or updates the database, then what is inside it, and prints the line
  `POSTGRES_HOST=...` to put in `.env`. The first one takes about 10 to 15 minutes, and the
  database is then on. A stopped database must be `start`ed first.
- `start` switches a stopped database on (a few minutes); `stop` switches it off. **Stop it after
  each working session.** AWS starts a stopped database again by itself after 7 days. Both wait
  out anything AWS is doing on its own first (a backup, a change).
- `snapshot-and-delete`, before a pause longer than a few days: saves the database as a snapshot
  (a copy of its disk) named `trading-agent-parked-<date and time>`, then deletes the database.
  Nothing inside is lost. Older parked snapshots stay (cents a month each); delete them in the
  AWS console when no longer wanted.
- `restore` makes the database again from the newest parked snapshot, with everything inside it,
  in about 10 to 15 minutes. Its address stays the same (it comes from the name
  `trading-agent`), so `.env` needs no change. It is on afterwards: stop it when done.

While parked, `plan` and `apply` leave the database out (they never make an empty one in its
place); `restore` brings it back.

First time: fill in `POSTGRES_ADMIN_PASSWORD`, the five `POSTGRES_<LOGIN>_PASSWORD` and
`AWS_BUDGET_EMAIL` in `.env`, run `plan`, then `apply -auto-approve`, put the printed
`POSTGRES_HOST` in `.env`, then make the tables with Alembic (CLAUDE.md), and `stop`.

### Moving the data in, and copies of it

Once, with the database on and its tables made: a fresh `storage save` of Snowflake, taken while
no sim or build is writing, goes in with `python -m jev_trader.storage load <save folder>`
(CLAUDE.md). It checks the text-to-numbers model first, loads every table in one transaction,
then compares row counts and some rows with the save.

From then on `storage save` (with `DATABASE_ENGINE=postgres`) is `pg_dump`: one file on this
computer. `storage restore <file>` loads it with `pg_restore` into a database that has the
logins, the database and pgvector but no tables: after `apply` on a new RDS, skip Alembic and
restore instead (the file holds Alembic's record too). Both tools run from the local Postgres's
Docker image, so nothing needs installing.
