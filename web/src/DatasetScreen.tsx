// The Dataset screen (spec appendix 7, section 9): build stage and progress with a Stop button,
// the check's numbers per asset and its verdict, a price chart per asset, the quality report
// and the asset key. Asked again every 2 seconds while the build runs; once otherwise.
import { useCallback, useState } from "react";

import {
  type DatasetPage,
  fetchDataset,
  fetchDatasetBars,
  type PriceChart as Chart,
  stopDataset,
} from "./api/client";
import { checkSummary, percent } from "./datasetWords";
import { dayAndTime, day, fromApi } from "./format";
import { AssetTag, ErrorBox, Pair, SectionHeading } from "./pieces";
import { PriceChart } from "./PriceChart";
import { usePoll } from "./usePoll";
import { useRead } from "./useRead";

const BUILD_REFRESH_MS = 2_000;
const th = "border-b border-rule py-[.4rem] pr-[2ch] text-left font-mono text-[13.5px] font-light tracking-wider text-dim";
const thNumber = th.replace("text-left", "text-right");
const td = "py-[.42rem] pr-[2ch] align-top";
const tdNumber = `${td} text-right font-mono`;
const row = "hover:bg-amber hover:text-screen [&:hover_*]:text-screen";
// Missing bars can run to thousands: the first ones show, the rest on request.
const MISSING_SHOWN = 40;

export function DatasetScreen({ id }: { id: number }) {
  const read = useCallback(() => fetchDataset(id), [id]);
  const { data: dataset, error, reload } = usePoll(read, BUILD_REFRESH_MS, (d) => d.status === "being built");

  return (
    <section>
      <a href="#/datasets" className="mb-4 inline-block font-mono text-[13.5px] tracking-wider text-dim hover:text-amber">
        &lt; Datasets
      </a>
      {error && <ErrorBox title="Cannot reach the API" text={`${error}. Asking again when you come back to this tab.`} />}
      {dataset === null && !error && <p className="text-center font-mono text-dim">Loading...</p>}
      {dataset !== null && <Dataset dataset={dataset} onStopped={reload} />}
    </section>
  );
}

function Dataset({ dataset: d, onStopped }: { dataset: DatasetPage; onStopped: () => void }) {
  const building = d.status === "being built";
  let n = 0;
  return (
    <>
      <h1 className="mb-1 text-center text-[2.1rem] leading-tight tracking-[.02em]">
        {d.tickers.length > 0 ? d.tickers.join(" ") : d.name}
      </h1>
      <p className="mb-5 text-center text-[1.1rem] text-dim">
        Dataset {d.id}, version {d.version}
        {d.first_day && d.last_day && `: ${day(d.first_day)} to ${day(d.last_day)}`}
      </p>
      <div className="mb-8 flex flex-wrap justify-center gap-3 font-mono text-[13.5px] tracking-wider">
        <Pair name="Status" value={d.published_without_check ? "published without the check" : d.status} />
        <Pair name="Assets" value={String(d.tickers.length || d.check?.assets.length || "--")} />
        {d.started_at && <Pair name="Started" value={dayAndTime(fromApi(d.started_at))} />}
        {d.published_at && <Pair name="Published" value={dayAndTime(fromApi(d.published_at))} />}
      </div>

      {building && <Progress dataset={d} onStopped={onStopped} />}
      {d.status === "failed" && (
        <div className="mb-8">
          <ErrorBox
            title="The build failed and was thrown away"
            text={
              (d.failure_reason ?? "No reason was stored.") +
              (d.check && !d.check.passed
                ? ' From this app, "build with the check off" means unticking the check box on the Datasets form.'
                : "")
            }
          />
        </div>
      )}
      {d.published_without_check && (
        <div className="mb-8">
          <ErrorBox
            title="Published without the check"
            text={`The limits were not enforced: ${checkSummary(d.check).toLowerCase()}. The numbers are below.`}
          />
        </div>
      )}

      <div className="mt-2 mb-10">
        <SectionHeading number={++n} title="The check" says={checkSummary(d.check)} />
        <CheckTable dataset={d} />
      </div>

      {d.asset_key.length > 0 && (
        <div className="mb-10">
          <SectionHeading number={++n} title="Prices" says="Each day's close, real dollars" />
          <div className="grid gap-6">
            {d.asset_key.map((k) => (
              <AssetChart key={k.masked_id} datasetId={d.id} asset={k.masked_id} />
            ))}
          </div>
        </div>
      )}

      {d.status === "published" && (
        <div className="mb-10">
          <SectionHeading
            number={++n}
            title="Quality report"
            says={`${d.partial_volume_days.length} partial-volume days, ${d.missing_bars.length} missing bars`}
          />
          <QualityReport dataset={d} />
        </div>
      )}

      {(d.asset_key.length > 0 || d.periods.length > 0) && (
        <div className="mb-10">
          <SectionHeading number={++n} title="Asset key and days" says="Only the API can read this key" />
          <AssetKey dataset={d} />
        </div>
      )}
    </>
  );
}

function Progress({ dataset: d, onStopped }: { dataset: DatasetPage; onStopped: () => void }) {
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const share = Math.max(0, Math.min(1, d.progress ?? 0));

  async function stop() {
    if (!window.confirm("Stop this build now? It is marked failed, stopped by hand, and thrown away.")) return;
    setBusy(true);
    setProblem(null);
    try {
      await stopDataset(d.id);
      onStopped();
    } catch (error) {
      setProblem(error instanceof Error ? error.message : String(error));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mb-10 border-[1.5px] border-rule px-[2ch] py-4">
      <div className="mb-2 flex flex-wrap items-baseline justify-between gap-3 font-mono">
        <span>
          <span className="text-pale">{d.stage ?? "Starting"}</span>{" "}
          <span className="text-dim">{percent(share)}</span>
        </span>
        <button
          type="button"
          className="cursor-pointer border-[1.5px] border-amber px-[1.5ch] py-1 text-amber uppercase hover:bg-amber hover:text-screen disabled:cursor-wait disabled:opacity-60"
          disabled={busy}
          onClick={() => void stop()}
        >
          {busy ? "Stopping..." : "Stop"}
        </button>
      </div>
      <div
        className="h-5 border-[1.5px] border-rule"
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={Math.round(share * 100)}
        aria-label="Build progress"
      >
        <div className="h-full bg-amber" style={{ width: `${share * 100}%` }} />
      </div>
      <ol className="mt-3 flex flex-wrap gap-x-[3ch] gap-y-1 font-mono text-[12.5px] tracking-wider text-dim">
        {d.stages.map((s, i) => (
          <li key={s.name} className={s.name === d.stage ? "text-pale" : ""}>
            {i + 1}. {s.name} ({percent(s.starts_at)})
          </li>
        ))}
      </ol>
      <p className="mt-2 text-[15px] text-dim">
        Each stage has a fixed share of the bar, set from timing the first build. The check against
        the two limits is the first stage.
      </p>
      {problem && (
        <p role="alert" className="mt-2 text-amber">
          Refused: {problem}
        </p>
      )}
    </div>
  );
}

function CheckTable({ dataset: d }: { dataset: DatasetPage }) {
  const check = d.check;
  if (check === null) {
    return <p className="font-mono text-dim">The check is the build's first stage: its numbers show here once it is done.</p>;
  }
  return (
    <>
      <div className="overflow-x-auto">
        <table className="w-full border-separate border-spacing-0">
          <thead>
            <tr>
              <th scope="col" className={th}>Asset</th>
              <th scope="col" className={thNumber}>Partial-volume days</th>
              <th scope="col" className={thNumber}>Bars missing for other reasons</th>
              <th scope="col" className={th}>Verdict</th>
            </tr>
          </thead>
          <tbody>
            {check.assets.map((a) => (
              <tr key={a.asset.masked_id} className={row}>
                <td className={td}>
                  <AssetTag asset={a.asset} />
                </td>
                <td className={tdNumber}>
                  {a.partial_volume_share === null ? (
                    <span className="text-dim">none: crypto</span>
                  ) : (
                    <>
                      {percent(a.partial_volume_share)}{" "}
                      <span className="text-dim">of {percent(check.limit_partial_volume_days)}</span>
                    </>
                  )}
                </td>
                <td className={tdNumber}>
                  {percent(a.other_missing_share)} <span className="text-dim">of {percent(check.limit_other_missing)}</span>
                </td>
                <td className={`${td} font-mono`}>{a.over.length === 0 ? "inside both limits" : `over: ${a.over.join(", ")}`}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="mt-3 font-mono text-[13.5px] tracking-wider text-dim">
        Partial-volume days: the share of a stock's trading days its data provider carried only part
        of; 1.9% of 899 days is 17 days. Crypto trades all day every day and has no such days. Bars
        missing for other reasons: the share of an asset's 15-minute bars the provider never sent.
      </p>
    </>
  );
}

function AssetChart({ datasetId, asset }: { datasetId: number; asset: string }) {
  const read = useCallback(() => fetchDatasetBars(datasetId, asset), [datasetId, asset]);
  const { data, error } = useRead<Chart>(read);
  if (error) return <ErrorBox title={`No chart for ${asset}`} text={error} />;
  if (data === null) return <p className="font-mono text-dim">Loading {asset}...</p>;
  return (
    <div>
      <div className="mb-1 font-mono">
        <AssetTag asset={data.asset} />
      </div>
      <PriceChart chart={data} />
    </div>
  );
}

function QualityReport({ dataset: d }: { dataset: DatasetPage }) {
  const [all, setAll] = useState(false);
  const missing = all ? d.missing_bars : d.missing_bars.slice(0, MISSING_SHOWN);
  return (
    <>
      <p className="mb-4 text-[15px] text-dim">
        No bar is ever invented to fill a gap: a missing bar is simply not there, and the agent sees
        the gap. Every bar of a partial-volume day counts as missing.
      </p>
      <h3 className="mb-2 font-mono tracking-wider text-pale">Partial-volume days</h3>
      {d.partial_volume_days.length === 0 ? (
        <p className="mb-6 font-mono text-dim">None.</p>
      ) : (
        <div className="mb-8 overflow-x-auto">
          <table className="w-full border-separate border-spacing-0">
            <thead>
              <tr>
                <th scope="col" className={th}>Stock</th>
                <th scope="col" className={th}>Day</th>
                <th scope="col" className={th}>Caught by</th>
                <th scope="col" className={thNumber}>Trading against usual</th>
              </tr>
            </thead>
            <tbody>
              {d.partial_volume_days.map((p) => (
                <tr key={`${p.asset.masked_id}-${p.day}`} className={row}>
                  <td className={td}>
                    <AssetTag asset={p.asset} />
                  </td>
                  <td className={`${td} font-mono`}>{p.day ? day(p.day) : "--"}</td>
                  <td className={td}>{p.test}</td>
                  <td className={tdNumber}>{p.share_of_usual === null ? "--" : percent(p.share_of_usual)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <h3 className="mb-2 font-mono tracking-wider text-pale">Missing bars</h3>
      {d.missing_bars.length === 0 ? (
        <p className="font-mono text-dim">None.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full border-separate border-spacing-0">
            <thead>
              <tr>
                <th scope="col" className={th}>Asset</th>
                <th scope="col" className={th}>Bar ending</th>
                <th scope="col" className={th}>Why</th>
              </tr>
            </thead>
            <tbody>
              {missing.map((m) => (
                <tr key={`${m.asset.masked_id}-${m.step}`} className={row}>
                  <td className={td}>
                    <AssetTag asset={m.asset} />
                  </td>
                  <td className={`${td} font-mono`}>
                    {m.ends_at ? dayAndTime(fromApi(m.ends_at)) : "--"}{" "}
                    <span className="text-[12.5px] text-dim">step {m.step}</span>
                  </td>
                  <td className={td}>{m.reason}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {d.missing_bars.length > MISSING_SHOWN && (
            <button type="button" className="mt-3 cursor-pointer font-mono text-dim uppercase underline hover:text-amber" onClick={() => setAll(!all)}>
              {all ? `Show the first ${MISSING_SHOWN}` : `Show all ${d.missing_bars.length}`}
            </button>
          )}
        </div>
      )}
    </>
  );
}

function AssetKey({ dataset: d }: { dataset: DatasetPage }) {
  return (
    <>
      <p className="mb-4 text-[15px] text-dim">
        The agent never sees a real name, price or date. Each asset gets a made-up name (its masked
        ID), and its prices are rescaled so the first one is 100: a stock first at $50 shows $60 as
        120. The price scale turns a rescaled price back: real price = rescaled price / scale.
      </p>
      {d.asset_key.length > 0 && (
        <div className="mb-6 overflow-x-auto">
          <table className="w-full border-separate border-spacing-0">
            <thead>
              <tr>
                <th scope="col" className={th}>Masked ID</th>
                <th scope="col" className={th}>Ticker</th>
                <th scope="col" className={th}>Name</th>
                <th scope="col" className={th}>Kind</th>
                <th scope="col" className={th}>Downloaded as</th>
                <th scope="col" className={thNumber}>Price scale</th>
              </tr>
            </thead>
            <tbody>
              {d.asset_key.map((k) => (
                <tr key={k.masked_id} className={row}>
                  <td className={`${td} font-mono`}>{k.masked_id}</td>
                  <td className={`${td} font-mono text-pale`}>{k.ticker}</td>
                  <td className={td}>{k.name}</td>
                  <td className={td}>{k.asset_class}</td>
                  <td className={`${td} font-mono`}>{k.provider_symbol}</td>
                  <td className={tdNumber}>{k.price_scale.toPrecision(5)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {d.periods.length > 0 && (
        <table className="border-separate border-spacing-0">
          <thead>
            <tr>
              <th scope="col" className={th}>Period</th>
              <th scope="col" className={th}>Days</th>
            </tr>
          </thead>
          <tbody>
            {d.periods.map((p) => (
              <tr key={p.name} className={row}>
                <td className={td}>
                  {p.name} <span className="text-[12.5px] text-dim">{p.kind === "test" ? "test period" : "no sim trades it"}</span>
                </td>
                <td className={`${td} font-mono`}>
                  {p.first_day && p.last_day ? `${day(p.first_day)} to ${day(p.last_day)}` : "--"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </>
  );
}
