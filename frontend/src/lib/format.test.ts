import { formatAuthors, formatCount, formatScore, formatTimestamp, paperTitle } from "./format";

describe("format", () => {
  it("formats counts and missing values", () => {
    expect(formatCount(1234)).toBe("1,234");
    expect(formatCount(null)).toBe("—");
    expect(formatCount(undefined)).toBe("—");
  });

  it("formats small scores in exponent form so they stay comparable", () => {
    expect(formatScore(0.0123)).toBe("0.012");
    expect(formatScore(0.000123)).toBe("1.23e-4");
    expect(formatScore(0)).toBe("0");
    expect(formatScore(null)).toBe("—");
  });

  it("truncates long author lists", () => {
    expect(formatAuthors(["A", "B"])).toBe("A, B");
    expect(formatAuthors(["A", "B", "C", "D", "E"])).toBe("A, B, C +2 more");
    expect(formatAuthors([])).toBe("Unknown authors");
    expect(formatAuthors(undefined)).toBe("Unknown authors");
  });

  it("handles missing timestamps and titles", () => {
    expect(formatTimestamp(null)).toBe("never");
    expect(formatTimestamp("not a date")).toBe("not a date");
    expect(paperTitle(null)).toMatch(/Untitled/);
    expect(paperTitle("  ")).toMatch(/Untitled/);
    expect(paperTitle("Real")).toBe("Real");
  });
});
