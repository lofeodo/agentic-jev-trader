// How numbers read on screen. A gain or a loss is told by its sign, never by colour.

const whole = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 });
const cents = new Intl.NumberFormat("en-US", {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

export const dollars = (value: number) => `$${whole.format(value)}`;
export const dollarsAndCents = (value: number) => `$${cents.format(value)}`;

export function signedDollars(value: number) {
  const rounded = Math.round(value);
  if (rounded === 0) return "$0";
  return `${rounded > 0 ? "+" : "-"}$${whole.format(Math.abs(rounded))}`;
}

const utcDay = new Intl.DateTimeFormat("en-GB", {
  day: "numeric",
  month: "short",
  year: "numeric",
  timeZone: "UTC",
});

export const day = (isoDate: string) => utcDay.format(new Date(`${isoDate}T00:00:00Z`));

// The API writes UTC times with no zone, such as 2025-03-02T11:00:00.
export const fromApi = (time: string) => new Date(`${time}Z`);
export const toApi = (time: Date) => time.toISOString().slice(0, 19);

const STEP_MS = 15 * 60 * 1000;
// A step ends 15 minutes after the one before; `stepsStartAt` is when step 0 ends.
export const stepTime = (stepsStartAt: string, step: number) =>
  new Date(fromApi(stepsStartAt).getTime() + step * STEP_MS);

const utcTime = new Intl.DateTimeFormat("en-GB", {
  hour: "2-digit",
  minute: "2-digit",
  hourCycle: "h23",
  timeZone: "UTC",
});

export const dayAndTime = (time: Date) =>
  `${utcDay.format(time)}, ${utcTime.format(time)} UTC`;
export const timeOfDay = (time: Date) => utcTime.format(time);
export const shortDay = (time: Date) =>
  new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", timeZone: "UTC" }).format(time);

export function signedDollarsAndCents(value: number) {
  const rounded = Math.round(value * 100) / 100;
  if (rounded === 0) return "$0.00";
  return `${rounded > 0 ? "+" : "-"}$${cents.format(Math.abs(rounded))}`;
}

// Real prices can be large (Bitcoin) or small; two decimals unless the price is tiny.
export const price = (value: number) =>
  `$${new Intl.NumberFormat("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: value < 1 ? 6 : 2,
  }).format(value)}`;

export const units = (value: number) =>
  new Intl.NumberFormat("en-US", { maximumFractionDigits: value < 10 ? 6 : 2 }).format(value);
