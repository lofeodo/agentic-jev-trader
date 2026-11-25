// The New trading sim form (spec appendix 7, section 8): the three kinds of sim the app starts,
// the days, memory, model, what the sim would cost, and why it may not start. Every change of
// choice asks the API again (`GET /sims/check`), which stores nothing; the start button starts
// the sim through `POST /sims` and opens its page.
import { type FormEvent, useEffect, useState } from "react";
import {
  checkSim,
  type DatasetLine,
  fetchDatasets,
  fetchModels,
  type Refusal,
  RefusedError,
  type SimCheck,
  type SimToStart,
  startSim,
} from "./api/client";
import { dollarsAndCents } from "./format";
import { ErrorBox, field, fieldLabel as label, formButton as button, SectionHeading } from "./pieces";
import { useRead } from "./useRead";

type Kind = "measurement" | "build-up" | "free";
type Variant = "memory_on" | "memory_off";

// The kinds the app starts, each with what it is for. Practice and tuning sims are command-line
// tools and never appear here.
const FORM_KINDS: { kind: Kind; title: string; says: string }[] = [
  {
    kind: "measurement",
    title: "Measurement",
    says:
      "The exam: 30 days of one test period the agent was never adjusted on, played with memory " +
      "and without, side by side. Only these results count.",
  },
  {
    kind: "build-up",
    title: "Build-up",
    says:
      "One year without memory, whose stored trades become the memory later sims start from. " +
      "Done once; never counts.",
  },
  {
    kind: "free",
    title: "Free sim",
    says: "Any days you choose, outside the test periods. Never counts.",
  },
];

const TEST_PERIODS = [
  { market: "falling market", title: "Falling market" },
  { market: "rising market", title: "Rising market" },
];

// The build-up sim's year (spec appendix 8, section 3), filled in when the developer picks it.
const BUILD_UP_YEAR = { first: "2024-03-10", last: "2025-03-09" };

// How long the form waits after a change before asking the API, so typing a date asks once.
const ASK_AFTER_MS = 300;

const VARIANT_WORDS: Record<Variant, string> = { memory_on: "with memory", memory_off: "without memory" };
const other = (variant: Variant): Variant => (variant === "memory_on" ? "memory_off" : "memory_on");

export function NewSimScreen() {
  const datasets = useRead(fetchDatasets);
  const choice = useRead(fetchModels);

  const [dataset, setDataset] = useState<number | null>(null);
  const [kind, setKind] = useState<Kind>("measurement");
  const [ownDates, setOwnDates] = useState(false);
  const [market, setMarket] = useState(TEST_PERIODS[0].market);
  const [firstDay, setFirstDay] = useState("");
  const [lastDay, setLastDay] = useState("");
  const [variant, setVariant] = useState<Variant>("memory_on");
  const [partner, setPartner] = useState(false);
  const [measured, setMeasured] = useState<string[] | null>(null); // a measurement's models
  const [freeModel, setFreeModel] = useState<string | null>(null); // a free sim's one model

  // Until the developer picks: the latest published dataset, both models for a measurement and
  // the default for a free sim.
  const published = (datasets.data?.datasets ?? []).filter((d) => d.status === "published");
  const datasetId = dataset ?? (published.length ? Math.max(...published.map((d) => d.id)) : null);
  const models = choice.data?.models ?? [];
  const measuredModels = measured ?? models.map((m) => m.model);
  const freeSimModel = freeModel ?? choice.data?.default_model ?? null;

  const usesDates = kind !== "measurement" && ownDates;
  // A free sim needs a model only when one of its sims reads memory; a build-up sim never does.
  const readsMemory = kind === "measurement" || (kind === "free" && (variant === "memory_on" || partner));

  // What the form asks for, or why it cannot ask yet.
  let wanted: SimToStart | null = null;
  let notReady: string | null = null;
  if (datasetId === null) notReady = datasets.data ? "Build and publish a dataset first." : null;
  else if (!choice.data) notReady = null;
  else if (kind === "measurement" && measuredModels.length === 0) notReady = "Tick at least one model.";
  else
    wanted = {
      dataset: datasetId,
      kind,
      variant: kind === "free" ? variant : kind === "measurement" ? "memory_on" : "memory_off",
      market: usesDates ? null : market,
      first_day: usesDates && firstDay ? firstDay : null,
      last_day: usesDates && lastDay ? lastDay : null,
      models: !readsMemory ? null : kind === "measurement" ? measuredModels : freeSimModel ? [freeSimModel] : null,
      partner: kind === "free" && partner,
      starting_value: 10_000,
    };
  const asked = wanted === null ? null : JSON.stringify(wanted);

  const [check, setCheck] = useState<{ asked: string; answer: SimCheck } | null>(null);
  const [checkError, setCheckError] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);
  const [startRefusals, setStartRefusals] = useState<Refusal[] | null>(null);
  const [startError, setStartError] = useState<string | null>(null);

  useEffect(() => {
    setStartRefusals(null);
    setStartError(null);
    if (asked === null) return;
    let stopped = false;
    const timer = window.setTimeout(async () => {
      try {
        const answer = await checkSim(JSON.parse(asked) as SimToStart);
        if (stopped) return;
        setCheck({ asked, answer });
        setCheckError(null);
      } catch (problem) {
        if (!stopped) setCheckError(problem instanceof Error ? problem.message : String(problem));
      }
    }, ASK_AFTER_MS);
    return () => {
      stopped = true;
      window.clearTimeout(timer);
    };
  }, [asked]);

  const answer = check !== null && check.asked === asked ? check.answer : null;
  const refusals = startRefusals ?? answer?.refusals ?? [];
  const canStart = wanted !== null && answer !== null && refusals.length === 0 && !starting;

  function pickKind(picked: Kind) {
    setKind(picked);
    if (picked === "measurement") return;
    setOwnDates(true);
    if (picked === "build-up" && !firstDay && !lastDay) {
      setFirstDay(BUILD_UP_YEAR.first);
      setLastDay(BUILD_UP_YEAR.last);
    }
  }

  async function start(event: FormEvent) {
    event.preventDefault();
    if (!canStart || wanted === null) return;
    setStarting(true);
    try {
      const started = await startSim(wanted);
      window.location.hash = `#/sims/${started.sim_ids[0]}`;
    } catch (problem) {
      if (problem instanceof RefusedError) setStartRefusals(problem.refusals);
      else setStartError(problem instanceof Error ? problem.message : String(problem));
      setStarting(false);
    }
  }

  const readError = datasets.error ?? choice.error;
  const chosenDataset = datasets.data?.datasets.find((d) => d.id === datasetId);

  return (
    <section>
      <h1 className="mb-1 text-center text-[2.1rem] leading-tight tracking-[.02em]">New trading sim</h1>
      <p className="mb-8 text-center text-[1.1rem] text-dim">
        Pick what to run; the form shows what it would cost before you start it
      </p>

      {readError && (
        <div className="mb-6">
          <ErrorBox title="The form could not load" text={readError} />
        </div>
      )}

      <form onSubmit={(e) => void start(e)} className="grid gap-8">
        <div>
          <SectionHeading number={1} title="Kind" says="Practice and tuning sims are command-line tools" />
          <fieldset className="grid gap-3 px-[2ch]">
            <legend className="sr-only">Kind of sim</legend>
            {FORM_KINDS.map((k) => (
              <label key={k.kind} className="flex items-start gap-3">
                <input
                  type="radio"
                  name="kind"
                  value={k.kind}
                  checked={kind === k.kind}
                  onChange={() => pickKind(k.kind)}
                  className="mt-1.5 size-4 accent-amber"
                />
                <span>
                  <span className="font-mono tracking-wider">{k.title}</span>
                  <span className="block text-[15px] text-dim">{k.says}</span>
                </span>
              </label>
            ))}
          </fieldset>
        </div>

        <div>
          <SectionHeading number={2} title="Days" says="A test period, or your own dates" />
          <fieldset className="grid gap-4 px-[2ch]">
            <legend className="sr-only">Days</legend>
            <label className="grid w-fit gap-1">
              <span className={label}>Dataset (the prices the sim replays)</span>
              <select
                className={field}
                value={datasetId ?? ""}
                onChange={(e) => setDataset(Number(e.target.value))}
              >
                {datasetId === null && <option value="">No published dataset</option>}
                {(datasets.data?.datasets ?? []).map((d) => (
                  <option key={d.id} value={d.id}>
                    {datasetWords(d)}
                  </option>
                ))}
              </select>
            </label>

            <div className="flex flex-wrap gap-6">
              <label className="flex items-center gap-3">
                <input
                  type="radio"
                  name="days"
                  checked={!usesDates}
                  onChange={() => setOwnDates(false)}
                  className="size-4 accent-amber"
                />
                <span className="font-mono tracking-wider">A test period</span>
              </label>
              <label className="flex items-center gap-3">
                <input
                  type="radio"
                  name="days"
                  checked={usesDates}
                  disabled={kind === "measurement"}
                  onChange={() => setOwnDates(true)}
                  className="size-4 accent-amber disabled:opacity-40"
                />
                <span className={`font-mono tracking-wider ${kind === "measurement" ? "text-dim" : ""}`}>
                  Your own dates
                </span>
              </label>
            </div>
            <p className="text-[15px] text-dim">
              {kind === "measurement"
                ? "A measurement plays one test period whole: 30 days the agent was never adjusted on."
                : "Test period days are kept for measurements; any other sim using them is refused."}
            </p>

            <div className="flex flex-wrap items-end gap-6">
              {usesDates ? (
                <>
                  <label className="grid gap-1">
                    <span className={label}>First day</span>
                    <input
                      type="date"
                      className={field}
                      value={firstDay}
                      min={chosenDataset?.first_day ?? undefined}
                      max={chosenDataset?.last_day ?? undefined}
                      onChange={(e) => setFirstDay(e.target.value)}
                    />
                  </label>
                  <label className="grid gap-1">
                    <span className={label}>Last day</span>
                    <input
                      type="date"
                      className={field}
                      value={lastDay}
                      min={chosenDataset?.first_day ?? undefined}
                      max={chosenDataset?.last_day ?? undefined}
                      onChange={(e) => setLastDay(e.target.value)}
                    />
                  </label>
                </>
              ) : (
                <label className="grid gap-1">
                  <span className={label}>Test period</span>
                  <select className={field} value={market} onChange={(e) => setMarket(e.target.value)}>
                    {TEST_PERIODS.map((p) => (
                      <option key={p.market} value={p.market}>
                        {p.title}
                      </option>
                    ))}
                  </select>
                </label>
              )}
            </div>
          </fieldset>
        </div>

        <div>
          <SectionHeading number={3} title="Memory" says="A free sim: with memory first" />
          {kind === "free" ? (
            <fieldset className="grid gap-3 px-[2ch]">
              <legend className="sr-only">Memory</legend>
              {(["memory_on", "memory_off"] as Variant[]).map((v) => (
                <label key={v} className="flex items-center gap-3">
                  <input
                    type="radio"
                    name="memory"
                    value={v}
                    checked={variant === v}
                    onChange={() => setVariant(v)}
                    className="size-4 accent-amber"
                  />
                  <span className="font-mono tracking-wider">{v === "memory_on" ? "With memory" : "Without memory"}</span>
                </label>
              ))}
              <label className="flex items-start gap-3">
                <input
                  type="checkbox"
                  checked={partner}
                  onChange={(e) => setPartner(e.target.checked)}
                  className="mt-1.5 size-4 accent-amber"
                />
                <span>
                  <span className="font-mono tracking-wider">
                    Also play the same days {VARIANT_WORDS[other(variant)]}
                  </span>
                  <span className="block text-[15px] text-dim">Side by side, as a second sim.</span>
                </span>
              </label>
            </fieldset>
          ) : (
            <p className="px-[2ch] text-[15px] text-dim">
              {kind === "measurement"
                ? "A measurement always plays both ways: with memory (once per model) and without, side by side."
                : "A build-up sim plays without memory: its trades become the memory later sims start from."}
            </p>
          )}
        </div>

        <div>
          <SectionHeading number={4} title="Model" says="The LLM that picks which past episodes Jev reads" />
          {kind === "measurement" && (
            <fieldset className="grid gap-3 px-[2ch]">
              <legend className="sr-only">Models</legend>
              <div className="flex flex-wrap gap-6">
                {models.map((m) => (
                  <label key={m.model} className="flex items-center gap-3">
                    <input
                      type="checkbox"
                      value={m.model}
                      checked={measuredModels.includes(m.model)}
                      onChange={(e) =>
                        setMeasured(
                          e.target.checked
                            ? models.map((x) => x.model).filter((x) => x === m.model || measuredModels.includes(x))
                            : measuredModels.filter((x) => x !== m.model),
                        )
                      }
                      className="size-4 accent-amber"
                    />
                    <span className="font-mono tracking-wider">{m.label}</span>
                  </label>
                ))}
              </div>
              <p className="text-[15px] text-dim">
                {measuredModels.length > 1
                  ? `${measuredModels.length + 1} sims over the same days: with memory once per model, and one without memory.`
                  : "2 sims over the same days: with memory and without."}
              </p>
            </fieldset>
          )}
          {kind === "free" && (
            <fieldset disabled={!readsMemory} className="grid gap-3 px-[2ch]">
              <legend className="sr-only">Model</legend>
              <div className="flex flex-wrap gap-6">
                {models.map((m) => (
                  <label key={m.model} className="flex items-center gap-3">
                    <input
                      type="radio"
                      name="model"
                      value={m.model}
                      checked={freeSimModel === m.model}
                      onChange={() => setFreeModel(m.model)}
                      className="size-4 accent-amber disabled:opacity-40"
                    />
                    <span className={`font-mono tracking-wider ${readsMemory ? "" : "text-dim"}`}>
                      {m.label}
                      {m.model === choice.data?.default_model && <span className="text-dim"> (default)</span>}
                    </span>
                  </label>
                ))}
              </div>
              <p className="text-[15px] text-dim">
                {readsMemory
                  ? "A free sim uses one model."
                  : "A sim without memory uses no LLM: Jev decides alone."}
              </p>
            </fieldset>
          )}
          {kind === "build-up" && (
            <p className="px-[2ch] text-[15px] text-dim">A build-up sim uses no LLM: Jev decides alone.</p>
          )}
        </div>

        <div>
          <SectionHeading number={5} title="Cost" says="Real dollars, asked again as choices change" />
          <dl className="flex flex-wrap gap-6 px-[2ch] font-mono">
            <div>
              <dt className={label}>Estimate</dt>
              <dd>{answer ? dollarsAndCents(answer.estimate_usd) : "--"}</dd>
            </div>
            <div>
              <dt className={label}>Spending cap</dt>
              <dd>{answer ? dollarsAndCents(answer.spending_cap_usd) : "--"}</dd>
            </div>
            <div>
              <dt className={label}>Left under the ceiling</dt>
              <dd>
                {answer
                  ? `${dollarsAndCents(answer.left_under_ceiling_usd)} of ${dollarsAndCents(answer.ceiling_usd)}`
                  : "--"}
              </dd>
            </div>
          </dl>
          <p className="mt-2 px-[2ch] text-[15px] text-dim">
            The spending cap is the most these sims may pay before they stop themselves: one and a half
            times the estimate, so an estimate of $3.00 gives a cap of $4.50. The ceiling is the most the
            whole project may pay; what is left already takes off what was paid and the caps of sims
            still running.
          </p>
        </div>

        <div className="grid gap-4">
          {/* The errors: empty unless something blocks the sim, then every refusal and its fix. */}
          <div aria-live="polite" aria-label="Why it cannot start">
            {(refusals.length > 0 || notReady || checkError || startError) && (
              <div role="alert" className="border-[1.5px] border-rule">
                <div className="bg-amber px-[2ch] py-1 font-mono text-[13.5px] tracking-widest text-screen">
                  Why it cannot start
                </div>
                <ul className="grid gap-2 px-[2ch] py-2">
                  {notReady && <li>{notReady}</li>}
                  {checkError && <li>The cost and checks could not be read: {checkError}</li>}
                  {startError && <li>The sim did not start: {startError}</li>}
                  {refusals.map((r) => (
                    <li key={`${r.code}:${r.message}`}>{r.message}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>
          <div>
            <button type="submit" className={button} disabled={!canStart}>
              {starting ? "Starting..." : "Start the sim"}
            </button>
          </div>
        </div>
      </form>
    </section>
  );
}

function datasetWords(d: DatasetLine) {
  const status = d.status === "published" ? "" : ` (${d.status})`;
  return `${d.id}: ${d.name}${status}`;
}
