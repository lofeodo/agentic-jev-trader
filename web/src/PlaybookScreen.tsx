import { fetchPlaybook } from "./api/client";
import { ErrorBox, Pair } from "./pieces";
import { useRead } from "./useRead";

const LEANS: { lean: string; says: string }[] = [
  { lean: "bullish", says: "bets the price rises" },
  { lean: "bearish", says: "bets the price falls" },
  { lean: "neutral", says: "no bet either way" },
];

const th = "border-b border-rule py-[.4rem] pr-[2ch] text-left font-mono text-[13.5px] font-light tracking-wider text-dim";
const td = "py-[.42rem] pr-[2ch] align-top";

export function PlaybookScreen() {
  const { data: playbook, error } = useRead(fetchPlaybook);
  const count = (lean: string) => playbook?.patterns.filter((p) => p.lean === lean).length ?? 0;

  return (
    <section>
      <h1 className="mb-1 text-center text-[2.1rem] leading-tight tracking-[.02em]">Playbook</h1>
      <p className="mb-6 text-center text-[1.1rem] text-dim">
        Every candle pattern the agent can spot, with its lean and its shape
      </p>

      {error && (
        <div className="mb-6">
          <ErrorBox title="Cannot reach the API" text={`${error}. Asking again when you come back to this tab.`} />
        </div>
      )}
      {playbook === null && !error && <p className="text-center font-mono text-dim">Loading...</p>}

      {playbook !== null && playbook.patterns.length === 0 && (
        <div className="border-[1.5px] border-rule px-[2ch] py-10 text-center">
          <p className="text-[1.2rem] text-pale">No playbook yet</p>
          <p className="mt-1 text-dim">The first dataset build stores it.</p>
        </div>
      )}

      {playbook !== null && playbook.patterns.length > 0 && (
        <>
          <div className="mb-4 flex flex-wrap justify-center gap-3 font-mono text-[13.5px] tracking-wider">
            <Pair name="Patterns" value={String(playbook.patterns.length)} />
            {LEANS.map(({ lean }) => (
              <Pair key={lean} name={lean} value={String(count(lean))} />
            ))}
            <Pair name="TA-Lib" value={playbook.talib_version ?? "--"} />
          </div>
          <p className="mb-6 font-mono text-[13.5px] tracking-wider text-dim">
            A candle (a bar) shows one stretch of trading: where the price opened, its high, its low and where it
            closed. A candle pattern is a shape the last few candles make, such as a big rising candle
            that swallows the falling one before it (bullish engulfing). The lean is what the pattern
            bets on: bullish, the price rises ($100 to $103); bearish, it falls; neutral, no bet. The
            shape is TA-Lib's own description: TA-Lib is the library that spots the patterns.
          </p>
          <div className="overflow-x-auto">
            <table className="w-full border-separate border-spacing-0">
              <thead>
                <tr>
                  <th scope="col" className={th}>Pattern</th>
                  <th scope="col" className={th}>Lean</th>
                  <th scope="col" className={`${th} w-full`}>Shape</th>
                </tr>
              </thead>
              <tbody>
                {playbook.patterns.map((p) => (
                  <tr key={`${p.detector}-${p.lean}`} className="hover:bg-amber hover:text-screen [&:hover_*]:text-screen">
                    <td className={`${td} min-w-[24ch] font-mono text-base text-pale`}>
                      {p.name}
                      <div className="text-[12.5px] tracking-wider text-dim">{p.detector}</div>
                    </td>
                    <td className={`${td} font-mono text-base whitespace-nowrap`}>
                      {p.lean}
                      <div className="text-[12.5px] tracking-wider text-dim">
                        {LEANS.find((l) => l.lean === p.lean)?.says}
                      </div>
                    </td>
                    <td className={`${td} text-[15px]`}>{p.shape}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </section>
  );
}
