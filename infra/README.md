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

## The kind cluster (being built)

The same code can also run in a local kind cluster (a small Kubernetes cluster inside Docker,
which runs and restarts programs). Its pieces sit beside the Snowflake setup, apart from it:

- `terraform/kubernetes/` is Terraform's Kubernetes part, a root of its own with its own
  state: the memory server, the API and the web app in the cluster. It has no resources yet.
- `images.py` builds the two images (an image is a packed copy of a program with everything
  it needs to run; recipes `Dockerfile` and `web/Dockerfile`) and loads them into kind. Not
  built yet.

`JOB_LAUNCHER=kubernetes` in `.env` (start each sim or dataset build as a Kubernetes Job, a
one-off run inside the cluster) is accepted, but starting a job with it is refused as not built
yet. CI's `deployment-check` job holds the deployment check's steps, each doing nothing yet.
