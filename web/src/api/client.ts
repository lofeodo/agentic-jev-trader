// Reads from the API. The types come from `schema.d.ts`, generated from the API's own description.
import type { components } from "./schema";

export type SimLine = components["schemas"]["SimLine"];
export type SimsList = components["schemas"]["SimsList"];
export type SpendingTotal = components["schemas"]["SpendingTotal"];

async function read<T>(path: string): Promise<T> {
  const answer = await fetch(`/api${path}`);
  if (!answer.ok) throw new Error(`The API answered ${answer.status} for ${path}`);
  return answer.json() as Promise<T>;
}

export const fetchSims = () => read<SimsList>("/sims");
export const fetchSpendingTotal = () => read<SpendingTotal>("/spending/total");
