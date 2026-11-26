// Reads from the API. The types come from `schema.d.ts`, generated from the API's own description.
import type { components } from "./schema";

type Schemas = components["schemas"];
export type SimLine = Schemas["SimLine"];
export type SimsList = Schemas["SimsList"];
export type SpendingTotal = Schemas["SpendingTotal"];
export type SimHeader = Schemas["SimHeader"];
export type Chart = Schemas["Chart"];
export type ChartLine = Schemas["ChartLine"];
export type TradeTick = Schemas["TradeTick"];
export type LiveFigures = Schemas["LiveFigures"];
export type Moment = Schemas["Moment"];
export type OrderLine = Schemas["OrderLine"];
export type DecisionLine = Schemas["DecisionLine"];
export type Price = Schemas["Price"];
export type AssetName = Schemas["AssetName"];
export type TradesTable = Schemas["TradesTable"];
export type TradeLine = Schemas["TradeLine"];
export type DayMark = Schemas["DayMark"];
export type FilterCounts = Schemas["FilterCounts"];
export type TradePage = Schemas["TradePage"];
export type DecisionTrail = Schemas["DecisionTrail"];
export type Measurements = Schemas["Measurements"];
export type MeasurementGroup = Schemas["MeasurementGroup"];
export type Figure = Schemas["Figure"];
export type Breakdown = Schemas["Breakdown"];
export type Scorecard = Schemas["Scorecard"];
export type ScorecardLine = Schemas["ScorecardLine"];
export type Split = Schemas["Split"];
export type Playbook = Schemas["Playbook"];
export type Pattern = Schemas["Pattern"];
export type Spending = Schemas["Spending"];
export type SpendingItem = Schemas["SpendingItem"];
export type Refusal = Schemas["Refusal"];
export type Comparison = Schemas["Comparison"];
export type MarketComparison = Schemas["MarketComparison"];
export type ModelResult = Schemas["ModelResult"];
export type GapLine = Schemas["GapLine"];
export type DatasetLine = Schemas["DatasetLine"];
export type DatasetsList = Schemas["DatasetsList"];
export type DatasetPage = Schemas["DatasetPage"];
export type DatasetToBuild = Schemas["DatasetToBuild"];
export type DatasetStarted = Schemas["DatasetStarted"];
export type QualityCheck = Schemas["QualityCheck"];
export type PriceChart = Schemas["PriceChart"];
export type SimToStart = Schemas["SimToStart"];
export type SimCheck = Schemas["SimCheck"];
export type SimsStarted = Schemas["SimsStarted"];
export type ModelChoice = Schemas["ModelChoice"];

async function read<T>(path: string): Promise<T> {
  const answer = await fetch(`/api${path}`);
  if (!answer.ok) throw new Error(`The API answered ${answer.status} for ${path}`);
  return answer.json() as Promise<T>;
}

export const fetchSims = () => read<SimsList>("/sims");
export const fetchSpendingTotal = () => read<SpendingTotal>("/spending/total");
export const fetchSpending = () => read<Spending>("/spending");
export const fetchPlaybook = () => read<Playbook>("/playbook");
export const fetchComparison = () => read<Comparison>("/comparison");
export const fetchModels = () => read<ModelChoice>("/models");
export const fetchDatasets = () => read<DatasetsList>("/datasets");
export const fetchDataset = (id: number) => read<DatasetPage>(`/datasets/${id}`);
// `ticker`: the asset's real ticker, such as AAPL.
export const fetchDatasetBars = (id: number, ticker: string) =>
  read<PriceChart>(`/datasets/${id}/bars?ticker=${encodeURIComponent(ticker)}`);
export const fetchSimHeader = (id: number) => read<SimHeader>(`/sims/${id}`);
export const fetchChart = (id: number) => read<Chart>(`/sims/${id}/chart`);
export const fetchLive = (id: number, afterStep: number | null) =>
  read<LiveFigures>(`/sims/${id}/live${afterStep === null ? "" : `?after_step=${afterStep}`}`);
// `at` is a real UTC time as the API writes it, such as 2025-03-02T11:00:00.
export const fetchMoment = (id: number, at: string) =>
  read<Moment>(`/sims/${id}/moment?at=${encodeURIComponent(at)}`);

// The trades table's filters: each true one keeps only the trades it names; `no_trade` adds the
// full evaluations that ended in no trade.
export type TradeFilters = {
  lost_money: boolean;
  trimmed: boolean;
  stop_price: boolean;
  overnight: boolean;
  no_trade: boolean;
};

export function fetchTrades(id: number, filters: TradeFilters, page: number, pageSize: number) {
  const ask = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
  for (const [name, on] of Object.entries(filters)) if (on) ask.set(name, "true");
  return read<TradesTable>(`/sims/${id}/trades?${ask}`);
}

// `trade`: the position number, as a trades table line gives it.
export const fetchTrade = (id: number, trade: number) => read<TradePage>(`/sims/${id}/trades/${trade}`);
export const fetchTrail = (id: number, decision: string) =>
  read<DecisionTrail>(`/sims/${id}/decisions/${encodeURIComponent(decision)}/trail`);

export const fetchMeasurements = (id: number) => read<Measurements>(`/sims/${id}/measurements`);

export function fetchScorecard(id: number, split: Split[]) {
  const ask = new URLSearchParams();
  for (const part of split) ask.append("split", part);
  return read<Scorecard>(`/sims/${id}/scorecard${split.length ? `?${ask}` : ""}`);
}

// The New trading sim form's question: may this sim start, and what would it cost? Takes what
// starting a sim takes; stores nothing.
export function checkSim(wanted: SimToStart) {
  const ask = new URLSearchParams();
  for (const [name, value] of Object.entries(wanted)) {
    if (value === null || value === undefined) continue;
    for (const one of Array.isArray(value) ? value : [value]) ask.append(name, String(one));
  }
  return read<SimCheck>(`/sims/check?${ask}`);
}

// A request to the API was refused: every reason, each saying how to fix it.
export class RefusedError extends Error {
  constructor(public refusals: Refusal[]) {
    super(refusals.map((r) => r.message).join("; "));
  }
}

async function post<T>(path: string, body?: unknown): Promise<T> {
  const answer = await fetch(`/api${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (answer.status === 409) throw new RefusedError((await answer.json()).refusals as Refusal[]);
  if (!answer.ok) throw new Error(`The API answered ${answer.status} for ${path}`);
  return answer.json() as Promise<T>;
}

export const buildDataset = (wanted: DatasetToBuild) => post<DatasetStarted>("/datasets", wanted);
export const stopDataset = (id: number) => post<DatasetPage>(`/datasets/${id}/stop`);
// Starts the sim or sims `wanted` describes (a measurement starts two or three); refused with
// every reason, as `checkSim` would have answered.
export const startSim = (wanted: SimToStart) => post<SimsStarted>("/sims", wanted);
export const stopSim = (id: number) => post<SimHeader>(`/sims/${id}/stop`);
// `spendingCapUsd`: a new cap, needed only when the spending cap stopped the sim.
export const resumeSim = (id: number, spendingCapUsd: number | null) =>
  post<SimHeader>(`/sims/${id}/resume`, { spending_cap_usd: spendingCapUsd });
