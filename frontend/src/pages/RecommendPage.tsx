import { type FormEvent, useState } from "react";
import { Link } from "react-router-dom";

import { usePaperSearch, useRecommendations } from "../api/queries";
import type { PaperSummary } from "../api/types";
import { PageHeader } from "../components/PageHeader";
import { ErrorState, Loading } from "../components/StateViews";
import { formatAuthors, paperTitle } from "../lib/format";

const MAX_LIST = 20;

function Picker({ onAdd, chosen }: { onAdd: (p: PaperSummary) => void; chosen: Set<string> }) {
  const [draft, setDraft] = useState("");
  const [query, setQuery] = useState("");
  const results = usePaperSearch(query, "hybrid");
  const submit = (e: FormEvent) => {
    e.preventDefault();
    setQuery(draft.trim());
  };
  return (
    <div>
      <form className="inline-form" onSubmit={submit} role="search" aria-label="Find papers to add">
        <label className="field" style={{ flex: 1, minWidth: 240 }}>
          Find a paper you have read
          <input type="search" value={draft} onChange={(e) => setDraft(e.target.value)} placeholder="Title or topic" />
        </label>
        <button type="submit" className="btn">
          Search
        </button>
      </form>
      {results.isPending && query && <Loading label="Searching" />}
      {results.isError && <ErrorState error={results.error} />}
      {results.data && (
        <ul className="plain" style={{ marginTop: 12 }}>
          {results.data.hits.slice(0, 6).map((h) => (
            <li key={h.paper.id} className="pick-row">
              <span>
                {paperTitle(h.paper.title)} <span className="muted small">({h.paper.year ?? "n.d."})</span>
              </span>
              <button type="button" className="btn" disabled={chosen.has(h.paper.id) || chosen.size >= MAX_LIST} onClick={() => onAdd(h.paper)}>
                {chosen.has(h.paper.id) ? "Added" : "Add"}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function RecommendPage() {
  const [list, setList] = useState<PaperSummary[]>([]);
  const rec = useRecommendations();
  const chosen = new Set(list.map((p) => p.id));
  return (
    <div className="stack">
      <PageHeader
        title="Recommendations"
        subtitle="Build a reading list of papers you know; get new papers close to it by citations and by meaning."
      />
      <section className="card card-pad" aria-labelledby="list-heading">
        <h2 id="list-heading">Your reading list ({list.length})</h2>
        {list.length === 0 ? (
          <p className="muted">Add one or more papers below.</p>
        ) : (
          <ul className="plain">
            {list.map((p) => (
              <li key={p.id} className="pick-row">
                <span>{paperTitle(p.title)}</span>
                <button
                  type="button"
                  className="btn"
                  aria-label={`Remove ${paperTitle(p.title)}`}
                  onClick={() => setList(list.filter((x) => x.id !== p.id))}
                >
                  Remove
                </button>
              </li>
            ))}
          </ul>
        )}
        <div style={{ marginTop: 12 }}>
          <button type="button" className="btn btn-primary" disabled={list.length === 0 || rec.isPending} onClick={() => rec.mutate(list.map((p) => p.id))}>
            {rec.isPending ? "Finding papers…" : "Recommend papers"}
          </button>
        </div>
      </section>
      <section className="card card-pad" aria-label="Add papers">
        <Picker chosen={chosen} onAdd={(p) => setList((l) => [...l, p])} />
      </section>
      {rec.isPending && <Loading label="Finding recommendations" />}
      {rec.isError && <ErrorState error={rec.error} />}
      {rec.data && (
        <section className="card card-pad" aria-labelledby="rec-heading">
          <h2 id="rec-heading">Suggested next reads</h2>
          {rec.data.note && <p className="note small">{rec.data.note}</p>}
          {rec.data.recommendations.length === 0 ? (
            <p className="muted">Nothing close enough to suggest. Try adding more papers.</p>
          ) : (
            <ol className="sources">
              {rec.data.recommendations.map((r, i) => (
                <li key={r.paper.id} className="source">
                  <span className="source-n">{i + 1}.</span>
                  <div>
                    <Link to={`/papers/${encodeURIComponent(r.paper.id)}`}>{paperTitle(r.paper.title)}</Link>
                    <div className="row-meta">
                      {formatAuthors(r.paper.authors)}
                      {r.paper.year != null && <> · {r.paper.year}</>}
                    </div>
                    <ul className="small muted reasons">
                      {r.reasons.map((reason) => (
                        <li key={reason.kind}>{reason.text}</li>
                      ))}
                    </ul>
                    {r.linked_to.length > 0 && <p className="small muted">Linked to: {r.linked_to.join("; ")}</p>}
                  </div>
                </li>
              ))}
            </ol>
          )}
        </section>
      )}
    </div>
  );
}
