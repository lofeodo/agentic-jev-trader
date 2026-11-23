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

  // Asks again only after the last answer, and only while a sim is in progress.
  useEffect(() => {
    let stopped = false;
    let timer: number | undefined;

    async function load() {
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
      }
      if (again) timer = window.setTimeout(load, REFRESH_MS);
    }

    void load();
    return () => {
      stopped = true;
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
