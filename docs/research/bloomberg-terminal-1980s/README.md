# What a 1980s Bloomberg terminal looked like on screen

Research for issue #75 (part of map #7). Researched 2026-11-19.

## Summary

The short, honest answer: **the web holds very little first-hand evidence of what the 1980s screen looked like.** No source I could open describes the 1982-89 screen's colours, character grid, layout or charts from direct observation, and I found no period screenshot or photograph of the screen itself. What can be sourced:

- The first terminal (the "Market Master", delivered December 1982) had a **monochrome CRT** (a single-colour tube; one colour of light on a dark background). Source: IEEE Spectrum.
- The first **colour** edition came in **1991** (Wikipedia; its own citation is missing, so this is weakly sourced). So every 1980s screen was one tube colour, not several.
- The famous **black background with amber/yellow/orange text** is documented for today's terminal (Bloomberg's own design team, Fast Company 2015). That the 1980s tube was amber is **plausible but not confirmed** by any primary source I could read.
- What is well documented is the **keyboard**: a red CANCEL key, a green GO key, and yellow market keys (EQUITY, GOVT, CORP and so on). Keys were colour-coded so people who had never used a computer could use it.
- One Bloomberg-published quote (seen only through a search summary, not opened) says the first graphic was a **monochrome yield curve, "just a simple line on the screen alongside text"**.

Conclusion for the prototype: do not claim a specific year's look as fact. The sourced facts are: one tube colour, text-first tables, keyboard colour-coding does the work colour later did on screen. Everything else below is marked as not confirmed.

Plain-language terms used here: a **CRT** is the glass-tube screen of old TVs and monitors. **Monochrome** means one colour of light on a dark background (like amber or green text on black). A **yield curve** is a line chart showing how much interest bonds of different lengths pay; a **bond** is a loan you buy that pays interest.

## 1. Colours

- **One tube colour.** IEEE Spectrum: the Market Master "consisted of a monochrome CRT monitor, a custom keyboard, and a communications/controller unit". It does not name the colour. The first colour edition is dated 1991 by Wikipedia (uncited there) and by a Businessweek-derived timeline relayed by a search summary (not opened). Source quality: medium.
- **Amber on black** is the documented default of the modern terminal: Fast Company (McCracken, 2015) says "amber characters on a black background, a color scheme that was commonplace in the early days of computing". Bloomberg's own Tech blog calls black-and-amber its strongest brand hallmark (seen via a search summary; the page returned 403 to me).
- A blog (ted-merz.com, 2021, no source cited) claims the look began because colour monitors were rare in the 1980s and most screens were orange or green on black. Weak source; consistent with general history.
- Second/third colour and their jobs: **nothing confirmed for the 1980s.** Descriptions of "yellow, orange, amber text" or colour-coded fields (prices, headlines, alerts) come from Interface Lineage and apply to the modern terminal; the page itself does not date them to 1982.
- Real colour in 1982-89 was on the **keys**, not the screen (see point 3).

## 2. The letters

- Capitals only vs mixed case: **not confirmed.** No source states it.
- Characters per line and lines per screen: **not confirmed.** The one hardware fact is that the 1982 keyboard replaced the IBM PC's ESC and ENTER keys with CANCEL and GO (Interface Lineage, citing Bloomberg's 1997 autobiography), which hints that early terminals were built from IBM PC-class parts. This is a hint only; it is not a confirmed screen size (an IBM PC text screen is 80 x 25, but I found no source tying that to Bloomberg).
- Openly licensed typefaces that look like period terminal text. **Licences below are from my own knowledge, not re-checked against each project's page this session; verify before shipping.**
  - VT323 (a copy of the DEC VT320 look): SIL Open Font Licence 1.1.
  - Terminus: SIL OFL 1.1.
  - Px437 / "Ultimate Oldschool PC Font Pack" by VileR (IBM PC screen fonts): CC BY-SA 4.0.
  - IBM Plex Mono (not period, but readable all day): SIL OFL 1.1.
  Since the real font is unknown, none can be called "closest"; the earlier rejected prototypes already used some of these looks.

## 3. Page layout

- **Not confirmed** for the screen: where the title, command line and page number sat, how price columns were aligned, how function names were written.
- What is sourced: data was "presented mostly in tabular form" (IEEE Spectrum, about the terminal generally). Commands are typed with a market key then GO, for example `IBM US <EQUITY> <GO>` (Interface Lineage; Bloomberg's later documentation). Writing function names inside angle brackets such as `<GO>` is the modern convention; whether the 1980s screens wrote them that way is unconfirmed.
- Keyboard (well sourced, Core77 and Interface Lineage): red CANCEL where ESC was, green GO where ENTER was, on opposite corners; yellow keys on the right for market sectors (EQUITY, GOVT, MUNI, MTGE, CORP, INDEX, CMDTY, CRNCY). Bloomberg's own history dates the hand-assembled "Chiclet" keyboard to about 1983, so the 1982 first units may have had something else.

## 4. Emphasis

**Not confirmed** for the 1980s: no source describes reverse video (dark text on a lit block), brightness levels, blinking, or underline. Do not assume them.

## 5. Charts

- One lead: a Bloomberg-published account quotes an early developer: "The first graphical function was a monochrome yield curve; just a simple line on the screen alongside text." I saw this only through a search-result summary; I could not open the Bloomberg page (403) or find the exact article and date, so treat as **unverified**.
- At launch the terminal offered only US government bond prices and bond-calculation tools (IEEE Spectrum), so a price chart of a stock was not part of the first product. Interface Lineage mentions a video of Michael Bloomberg demonstrating graphs but gives no date.
- How lines were drawn (text characters vs pixels): **not confirmed.**

## 6. How it changed, 1982 to 1989

Sourced milestones (IEEE Spectrum, Bloomberg's keyboard history, Wikipedia):

- 1981: company founded as Innovative Market Systems.
- Dec 1982: first Market Master terminals delivered to Merrill Lynch (sources say 20 or 22 units). Merrill paid $30 million for 30 percent and five years of exclusive rights.
- About 1983: "Chiclet" colour-coded keyboard.
- 1984: Merrill waives exclusivity.
- About 1987: renamed Bloomberg and the product became "the Bloomberg Terminal" (IEEE Spectrum says five years after launch; Wikipedia-derived text says 1986. Sources disagree).
- 1989 or 1990: keyboard redesigned with a trackball (Core77 says 1989; Bloomberg and IEEE say 1990).
- 1991: first colour edition (Wikipedia).
- Late 1980s: one summary says the terminal was ported to ordinary PC hardware; unverified.

How the **screen** changed across the decade: **not confirmed**. The only inference is: every 1980s screen was single-colour; colour arrived in 1991. A prototype should pick the mid/late 1980s (single colour, text tables, keyboard does the colour-coding) but cannot be checked against sourced screens.

## 7. Photographs and screen captures

I found **no verified period (1982-89) photograph or capture of the screen.** Candidates, each with what I could and could not confirm:

1. **Vintage Bloomberg terminal, Museum of the City of New York.** Wikimedia Commons, photo by Paul Lowry, taken 17 August 2025, licence CC BY 4.0. File page: https://commons.wikimedia.org/wiki/File:Vintage_Bloomberg_terminal_at_the_Museum_of_the_City_of_New_York.jpg (categories: Bloomberg Terminal, Keyboard trays). It is a modern photo of a museum exhibit, not a period capture. I could not download or view the image (Wikimedia blocked my fetch) and the page does not describe the screen, so I cannot say what colours or text it shows. The developer should open it; it is the most promising lead for a real surviving machine.
2. **Chiclet keyboard, about 1983.** National Museum of American History (Smithsonian), reproduced in the IEEE Spectrum article (https://spectrum.ieee.org/bloomberg-terminal). Caption: introduced around 1983; a mostly black keyboard with red, yellow and green keys; the function keys are finance-specific hot keys. Keyboard only, no screen.
3. **Early 1990s keyboard with trackball** and **Bill Gross's keyboard** (1990s-2000s), same IEEE article, Smithsonian credit. Not 1980s.
4. **Tietokonemuseo (Finnish computer museum) listing "Bloomberg display and keyboard".** https://www.tietokonemuseo.net/?p=1717, image https://www.tietokonemuseo.net/wp-content/uploads/2012/07/bloomberg2.jpg (upload path suggests July 2012). No date, caption or description for the unit; I could not view the image. Era unknown.
5. **Computer History Museum** holds a Bloomberg Terminal (Wikipedia infobox image "Bloomberg Terminal Museum.jpg", a two-monitor setup with a custom keyboard); the machine's age is not stated and looks late (two monitors). I did not find a CHM catalogue entry for a 1980s unit. The CHM item 102756299 turned up in search is DEC terminals from 1980-81, unrelated to Bloomberg.
6. Video: Interface Lineage embeds a *60 Minutes Overtime* clip of Michael Bloomberg demoing graphs (https://www.youtube.com/watch?v=BkH03iqDOU8, date not given, era unknown).

Suggested next steps to get real references: view the Commons photo above; search the Internet Archive for Bloomberg print advertisements and *Bloomberg by Bloomberg* (1997); try Wall Street Journal and New York Times archives (1983-89); ask Bloomberg's corporate archive or the Computer History Museum.

## What made the screens readable all day

**Not confirmed** by any source for the 1980s terminal. The only related statements are about today's terminal: amber on black is called "easy on the eyes" (Fast Company, 2015, still in the context of the modern default) and one summary of a general article says the yellow-on-black scheme was chosen for clarity and reduced eye strain (Tietokonemuseo's general text; no source). A critic (UX Magazine, Dominique Leca, 2010) calls the interface cluttered.

## Not confirmed

- The 1982-89 screen colour (amber, green or white).
- Whether text was capitals only; the screen's character grid.
- Placement of title, command line and page number; column alignment; how function names were printed.
- Any use of reverse video, brightness, blinking or underline.
- How charts were drawn; the exact origin and date of the "monochrome yield curve" quote.
- How the screen changed between 1982 and 1989.
- Any period photograph or screen capture of the screen. No primary source (Smithsonian, Computer History Museum, period press) was found showing it.
- Typeface licences (stated from memory).
- Sources I could not open: bloomberg.com pages (403), Fast Company (403), Boing Boing (403), and one Internet Archive and one site my environment refused. Some points above come via search-result summaries and are flagged.

## Sources

- IEEE Spectrum, "A Brief History of the Bloomberg Terminal" (Allison Marsh): https://spectrum.ieee.org/bloomberg-terminal (read in full by fetch)
- Fast Company, "How the Bloomberg Terminal Made History and Stays Ever Relevant" (Harry McCracken, 2015): https://www.fastcompany.com/3051883/the-bloomberg-terminal (via search summaries only)
- Bloomberg, "Innovating a modern icon" (source of the yield-curve quote, via summary only): https://www.bloomberg.com/company/stories/innovating-a-modern-icon-how-bloomberg-keeps-the-terminal-cutting-edge/
- Bloomberg, "A look back: The Bloomberg Keyboard" (keyboard dates, via summary): https://www.bloomberg.com/professional/blog/look-back-bloomberg-keyboard
- Wikipedia, Bloomberg Terminal: https://en.wikipedia.org/wiki/Bloomberg_Terminal
- Interface Lineage, Bloomberg Terminal 1982: https://interfacelineage.com/bloomberg-terminal-1982
- Core77, "Bloomberg is a Billionaire Because He Backed Good Design": https://www.core77.com/posts/91421/Bloomberg-is-a-Billionaire-Because-He-Backed-Good-Design
- Ted Merz, "Amber on Black" (2021, opinion): https://ted-merz.com/2021/06/26/amber-on-black/
- Wikimedia Commons file page (photo, 2025): https://commons.wikimedia.org/wiki/File:Vintage_Bloomberg_terminal_at_the_Museum_of_the_City_of_New_York.jpg
- Tietokonemuseo listing: https://www.tietokonemuseo.net/?p=1717
- Computer History Museum catalogue 102756299 (checked; unrelated DEC photos): https://www.computerhistory.org/collections/catalog/102756299
- Michael R. Bloomberg, *Bloomberg by Bloomberg* (1997): not opened; cited by Interface Lineage and Wikipedia.
