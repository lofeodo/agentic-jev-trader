import { useEffect, useState } from "react";

import {
  fetchSims,
  fetchSpendingTotal,
  type SimLine,
  type SpendingTotal,
} from "./api/client";
import { SimsScreen } from "./SimsScreen";
import { TopBar } from "./TopBar";

const REFRESH_MS = 20_000;

const inProgress = (sim: SimLine) => sim.status === "created" || sim.status === "running";

export function App() {
  const [sims, setSims] = useState<SimLine[] | null>(null);
  const [spending, setSpending] = useState<SpendingTotal | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Asks again only after the last answer: on a timer while a sim is in progress, and whenever
  // the developer comes back to the page (a sim started from the command line then shows up).
  // With nothing in progress it stays quiet, so an open tab doesn't keep Snowflake awake.
  useEffect(() => {
    let stopped = false;
    let asking = false;
    let timer: number | undefined;

    async function load() {
      if (asking) return;
      asking = true;
      window.clearTimeout(timer);
      let again = false;
      try {
        const [list, total] = await Promise.all([fetchSims(), fetchSpendingTotal()]);
        if (stopped) return;
        setSims(list.sims);
        setSpending(total);
        setError(null);
        again = list.sims.some(inProgress);
      } catch (problem) {
        if (stopped) return;
        setError(problem instanceof Error ? problem.message : String(problem));
        again = true;
      } finally {
        asking = false;
      }
      if (again) timer = window.setTimeout(load, REFRESH_MS);
    }

    const onReturn = () => void load();
    window.addEventListener("focus", onReturn);
    void load();
    return () => {
      stopped = true;
      window.removeEventListener("focus", onReturn);
      window.clearTimeout(timer);
    };
  }, []);

  return (
    <main className="mx-auto max-w-[1500px] px-6 pt-6 pb-16">
      <TopBar spending={spending} />
      <SimsScreen sims={sims} error={error} />
    </main>
  );
}
