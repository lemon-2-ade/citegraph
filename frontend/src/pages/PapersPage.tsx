import { type FormEvent, useState } from "react";
import { useSearchParams } from "react-router-dom";

import { type PaperListParams, type PaperSort, usePapers } from "../api/queries";
import { PaperList } from "../components/PaperList";
import { Pagination } from "../components/Pagination";
import { Empty, ErrorState, Loading } from "../components/StateViews";
import { formatCount } from "../lib/format";

const PAGE_SIZE = 20;
const SORTS: { value: PaperSort; label: string }[] = [
  { value: "year", label: "Newest first" },
  { value: "pagerank", label: "PageRank (structural influence)" },
  { value: "cited_by", label: "Cited by (in this graph)" },
];

function parseYear(value: string | null): number | undefined {
  if (!value) return undefined;
  const year = Number(value);
  return Number.isInteger(year) && year >= 1600 && year <= 2100 ? year : undefined;
}

function parseSort(value: string | null): PaperSort {
  return SORTS.some((s) => s.value === value) ? (value as PaperSort) : "year";
}

function parsePage(value: string | null): number {
  const page = Number(value);
  return Number.isInteger(page) && page >= 1 ? page : 1;
}

export function PapersPage() {
  const [params, setParams] = useSearchParams();
  const yearFrom = parseYear(params.get("year_from"));
  const yearTo = parseYear(params.get("year_to"));
  const sort = parseSort(params.get("sort"));
  const page = parsePage(params.get("page"));

  const query: PaperListParams = { page, page_size: PAGE_SIZE, sort };
  if (yearFrom !== undefined) query.year_from = yearFrom;
  if (yearTo !== undefined) query.year_to = yearTo;
  const papers = usePapers(query);

  const [from, setFrom] = useState(yearFrom?.toString() ?? "");
  const [to, setTo] = useState(yearTo?.toString() ?? "");

  const update = (changes: Record<string, string | null>) => {
    const next = new URLSearchParams(params);
    for (const [key, value] of Object.entries(changes)) {
      if (value === null || value === "") next.delete(key);
      else next.set(key, value);
    }
    setParams(next);
  };

  const onSubmit = (event: FormEvent) => {
    event.preventDefault();
    update({ year_from: from, year_to: to, page: null });
  };

  return (
    <div className="stack">
      <h1>Papers</h1>

      <form className="card filters" onSubmit={onSubmit}>
        <label className="field">
          From year
          <input inputMode="numeric" value={from} onChange={(e) => setFrom(e.target.value)} placeholder="e.g. 2017" />
        </label>
        <label className="field">
          To year
          <input inputMode="numeric" value={to} onChange={(e) => setTo(e.target.value)} placeholder="e.g. 2024" />
        </label>
        <label className="field">
          Sort by
          <select value={sort} onChange={(e) => update({ sort: e.target.value, page: null })}>
            {SORTS.map((s) => (
              <option key={s.value} value={s.value}>
                {s.label}
              </option>
            ))}
          </select>
        </label>
        <button type="submit" className="btn btn-primary">
          Apply
        </button>
      </form>

      {papers.isPending && <Loading label="Loading papers" />}
      {papers.isError && <ErrorState error={papers.error} onRetry={() => void papers.refetch()} />}
      {papers.data &&
        (papers.data.items.length === 0 ? (
          <Empty title="No papers match these filters">Try widening the year range.</Empty>
        ) : (
          <section className="card" aria-label="Paper results">
            <p className="muted small">{formatCount(papers.data.total)} papers</p>
            <PaperList papers={papers.data.items} showPagerank={sort === "pagerank"} />
            <Pagination
              page={papers.data.page}
              pageSize={papers.data.page_size}
              total={papers.data.total}
              onChange={(p) => update({ page: String(p) })}
            />
          </section>
        ))}
    </div>
  );
}
