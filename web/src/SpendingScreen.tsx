import { fetchSpending, type SpendingItem } from "./api/client";
import { dollarsAndCents, modelDollars } from "./format";
import { ErrorBox, KeyFigure } from "./pieces";
import { KINDS } from "./SimsScreen";
import { useRead } from "./useRead";

const GROUPS = [
  ...KINDS,
  { kind: "outside sims", title: "Outside sims", says: "The benchmark and saving answers for tests" },
];

const COLUMNS = ["Item", "Calls", "Jev", "LLM", "Total"];
const cell = "py-[.42rem] pr-[2ch] align-top font-mono text-base";
const number = `${cell} text-right whitespace-nowrap`;

function Line({ item }: { item: SpendingItem }) {
  return (
    <tr className="hover:bg-amber hover:text-screen [&:hover_*]:text-screen">
      <td className={cell}>
        {item.sim_id === null ? (
          item.name
        ) : (
          <a href={`#/sims/${item.sim_id}`} className="underline decoration-rule underline-offset-4">
            {item.name}
          </a>
        )}
      </td>
      <td className={number}>{item.calls}</td>
      <td className={number}>{modelDollars(item.jev_usd)}</td>
      <td className={number}>{modelDollars(item.llm_usd)}</td>
      <td className={`${number} text-pale`}>{modelDollars(item.total_usd)}</td>
    </tr>
  );
}

function Group({ n, title, says, items }: { n: number; title: string; says: string; items: SpendingItem[] }) {
  const total = items.reduce((sum, item) => sum + item.total_usd, 0);
  return (
    <tbody>
      <tr>
        <td colSpan={COLUMNS.length} className="pt-7 pb-2">
          <div className="flex items-stretch border-[1.5px] border-rule">
            <span className="border-r-[1.5px] border-rule px-[1.6ch] py-2 font-mono text-[15px]">
              {String(n).padStart(2, "0")}
            </span>
            <h2 className="flex flex-1 items-center gap-[2ch] px-[2ch] py-2 text-[1.15rem] tracking-[.14em] whitespace-nowrap after:flex-1 after:border-t-[1.5px] after:border-rule after:content-['']">
              {title}
            </h2>
            <span className="self-center pr-[2ch] font-mono text-[13.5px] tracking-wider whitespace-nowrap text-dim">
              {says && `${says} / `}
              {modelDollars(total)}
            </span>
          </div>
        </td>
      </tr>
      {items.map((item) => (
        <Line key={`${item.sim_id}-${item.name}`} item={item} />
      ))}
    </tbody>
  );
}

export function SpendingScreen() {
  const { data: spending, error } = useRead(fetchSpending);
  const items = spending?.items ?? [];
  const known = new Set(GROUPS.map((g) => g.kind));
  const groups = [
    ...GROUPS,
    // A kind the screen has no words for still shows, under its own name.
    ...[...new Set(items.map((i) => i.kind))]
      .filter((kind) => !known.has(kind))
      .map((kind) => ({ kind, title: kind, says: "" })),
  ]
    .map((group) => ({ ...group, items: items.filter((item) => item.kind === group.kind) }))
    .filter((group) => group.items.length > 0);
  const share = spending && spending.ceiling_usd > 0 ? spending.spent_usd / spending.ceiling_usd : 0;

  return (
    <section>
      <h1 className="mb-1 text-center text-[2.1rem] leading-tight tracking-[.02em]">Spending</h1>
      <p className="mb-6 text-center text-[1.1rem] text-dim">
        Real dollars paid to Jev and the LLM, against the project's ceiling
      </p>

      {error && (
        <div className="mb-6">
          <ErrorBox title="Cannot reach the API" text={`${error}. Asking again when you come back to this tab.`} />
        </div>
      )}
      {spending === null && !error && <p className="text-center font-mono text-dim">Loading...</p>}

      {spending !== null && (
        <>
          <div className="mb-3 grid grid-cols-2 gap-3 lg:grid-cols-4">
            <KeyFigure
              name="Spent"
              figure={modelDollars(spending.spent_usd)}
              says={`Of the ${dollarsAndCents(spending.ceiling_usd)} ceiling: ${share > 0 && share < 0.01 ? "under 1" : Math.round(share * 100)}% used`}
              first
            />
            <KeyFigure
              name="Left under the ceiling"
              figure={dollarsAndCents(spending.left_usd)}
              says="A sim whose cap could pass it is refused"
            />
            <KeyFigure name="Paid to Jev" figure={modelDollars(spending.jev_usd)} says="The decision model's answers" />
            <KeyFigure name="Paid to the LLM" figure={modelDollars(spending.llm_usd)} says="Picking past episodes from memory" />
          </div>
          <div
            className="mb-2 h-[6px] border border-rule"
            role="meter"
            aria-valuenow={Math.min(1, share)}
            aria-valuemin={0}
            aria-valuemax={1}
            aria-label="Spent against the ceiling"
          >
            <div className="h-full bg-amber" style={{ width: `${Math.min(1, share) * 100}%` }} />
          </div>
          <p className="mb-6 font-mono text-[13.5px] tracking-wider text-dim">
            The ceiling is the most the whole project may pay for model calls. Each sim also has its own
            cap, one and a half times its estimate: a sim estimated at $3.00 stops itself at $4.50. A new
            sim is refused if its cap, added to what is spent and to what running sims may still spend,
            would pass the ceiling.
          </p>

          {groups.length === 0 && (
            <div className="border-[1.5px] border-rule px-[2ch] py-10 text-center">
              <p className="text-[1.2rem] text-pale">Nothing paid yet</p>
              <p className="mt-1 text-dim">Each paid call to Jev or the LLM shows here, under its sim.</p>
            </div>
          )}

          {groups.length > 0 && (
            <div className="overflow-x-auto">
              <table className="w-full border-separate border-spacing-0">
                <thead>
                  <tr>
                    {COLUMNS.map((name, i) => (
                      <th
                        key={name}
                        scope="col"
                        className={`border-b border-rule py-[.4rem] pr-[2ch] font-mono text-[13.5px] font-light tracking-wider text-dim ${i === 0 ? "text-left" : "text-right"}`}
                      >
                        {name}
                      </th>
                    ))}
                  </tr>
                </thead>
                {groups.map((group, i) => (
                  <Group key={group.kind} n={i + 1} title={group.title} says={group.says} items={group.items} />
                ))}
              </table>
              <p className="mt-4 font-mono text-[13.5px] tracking-wider text-dim">
                Calls: how many times the model was asked, failed calls included (a failed call before it
                was priced counts $0).
              </p>
            </div>
          )}
        </>
      )}
    </section>
  );
}
