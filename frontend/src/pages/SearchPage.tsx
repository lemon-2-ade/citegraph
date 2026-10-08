import { type FormEvent, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";

import { type SearchMode, usePaperSearch } from "../api/queries";
import { PageHeader } from "../components/PageHeader";
import { Empty, ErrorState, Loading } from "../components/StateViews";
import { formatAuthors, paperTitle } from "../lib/format";

const MODES: { value: SearchMode; label: string; help: string }[] = [
  { value: "hybrid", label: "Hybrid", help: "Keyword and meaning combined (recommended)" },
  { value: "keyword", label: "Keyword", help: "Exact words in title, abstract or description (BM25)" },
  { value: "semantic", label: "Meaning", help: "Papers about the same idea, even with different words" },
];

function parseMode(value: string | null): SearchMode {
  return MODES.some((m) => m.value === value) ? (value as SearchMode) : "hybrid";
}

export function SearchPage() {
  const [params, setParams] = useSearchParams();
  const q = params.get("q") ?? "";
  const mode = parseMode(params.get("mode"));
  const [draft, setDraft] = useState(q);
  const results = usePaperSearch(q, mode);

  const update = (changes: Record<string, string | null>) => {
    const next = new URLSearchParams(params);
    for (const [k, v] of Object.entries(changes)) {
      if (v === null || v === "") next.delete(k);
      else next.set(k, v);
    }
    setParams(next);
  };
  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    update({ q: draft.trim() });
  };
  const help = MODES.find((m) => m.value === mode)?.help;

  return (
    <div className="stack">
      <PageHeader title="Search papers" subtitle="Find papers by the words they use, by what they are about, or both." />
      <form className="card filters" onSubmit={onSubmit} role="search">
        <label className="field" style={{ flex: 1, minWidth: 240 }}>
          Query
          <input
            type="search"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder="e.g. ways to make transformers cheaper to run"
          />
        </label>
        <div className="seg" role="group" aria-label="Search mode">
          {MODES.map((m) => (
            <button key={m.value} type="button" aria-pressed={mode === m.value} title={m.help} onClick={() => update({ mode: m.value === "hybrid" ? null : m.value })}>
              {m.label}
            </button>
          ))}
        </div>
        <button type="submit" className="btn btn-primary">
          Search
        </button>
      </form>
      <p className="small muted">{help}</p>

      {q.trim().length < 2 && <Empty title="Type at least two characters to search" />}
      {q.trim().length >= 2 && results.isPending && <Loading label="Searching" />}
      {results.isError && <ErrorState error={results.error} onRetry={() => void results.refetch()} />}
      {results.data && (
        <>
          {results.data.note && <p className="note">{results.data.note}</p>}
          {results.data.hits.length === 0 ? (
            <Empty title="No matching papers">Try different words, or switch the search mode.</Empty>
          ) : (
            <section className="card card-pad" aria-label="Search results">
              <p className="muted small">{results.data.hits.length} results</p>
              <ul className="rows">
                {results.data.hits.map((hit) => (
                  <li key={hit.paper.id} className="row">
                    <div>
                      <Link className="row-title" to={`/papers/${encodeURIComponent(hit.paper.id)}`}>
                        {paperTitle(hit.paper.title)}
                      </Link>
                      <div className="row-meta">
                        {formatAuthors(hit.paper.authors)}
                        {hit.paper.year != null && <> · {hit.paper.year}</>}
                        {hit.paper.venue && <> · {hit.paper.venue}</>}
                      </div>
                      <div className="chips" style={{ marginTop: 6 }}>
                        {hit.matched_by.includes("keyword") && (
                          <span className="chip">Keyword match · #{hit.keyword_rank}</span>
                        )}
                        {hit.matched_by.includes("semantic") && (
                          <span className="chip chip-accent">Similar meaning · #{hit.semantic_rank}</span>
                        )}
                      </div>
                    </div>
                  </li>
                ))}
              </ul>
            </section>
          )}
        </>
      )}
    </div>
  );
}
