// How the Datasets and Dataset screens put a dataset's state into words.
import type { DatasetLine, QualityCheck } from "./api/client";

export const percent = (share: number) =>
  `${new Intl.NumberFormat("en-US", { maximumFractionDigits: share < 0.01 ? 2 : 1 }).format(share * 100)}%`;

export function datasetStatus(d: DatasetLine) {
  if (d.status === "being built") return `Being built: ${d.stage ?? "starting"}, ${percent(d.progress ?? 0)}`;
  if (d.status === "published" && d.published_without_check) return "Published without the check";
  if (d.status === "failed") {
    // A failed check's reason is several lines ("Over a limit:", one line per asset): the first leads.
    const reason = d.failure_reason?.split("\n")[0].replace(/:$/, "") ?? "no reason stored";
    return `Failed: ${reason}`;
  }
  return d.status;
}

// The check's verdict in one line: inside both limits, or which asset is over which.
export function checkSummary(check: QualityCheck | null) {
  if (check === null) return "Not checked yet";
  const over = check.assets.filter((a) => a.over.length > 0);
  if (over.length === 0) return "Inside both limits";
  return `Over a limit: ${over.map((a) => `${a.asset.name} (${a.over.join(", ")})`).join("; ")}`;
}
