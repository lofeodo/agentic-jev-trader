import type { SpendingTotal } from "./api/client";
import { dollarsAndCents } from "./format";

export type Screen = "sims" | "playbook" | "spending";

const SCREENS: { screen: Screen; title: string; href: string }[] = [
  { screen: "sims", title: "Trading sims", href: "#/" },
  { screen: "playbook", title: "Playbook", href: "#/playbook" },
  { screen: "spending", title: "Spending", href: "#/spending" },
];
// Shown dimmed until they are built.
const LATER_SCREENS = ["Comparison", "Datasets"];

export function TopBar({ spending, screen }: { spending: SpendingTotal | null; screen: Screen }) {
  return (
    <header className="font-mono text-[13.5px] tracking-widest">
      <div className="flex flex-wrap items-stretch border-[1.5px] border-rule">
        <span className="border-r-[1.5px] border-rule px-[2ch] py-2">Jev/Trader</span>
        <nav className="mr-auto flex flex-wrap" aria-label="Screens">
          {SCREENS.map((s) => (
            <a
              key={s.screen}
              href={s.href}
              aria-current={s.screen === screen ? "page" : undefined}
              className={`border-r-[1.5px] border-rule px-[2ch] py-2 ${s.screen === screen ? "bg-amber text-screen" : "hover:text-pale"}`}
            >
              {s.title}
            </a>
          ))}
          {LATER_SCREENS.map((later) => (
            <span
              key={later}
              title="Not built yet"
              className="border-r-[1.5px] border-rule px-[2ch] py-2 text-dim"
            >
              {later}
            </span>
          ))}
        </nav>
        <a href="#/spending" className="self-center px-[2ch] py-2 text-dim hover:text-pale">
          Models:{" "}
          <b className="font-normal text-amber">
            {spending ? dollarsAndCents(spending.spent_usd) : "..."}
          </b>
          {spending && ` of ${dollarsAndCents(spending.ceiling_usd)} spent`}
        </a>
      </div>
      <div className="mb-11 flex w-fit border-x-[1.5px] border-b-[1.5px] border-rule">
        <span className="border-r-[1.5px] border-rule px-[2ch] py-1.5 text-dim">Command:</span>
        <span className="py-1.5 pl-[2ch]">Read only: sims start from the command line</span>
        <kbd className="px-[2ch] py-1.5 pl-[1ch] font-mono">&lt;GO&gt;</kbd>
      </div>
    </header>
  );
}
