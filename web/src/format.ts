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
