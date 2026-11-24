// The Datasets screen (spec appendix 7, section 9): the form that builds a dataset, and the list
// of datasets with their status and quality summary.
import { useState } from "react";

import { buildDataset, type DatasetLine, fetchDatasets, RefusedError } from "./api/client";
import { checkSummary, datasetStatus } from "./datasetWords";
import { day } from "./format";
import { ErrorBox, SectionHeading } from "./pieces";
import { usePoll } from "./usePoll";

const REFRESH_MS = 5_000;
const building = (d: DatasetLine) => d.status === "being built";

const th = "border-b border-rule py-[.4rem] pr-[2ch] text-left font-mono text-[13.5px] font-light tracking-wider text-dim";
const td = "py-[.42rem] pr-[2ch] align-top";
const field = "bg-amber px-[1ch] py-1 font-mono text-screen placeholder:text-screen/60";
const label = "font-mono text-[13.5px] tracking-wider text-dim";
const button =
  "cursor-pointer border-[1.5px] border-amber px-[2ch] py-1.5 font-mono tracking-widest text-amber uppercase hover:bg-amber hover:text-screen disabled:cursor-wait disabled:opacity-60";

export function DatasetsScreen() {
  const { data, error } = usePoll(fetchDatasets, REFRESH_MS, (list) => list.datasets.some(building));

  return (
    <section>
      <h1 className="mb-1 text-center text-[2.1rem] leading-tight tracking-[.02em]">Datasets</h1>
      <p className="mb-8 text-center text-[1.1rem] text-dim">
        The market days a sim replays: build one, then read how clean its data is
      </p>

      <SectionHeading number={1} title="Build a dataset" says="Downloads are free; the build takes about 25 minutes" />
      <BuildForm busy={data?.datasets.some(building) ?? false} />

      <div className="mt-10">
        <SectionHeading number={2} title="Datasets" says="Newest first" />
      </div>
      {error && <ErrorBox title="Cannot reach the API" text={`${error}. Asking again when you come back to this tab.`} />}
      {data === null && !error && <p className="text-center font-mono text-dim">Loading...</p>}
      {data !== null && data.datasets.length === 0 && (
        <div className="border-[1.5px] border-rule px-[2ch] py-10 text-center">
          <p className="text-[1.2rem] text-pale">No datasets yet</p>
          <p className="mt-1 text-dim">Build the first one with the form above.</p>
        </div>
      )}
      {data !== null && data.datasets.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full border-separate border-spacing-0">
            <thead>
              <tr>
                <th scope="col" className={th}>Dataset</th>
                <th scope="col" className={th}>Status</th>
                <th scope="col" className={th}>Days</th>
                <th scope="col" className={th}>Quality</th>
              </tr>
            </thead>
            <tbody>
              {data.datasets.map((d) => (
                <tr
                  key={d.id}
                  className="cursor-pointer hover:bg-amber hover:text-screen [&:hover_*]:text-screen"
                  onClick={() => (window.location.hash = `#/datasets/${d.id}`)}
                >
                  <td className={`${td} font-mono`}>
                    <a href={`#/datasets/${d.id}`} className="text-pale">
                      {d.tickers.length > 0 ? d.tickers.join(" ") : d.name}
                    </a>
                    <div className="text-[12.5px] tracking-wider text-dim">
                      ID {d.id}, version {d.version}
                    </div>
                  </td>
                  <td className={`${td} font-mono`}>{datasetStatus(d)}</td>
                  <td className={`${td} font-mono whitespace-nowrap`}>
                    {d.first_day && d.last_day ? `${day(d.first_day)} to ${day(d.last_day)}` : "--"}
                  </td>
                  <td className={td}>{checkSummary(d.check)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

type Period = { first: string; last: string };

function BuildForm({ busy }: { busy: boolean }) {
  const [tickers, setTickers] = useState("");
  const [firstDay, setFirstDay] = useState("");
  const [lastDay, setLastDay] = useState("");
  const [partialLimit, setPartialLimit] = useState("3");
  const [otherLimit, setOtherLimit] = useState("0.5");
  const [falling, setFalling] = useState<Period>({ first: "", last: "" });
  const [rising, setRising] = useState<Period>({ first: "", last: "" });
  const [check, setCheck] = useState(true);
  const [sending, setSending] = useState(false);
  const [problems, setProblems] = useState<string[]>([]);

  async function send(event: React.FormEvent) {
    event.preventDefault();
    const periods = [
      { name: "falling market", ...falling },
      { name: "rising market", ...rising },
    ].filter((p) => p.first || p.last);
    const halfGiven = periods.find((p) => !p.first || !p.last);
    if (!firstDay || !lastDay) return setProblems(["Give the first and the last day."]);
    if (halfGiven) return setProblems([`Give both days of the ${halfGiven.name} test period, or neither.`]);
    setSending(true);
    setProblems([]);
    try {
      const started = await buildDataset({
        tickers: tickers.split(/[\s,]+/).filter(Boolean),
        first_day: firstDay,
        last_day: lastDay,
        test_periods: periods.map((p) => ({ name: p.name, first_day: p.first, last_day: p.last })),
        limit_partial_volume_days: Number(partialLimit) / 100,
        limit_other_missing: Number(otherLimit) / 100,
        check,
      });
      window.location.hash = `#/datasets/${started.dataset_id}`;
    } catch (error) {
      setProblems(error instanceof RefusedError ? error.refusals.map((r) => r.message) : [String(error)]);
    } finally {
      setSending(false);
    }
  }

  return (
    <form onSubmit={(e) => void send(e)} className="grid gap-6 border-[1.5px] border-rule px-[2ch] py-5">
      <label className="grid gap-1">
        <span className={label}>Tickers</span>
        <input
          className={field}
          value={tickers}
          onChange={(e) => setTickers(e.target.value)}
          placeholder="SPY AAPL JPM XOM BTC"
          aria-describedby="tickers-says"
        />
        <span id="tickers-says" className="text-[15px] text-dim">
          A ticker is the short code an asset trades under, such as AAPL for Apple. Separate them with
          spaces. BTC (Bitcoin) and ETH (Ether) are crypto, downloaded from Binance; every other ticker
          is a stock or fund, downloaded from Twelve Data. The build's check says if one does not exist.
        </span>
      </label>

      <div className="flex flex-wrap gap-6">
        <label className="grid gap-1">
          <span className={label}>First day</span>
          <input type="date" className={field} value={firstDay} onChange={(e) => setFirstDay(e.target.value)} />
        </label>
        <label className="grid gap-1">
          <span className={label}>Last day</span>
          <input type="date" className={field} value={lastDay} onChange={(e) => setLastDay(e.target.value)} />
        </label>
        <p className="max-w-[60ch] self-end text-[15px] text-dim">
          The first three months are the warm-up: no sim trades them; they only set what "usual"
          looks like for each measurement. The last day must be before today.
        </p>
      </div>

      <fieldset className="grid gap-3">
        <legend className={`${label} mb-1`}>The two quality limits</legend>
        <div className="flex flex-wrap gap-6">
          <label className="grid gap-1">
            <span className={label}>Partial-volume days per stock, %</span>
            <input type="number" min="0" max="100" step="0.1" className={`${field} w-[12ch]`} value={partialLimit} onChange={(e) => setPartialLimit(e.target.value)} />
          </label>
          <label className="grid gap-1">
            <span className={label}>Bars missing for other reasons, %</span>
            <input type="number" min="0" max="100" step="0.1" className={`${field} w-[12ch]`} value={otherLimit} onChange={(e) => setOtherLimit(e.target.value)} />
          </label>
        </div>
        <p className="text-[15px] text-dim">
          A bar is 15 minutes of trading. A partial-volume day is a day on which the data provider's
          bars for a stock carry only part of the market's trading (a bar with no trades at all, or the
          day's trading under a quarter of usual); the whole day is left out. 3% is about 7 days a
          year. Bars missing for other reasons are bars the provider never sent, or Bitcoin bars with no
          trades.
        </p>
      </fieldset>

      <fieldset className="grid gap-3">
        <legend className={`${label} mb-1`}>Test period (optional)</legend>
        <p className="text-[15px] text-dim">
          Days kept for the measurement sims only. Naming them here lets code refuse a free sim or a
          tuning sim on those days, so the agent is never tuned on the days it is judged on.
        </p>
        <PeriodFields name="Falling market" period={falling} onChange={setFalling} />
        <PeriodFields name="Rising market" period={rising} onChange={setRising} />
      </fieldset>

      <label className="flex items-start gap-3">
        <input type="checkbox" className="mt-1.5 size-4 accent-amber" checked={check} onChange={(e) => setCheck(e.target.checked)} />
        <span>
          <span className="font-mono tracking-wider">Check the data against the two limits first</span>
          <span className="block text-[15px] text-dim">
            The check is the build's first step, before the slow part: if an asset is over a limit the
            build stops there and says which. Unticked, the build publishes whatever the numbers are,
            and the dataset is marked "published without the check".
          </span>
        </span>
      </label>

      <div className="flex flex-wrap items-center gap-4">
        <button type="submit" className={button} disabled={sending || busy}>
          {sending ? "Starting..." : "Build the dataset"}
        </button>
        {busy && <span className="text-dim">A dataset is being built: one build at a time.</span>}
      </div>
      {problems.length > 0 && <ErrorBox title="Refused" text={problems.join(" ")} />}
    </form>
  );
}

function PeriodFields({ name, period, onChange }: { name: string; period: Period; onChange: (p: Period) => void }) {
  return (
    <div className="flex flex-wrap items-end gap-6">
      <span className="w-[16ch] pb-1 font-mono">{name}</span>
      <label className="grid gap-1">
        <span className={label}>First day</span>
        <input type="date" className={field} value={period.first} onChange={(e) => onChange({ ...period, first: e.target.value })} />
      </label>
      <label className="grid gap-1">
        <span className={label}>Last day</span>
        <input type="date" className={field} value={period.last} onChange={(e) => onChange({ ...period, last: e.target.value })} />
      </label>
    </div>
  );
}
