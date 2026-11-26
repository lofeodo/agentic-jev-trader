# Sim timing runs

How long one step of a sim takes (one 15-minute tick of the replay), and where that time goes:
the database, Jev, the LLM, memory's lookups, and the rest (the sim's own work). Spec appendix
11, section 6: two "before" runs on Snowflake, two "after" runs on Postgres (ADR 0018). Each is
one sim day (96 steps) of `sim practice` on the same day of dataset 1, run alone.

The figures are the last line of each run's output, `Timing, average of N steps: ...`, in
seconds per step. Done when the database part is under 0.1 s in both "after" runs.

All four runs replay steps 9409 to 9504 of dataset 1; the runs with memory start from a copy of
sim 201's memory (`--first-step 9409`, and `--memory-from 201` for the runs with memory).

| Run | Runs on | Sim | Date | Steps | Step | Database | Jev | LLM | Memory | Rest |
|---|---|---|---|---|---|---|---|---|---|---|
| Before, without memory | Snowflake | 603 | 2026-11-26 | 96 | 4.40 | 4.12 | 0.28 | 0.00 | 0.00 | 0.00 |
| Before, with memory | Snowflake | 701 | 2026-11-26 | 96 | 6.94 | 4.17 | 0.29 | 0.54 | 1.94 | 0.00 |
| After, without memory | Postgres | not run yet | | | | | | | | |
| After, with memory | Postgres | not run yet | | | | | | | | |

The command's `Seconds a step` (setup included): 4.46 for sim 603, 7.02 for sim 701. Cost:
$0.017 for sim 603, $0.033 for sim 701. LangSmith tracing was on for both (`LANGSMITH_TRACING=true` in `.env`); its time is in "rest",
0.00 s a step. The memory server
reads Snowflake too, so on Snowflake its 1.94 s is mostly database time on the server's side.

What counts toward no step: what a sim reads once before its first step (its bars, its
settings, its copy of memory). The command's own `Seconds a step` line includes it, so it is
written down beside each run too. LangSmith tracing time falls in "rest": run the before and
after runs with the same tracing setting.
