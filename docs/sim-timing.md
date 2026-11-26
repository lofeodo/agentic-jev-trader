# Sim timing runs

How long one step of a sim takes (one 15-minute tick of the replay), and where that time goes:
the database, Jev, the LLM, memory's lookups, and the rest (the sim's own work). Spec appendix
11, section 6: two "before" runs on Snowflake, two "after" runs on Postgres (ADR 0018). Each is
one sim day (96 steps) of `sim practice` on the same day of dataset 1, run alone.

The figures are the last line of each run's output, `Timing, average of N steps: ...`, in
seconds per step. Done when the database part is under 0.1 s in both "after" runs.

| Run | Runs on | Sim | Date | Steps | Step | Database | Jev | LLM | Memory | Rest |
|---|---|---|---|---|---|---|---|---|---|---|
| Before, without memory | Snowflake | not run yet | | | | | | | | |
| Before, with memory | Snowflake | not run yet | | | | | | | | |
| After, without memory | Postgres | not run yet | | | | | | | | |
| After, with memory | Postgres | not run yet | | | | | | | | |

What counts toward no step: what a sim reads once before its first step (its bars, its
settings, its copy of memory). The command's own `Seconds a step` line includes it, so it is
written down beside each run too. LangSmith tracing time falls in "rest": run the before and
after runs with the same tracing setting.
