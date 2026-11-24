# The screen's question names what a day trader looks for

The screen is the cheap yes-or-no question Jev (the hosted decision model) answers for every asset the account holds nothing in, at every step (every 15 minutes): should this asset get a closer look now? A yes (0.5 or above) runs a full evaluation, which can open a trade. Asked "is it worth a full evaluation?", Jev said yes to 190 of 192 screens on the first practice day: the agent would have looked closer at, and could have bought or sold, nearly everything all day. A day trader looks closer only at the few moments that stand out.

So the screen's question now names what counts and what does not, the way a day trader scans: a decisive move on volume well above normal (say 2.4 times the usual amount traded in 15 minutes, together with a large bar that breaks out of the day's range), or a clean trend turning back its way after a shallow pullback (a price rising all morning dips for two bars, then turns up again). It does not count a price drifting in the middle of the day's range, small bars that go up and down without getting anywhere (choppy), or average volume. It ends by saying that most assets at most steps do not qualify. The list comes from day-trading teaching on how traders scan for stocks in play.

This is an exception to the rule, decided on 2026-11-19, that Jev's text holds no rules of thumb because the project measures Jev's own judgment. The exception covers the screen's question only. The background, the full evaluation and the position review still carry facts, not advice.

## Considered Options

On 2026-11-24 seven wordings were asked on the same 50 stored screens of the first practice day:

| Wording | Said yes |
|---|---|
| "Is it worth a full evaluation?" (the old one) | 50 of 50 (100%) |
| "Does it stand out as a setup a day trader would act on now?" | 34% |
| "A day trader looks closer at only about one asset in seven. Is it one of them?" | 18% |
| "Is there a clear reason to act now rather than wait?" | 20% |
| "A full evaluation is worth running only if a setup stands out. Does it?" | 14% |
| The checklist, long version | 4% |
| The checklist, short version (chosen) | 10% |

- **The wordings without a checklist** keep the earlier rule, and the 14% one is nearest the plan of about 15%. But their answers bunch close to the 0.5 cut-off (most between 0.30 and 0.48), so a small wobble in Jev's answer flips a yes to a no, and they follow unusual volume only weakly.
- **Raising the cut-off** to about 0.72 under the old wording. A one-line setting, but tuned on a single day, and the spec leaves setting the cut-off from a sim's own records out of version 1.
- **The long checklist** said yes too rarely (4%).

The short checklist's answers follow how unusual the volume is far more closely than the old wording's (a match of 0.59 against 0.13, where 1 would be a perfect match), so it picks moments rather than saying no across the board.

## Consequences

- A one-day practice sim with the new wording (sim 102) said yes to 10 of 107 screens (9.3%), under the 30% at which the spec stops for the developer, and a little under the planned 15%.
- Jev's yes on the screen partly reflects the checklist, not only its own judgment. Every agent reads the same question, so the agents with and without memory still differ only by memory.
- The position screen (built later) is worded like the old screen and may say yes too often in the same way. Check it the same way when it is built.
