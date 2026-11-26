"""The written list of paths through the agent (spec appendix 10, section 8).

Each recorded-answer scenario names the one path it covers, word for word from this list, and
`test_paths.py` fails when a scenario names a path not listed or a path has no scenario. The
paths are the spec's, in its order, with two items written out so the check can hold them:

- "each of the three 'nothing to show' cases" (appendix 4): two of them are already lines of the
  list ("the LLM selects none", "a full evaluation in the agent without memory"), so only the
  third, memory holding none yet, is added;
- "everything is sold (ADR 0009), including the holding sim that holds the five assets" is two
  paths, the agent's sim and the holding sim.

Terms (appendices 1 and 4 have the rules): a **short** is a bet that the price falls (sell $2,000
of borrowed stock, the price falls 1%, the account is up $20). A **stop price** is the price at
which code closes a trade by itself to cap its loss. The **daily loss limit** blocks new trades
for the rest of the UTC day once the account is down 5% since midnight ($500 of $10,000). A
**forced close** is code closing every position when the account's value falls below a quarter
of what it holds.
"""

NO_POSITION = (
    "the screen says no",
    "the LLM answers at once",
    "the LLM looks further first",
    "the LLM hits its limit of 6 lookups",
    "the LLM replies without a tool call and is asked again",
    "the LLM names an episode ID it was never shown",
    "the LLM selects none",
    "nothing to show: memory holds none yet",
    "Jev picks no trade",
    "a pick where adding the probabilities by direction changes the winner",
    "a short is picked",
    "a size above what a limit allows",
    "a new trade blocked by the daily loss limit",
    "a full evaluation in the agent without memory",
)

OPEN_POSITION = (
    "a position screen that says no",
    "a position review ending in hold",
    "a position review ending in close",
    "a position review ending in reduce",
    "a position review ending in add",
    "an end-of-session review",
    "a review where the LLM selects none",
    "a review in the agent without memory",
    "a position closed at its stop price",
    "a forced close",
)

# ADR 0009.
SIM_ENDS = (
    "everything is sold at the sim's last step",
    "the holding sim sells the five assets at its last step",
)

# Tested with hand-written fake answers: failures cannot be recorded on demand.
SERVICE_FAILURES = (
    "a service failing 3 times stops the sim",
    "a third failed reply stops the sim",
)

PATHS = (*NO_POSITION, *OPEN_POSITION, *SIM_ENDS, *SERVICE_FAILURES)
