const number = new Intl.NumberFormat("en-US");

export function formatCount(value: number | null | undefined): string {
  return value == null ? "—" : number.format(value);
}

/** PageRank values are tiny; show enough significant digits to compare them. */
export function formatScore(value: number | null | undefined): string {
  if (value == null) return "—";
  if (value === 0) return "0";
  return value >= 0.01 ? value.toFixed(3) : value.toExponential(2);
}

export function formatAuthors(authors: readonly string[] | undefined, max = 3): string {
  const names = authors ?? [];
  if (names.length === 0) return "Unknown authors";
  const shown = names.slice(0, max).join(", ");
  return names.length > max ? `${shown} +${names.length - max} more` : shown;
}

export function formatTimestamp(iso: string | null | undefined): string {
  if (!iso) return "never";
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? iso : date.toLocaleString();
}

export function paperTitle(title: string | null | undefined): string {
  return title && title.trim() ? title : "Untitled paper (metadata not yet fetched)";
}

export function plural(n: number, word: string): string {
  return `${formatCount(n)} ${word}${n === 1 ? "" : "s"}`;
}
