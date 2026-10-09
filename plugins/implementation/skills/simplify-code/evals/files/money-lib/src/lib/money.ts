export type Currency = "USD" | "EUR" | "GBP";

export function formatMoney(cents: number, currency: Currency = "USD", locale?: string): string {
  // Create the number formatter for the currency
  const formatter = new Intl.NumberFormat(locale ?? "en-US", { style: "currency", currency });
  // Convert cents to a whole amount and format it
  return formatter.format(cents / 100);
}

/** Converts a decimal amount to integer cents. */
export function toCents(amount: number): number {
  return Math.round(amount * 100);
}
