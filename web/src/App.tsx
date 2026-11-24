import { useEffect, useState } from "react";

import {
  fetchSims,
  fetchSpendingTotal,
  type SimLine,
  type SpendingTotal,
} from "./api/client";
import { DatasetScreen } from "./DatasetScreen";
import { DatasetsScreen } from "./DatasetsScreen";
import { PlaybookScreen } from "./PlaybookScreen";
import { SimPage } from "./SimPage";
import { SimsScreen } from "./SimsScreen";
import { SpendingScreen } from "./SpendingScreen";
import { type Screen, TopBar } from "./TopBar";

const REFRESH_MS = 20_000;

// A sim that is not responding has likely crashed, so it doesn't keep the page asking.
const inProgress = (sim: SimLine) =>
  sim.status === "created" || (sim.status === "running" && !sim.not_responding);

// `simId` is a sim's or a dataset's ID, as the screen says.
type Page = { screen: Screen; simId: number | null };

// The address after `#`: `#/sims/12` is sim 12's page, `#/datasets/3` dataset 3's,
// `#/datasets`, `#/playbook` and `#/spending` their screens; anything else is the list of sims.
function pageInAddress(): Page {
  const hash = window.location.hash;
  const sim = /^#\/sims\/(\d+)$/.exec(hash);
  if (sim) return { screen: "sims", simId: Number(sim[1]) };
  const dataset = /^#\/datasets\/(\d+)$/.exec(hash);
  if (dataset) return { screen: "datasets", simId: Number(dataset[1]) };
  if (hash === "#/datasets") return { screen: "datasets", simId: null };
  if (hash === "#/playbook") return { screen: "playbook", simId: null };
  if (hash === "#/spending") return { screen: "spending", simId: null };
  return { screen: "sims", simId: null };
}

export function App() {
  const [page, setPage] = useState<Page>(pageInAddress);
  const [spending, setSpending] = useState<SpendingTotal | null>(null);
  const { screen, simId } = page;

  useEffect(() => {
    const onMove = () => {
      setPage(pageInAddress());
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
  }, [screen, simId]);

  return (
    <main className="mx-auto max-w-[1500px] px-6 pt-6 pb-16">
      <TopBar spending={spending} screen={screen} />
      {screen === "datasets" && (simId === null ? <DatasetsScreen /> : <DatasetScreen key={simId} id={simId} />)}
      {screen === "playbook" && <PlaybookScreen />}
      {screen === "spending" && <SpendingScreen />}
      {screen === "sims" && (simId === null ? <SimsListPage /> : <SimPage key={simId} id={simId} />)}
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
