# A restarted sim carries on from the account saved with its last completed step

A sim (one replay of the agent, or of the holding comparison, over a stretch of past market days) can be stopped partway through, by a crash, by a Stop or by its spending cap, and then restarted. To carry on, it needs its account exactly as it stood after the last step it stored: its cash, its open positions, the orders still waiting for their asset's next bar, each asset's last price, and the account value at the start of the day. Spec appendix 6 says the restart rebuilds that account from the stored records. Instead, every step's write saves a copy of the account, as one JSON document in `SIM.SIMS.ACCOUNT_STATE`, in the same transaction (the group of writes that all land or none do) and the same statement that moves the sim's last completed step. A restart reads the copy back and carries on from the next step. Example: a holding sim killed at step 140 after storing up to step 136 reads back $0.01 of cash and two positions worth $5,000 each, and works steps 137 onwards again exactly as before, so it ends with the same records as a sim that was never stopped. We chose this because the copy cannot disagree with what the sim had in memory, while a rebuild would have to redo the broker's arithmetic from orders, nightly charges and positions, and any mistake in that would show up only after a restart.

## Considered Options

- **Rebuild the account from the stored records, as the spec describes.** Nothing extra is stored, but it needs the positions table (`MEMORY.POSITIONS`, built with the agent's sims) and a second, separate path through the broker's arithmetic (cash from every order and charge, each position's average price and costs) that must match the first to the cent.
- **Replay the sim from its first step.** Simple for the holding sim, which calls nothing paid, but an agent sim would ask Jev and the LLM again for every step, at real cost.

## Consequences

- The saved account is a few kilobytes and is rewritten with each write, on the sim's one row.
- The stored records stay the full history; the saved account is only where to carry on from. If the broker gains a field, `Broker.state` and `Broker.from_state` must carry it, and a test checks that a broker brought back carries on identically.
- A sim saved by an older version of the code may not load in a newer one. Version 1 restarts a sim with the same code it started with.
