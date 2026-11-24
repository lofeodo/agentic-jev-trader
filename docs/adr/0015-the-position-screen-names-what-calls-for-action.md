# The position screen's question names what calls for action

The position screen is the cheap yes-or-no question Jev (the hosted decision model) answers about each open position at every step (every 15 minutes): should this position get a closer look now? A yes (0.5 or above) runs a position review, where Jev decides to hold the position, close it, reduce it (sell part) or add to it (ADR 0010). Asked "is the position worth a review?", Jev said yes to 27 of 27 position screens on the first practice day with open positions. The gate let everything through: every position was reviewed every 15 minutes, and each review was a fresh chance to close a good trade on a wobble in Jev's answer. In that sim the reviews closed 5 positions, all while losing $52 to $76 and well before their stop prices (the price at which code closes a losing position by itself).

So the position screen's question now names what makes a day trader look again at a trade they hold, and what does not, as ADR 0014 did for the screen. A bar is one 15-minute stretch of trading: its opening, highest, lowest and closing price. Volume is how much was traded in it, compared with what is usual for that asset. What counts:

- a hard move against the position on volume well above normal: a long (a bet that the price rises) of $10,000 drops $60 in one bar while twice the usual amount trades;
- the price near its stop price;
- a strong bar back against the trade after it had gone its way: the same long was up $50 over four bars, then gives back $40 in one;
- a good gain that has stopped moving: the long was up $80 and has sat at $50 for several bars that go nowhere.

What does not: the price drifting the trade's way, small bars that go up and down without getting anywhere (choppy), and average volume. It ends by saying that most positions at most steps need no action.

This extends ADR 0014's exception to the rule that Jev's text holds no rules of thumb: the exception now covers the screen's question and the position screen's question. The background, the full evaluation and the position review still carry facts, not advice.

## Considered Options

On 2026-11-24 seven wordings were asked, twice each, on the same 50 positions. Each was built with the real agent and broker code at a random step of dataset 1 (stocks and crypto, long and short, open 0 to 12 bars), and only the question changed between wordings. About 5 cents.

| Wording | Said yes (run 1, run 2) |
|---|---|
| "Is the position worth a review?" (the old one) | 50, 50 |
| The checklist, long version ("Would a disciplined day trader holding the position act on it now?") | 9, 7 |
| The checklist, short version (chosen) | 9, 8 |
| "Left alone until something changes: has something changed?" | 31, 29 |
| "A day trader acts at only about one step in eight. Is this one?" | 9, 11 |
| "Should it simply be held?", with a no running the review | 14, 14 |
| "Is there a clear reason to act now rather than hold?" | 20, 21 |

- **Raising the cut-off** under the old wording. Its answers all fell between 0.62 and 0.80 and followed nothing about the position, so a higher cut-off sorts by noise: at 0.75 the two runs said yes 20 and 13 times. The spec also leaves setting the cut-off from a sim's own records out of version 1.
- **"One step in eight"** had the right share, but 96% of its answers sat within 0.1 of the cut-off: coin flips.
- **"Should it simply be held?"** followed how near the stop price was best of all, but most of its answers sat near the cut-off, and it needs code to read a no as the review.
- **The long checklist** behaved like the short one with more answers near the cut-off.

The short checklist's answers spread from 0.13 to 0.71, with fewest near the cut-off (18%), and follow unusual volume (a match of 0.29, where 1 would be perfect and 0 none) and a gain given back (0.49). The old wording's matched unusual volume at 0.09, and with every answer a yes it picked out nothing.

## Consequences

- A one-day practice sim with the new wording (sim 201, the same day as sim 2) said yes to 7 of 29 position screens (24.1%), against 27 of 27 before. Its answers ran from 0.16 to 0.69. With the screen's 10 of 115, the two kinds of screen together said yes 17 times in 144 (11.8%), under the 30% at which the spec stops for the developer. Its position reviews closed 2 positions; sim 2's closed 5.
- The short checklist reacts only weakly to the price nearing the stop price (a match of 0.17). The stop price still closes the position by code, so a missed review there costs a chance to close early, not an unguarded loss. The test's positions were mostly calm (5 of 50 reached their stop within the next 8 bars), so this is the part least checked.
- Jev's yes on the position screen partly reflects the checklist, not only its own judgment. Every agent reads the same question, so the agents with and without memory still differ only by memory.
- A stock's end-of-session review still runs without the position screen.
