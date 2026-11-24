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
export type Playbook = Schemas["Playbook"];
export type Pattern = Schemas["Pattern"];
export type Spending = Schemas["Spending"];
export type SpendingItem = Schemas["SpendingItem"];

async function read<T>(path: string): Promise<T> {
  const answer = await fetch(`/api${path}`);
  if (!answer.ok) throw new Error(`The API answered ${answer.status} for ${path}`);
  return answer.json() as Promise<T>;
}

export const fetchSims = () => read<SimsList>("/sims");
export const fetchSpendingTotal = () => read<SpendingTotal>("/spending/total");
export const fetchSpending = () => read<Spending>("/spending");
export const fetchPlaybook = () => read<Playbook>("/playbook");
export const fetchSimHeader = (id: number) => read<SimHeader>(`/sims/${id}`);
export const fetchChart = (id: number) => read<Chart>(`/sims/${id}/chart`);
export const fetchLive = (id: number, afterStep: number | null) =>
  read<LiveFigures>(`/sims/${id}/live${afterStep === null ? "" : `?after_step=${afterStep}`}`);
// `at` is a real UTC time as the API writes it, such as 2025-03-02T11:00:00.
export const fetchMoment = (id: number, at: string) =>
  read<Moment>(`/sims/${id}/moment?at=${encodeURIComponent(at)}`);
