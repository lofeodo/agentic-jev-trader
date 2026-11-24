import type { SpendingTotal } from "./api/client";
import { dollarsAndCents, modelDollars } from "./format";

export type Screen = "sims" | "comparison" | "datasets" | "playbook" | "spending";

// The menu in the spec's order (appendix 7, section 4). A screen with no address is not built
// yet and is shown dimmed.
const SCREENS: { screen: Screen | null; title: string; href: string | null }[] = [
  { screen: "sims", title: "Trading sims", href: "#/" },
  { screen: "comparison", title: "Comparison", href: "#/comparison" },
  { screen: "datasets", title: "Datasets", href: "#/datasets" },
  { screen: "playbook", title: "Playbook", href: "#/playbook" },
  { screen: "spending", title: "Spending", href: "#/spending" },
];

// The command line under the menu: what to do on the screen.
const COMMANDS: Record<Screen, string> = {
  sims: "Read only: sims start from the command line",
  comparison: "Read only: did memory help, per market and per model",
  datasets: "Build a dataset with the form, or open one to follow its build",
  playbook: "Read only: the candle patterns the agent can spot",
  spending: "Read only: what the models have cost",
};

export function TopBar({ spending, screen }: { spending: SpendingTotal | null; screen: Screen }) {
  return (
    <header className="font-mono text-[13.5px] tracking-widest">
      <div className="flex flex-wrap items-stretch border-[1.5px] border-rule">
        <span className="border-r-[1.5px] border-rule px-[2ch] py-2">Jev/Trader</span>
        <nav className="mr-auto flex flex-wrap" aria-label="Screens">
          {SCREENS.map((s) =>
            s.href === null ? (
              <span
                key={s.title}
                title="Not built yet"
                className="border-r-[1.5px] border-rule px-[2ch] py-2 text-dim"
              >
                {s.title}
              </span>
            ) : (
              <a
                key={s.title}
                href={s.href}
                aria-current={s.screen === screen ? "page" : undefined}
                className={`border-r-[1.5px] border-rule px-[2ch] py-2 ${s.screen === screen ? "bg-amber text-screen" : "hover:text-pale"}`}
              >
                {s.title}
              </a>
            ),
          )}
        </nav>
        <a href="#/spending" className="self-center px-[2ch] py-2 text-dim hover:text-pale">
          Models:{" "}
          <b className="font-normal text-amber">
            {spending ? modelDollars(spending.spent_usd) : "..."}
          </b>
          {spending && ` of ${dollarsAndCents(spending.ceiling_usd)} spent`}
        </a>
      </div>
      <div className="mb-11 flex w-fit border-x-[1.5px] border-b-[1.5px] border-rule">
        <span className="border-r-[1.5px] border-rule px-[2ch] py-1.5 text-dim">Command:</span>
        <span className="py-1.5 pl-[2ch]">{COMMANDS[screen]}</span>
        <kbd className="px-[2ch] py-1.5 pl-[1ch] font-mono">&lt;GO&gt;</kbd>
      </div>
    </header>
  );
}
