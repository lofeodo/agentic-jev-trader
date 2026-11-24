import { useEffect, useState } from "react";

import {
  fetchSims,
  fetchSpendingTotal,
  type SimLine,
  type SpendingTotal,
} from "./api/client";
import { SimPage } from "./SimPage";
import { SimsScreen } from "./SimsScreen";
import { TopBar } from "./TopBar";

const REFRESH_MS = 20_000;

// A sim that is not responding has likely crashed, so it doesn't keep the page asking.
const inProgress = (sim: SimLine) =>
  sim.status === "created" || (sim.status === "running" && !sim.not_responding);

// The address after `#`: `#/sims/12` is sim 12's page; anything else is the list of sims.
function simInAddress(): number | null {
  const found = /^#\/sims\/(\d+)$/.exec(window.location.hash);
  return found ? Number(found[1]) : null;
}

export function App() {
  const [simId, setSimId] = useState<number | null>(simInAddress);
  const [spending, setSpending] = useState<SpendingTotal | null>(null);

  useEffect(() => {
    const onMove = () => {
      setSimId(simInAddress());
      window.scrollTo(0, 0);
    };
    window.addEventListener("hashchange", onMove);
    return () => window.removeEventListener("hashchange", onMove);
  }, []);

  // The top bar's spending total, read on each screen change and whenever the developer returns.
  useEffect(() => {
    let stopped = false;
    const load = () =>
      fetchSpendingTotal()
        .then((total) => !stopped && setSpending(total))
        .catch(() => undefined);
    window.addEventListener("focus", load);
    void load();
    return () => {
      stopped = true;
      window.removeEventListener("focus", load);
    };
  }, [simId]);

  return (
    <main className="mx-auto max-w-[1500px] px-6 pt-6 pb-16">
      <TopBar spending={spending} />
      {simId === null ? <SimsListPage /> : <SimPage key={simId} id={simId} />}
    </main>
  );
}

function SimsListPage() {
  const [sims, setSims] = useState<SimLine[] | null>(null);
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
        const list = await fetchSims();
        if (stopped) return;
        setSims(list.sims);
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

  return <SimsScreen sims={sims} error={error} />;
}
