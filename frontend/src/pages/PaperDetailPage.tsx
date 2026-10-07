import { useState } from "react";
import { Link, useParams } from "react-router-dom";

import {
  useCitations,
  usePaper,
  useReferences,
  useRelatedPapers,
  useSimilarPapers,
} from "../api/queries";
import type { PaperDetail, SimilarPaper } from "../api/types";
import { PaperList } from "../components/PaperList";
import { Pagination } from "../components/Pagination";
import { Empty, ErrorState, Loading } from "../components/StateViews";
import { formatCount, formatScore, paperTitle } from "../lib/format";

function Metrics({ paper }: { paper: PaperDetail }) {
  const m = paper.metrics;
  return (
    <section className="card" aria-labelledby="metrics-heading">
      <h2 id="metrics-heading">Graph metrics</h2>
      <dl className="kv">
        <dt>Cited by (in this graph)</dt>
        <dd>{formatCount(paper.cited_by_in_graph)}</dd>
        <dt>References (in this graph)</dt>
        <dd>{formatCount(paper.references_in_graph)}</dd>
        <dt>Citations reported by source</dt>
        <dd>{formatCount(paper.citation_count)}</dd>
        <dt>PageRank</dt>
        <dd>{formatScore(m.pagerank)}</dd>
        <dt>Betweenness</dt>
        <dd>{formatScore(m.betweenness)}</dd>
        <dt>Community</dt>
        <dd>{m.community_id ?? "—"}</dd>
      </dl>
      <p className="note small">
        Structural metrics depend on which papers are in this graph. They are not measures of quality.
        {m.pagerank == null && " Run researchgraph analyze to compute them."}
      </p>
    </section>
  );
}

function CitationLists({ id }: { id: string }) {
  const [direction, setDirection] = useState<"citations" | "references">("citations");
  const [page, setPage] = useState(1);
  const citations = useCitations(id, page);
  const references = useReferences(id, page);
  const active = direction === "citations" ? citations : references;

  const choose = (next: "citations" | "references") => {
    setDirection(next);
    setPage(1);
  };

  return (
    <section className="card" aria-labelledby="links-heading">
      <h2 id="links-heading">Citation links</h2>
      <div className="tabs" role="group" aria-label="Link direction">
        <button type="button" className="btn tab" aria-pressed={direction === "citations"} onClick={() => choose("citations")}>
          Cited by
        </button>
        <button type="button" className="btn tab" aria-pressed={direction === "references"} onClick={() => choose("references")}>
          References
        </button>
      </div>
      {active.isPending && <Loading />}
      {active.isError && <ErrorState error={active.error} onRetry={() => void active.refetch()} />}
      {active.data &&
        (active.data.items.length === 0 ? (
          <p className="muted">
            {direction === "citations"
              ? "No papers in this graph cite this paper."
              : "No references from this paper are in this graph."}
          </p>
        ) : (
          <>
            <PaperList papers={active.data.items} />
            <Pagination
              page={active.data.page}
              pageSize={active.data.page_size}
              total={active.data.total}
              onChange={setPage}
            />
          </>
        ))}
    </section>
  );
}

function SimilarList({ items }: { items: readonly SimilarPaper[] }) {
  return (
    <ul className="paper-list">
      {items.map((item) => (
        <li key={item.paper.id} className="paper-item">
          <Link className="paper-title" to={`/papers/${encodeURIComponent(item.paper.id)}`}>
            {paperTitle(item.paper.title)}
          </Link>
          <div className="paper-meta">{item.explanation}</div>
        </li>
      ))}
    </ul>
  );
}

function SimilarPapers({ id }: { id: string }) {
  const [method, setMethod] = useState<"coupling" | "cocitation">("coupling");
  const similar = useSimilarPapers(id, method);
  const related = useRelatedPapers(id);

  return (
    <section className="card" aria-labelledby="similar-heading">
      <h2 id="similar-heading">Similar and related papers</h2>
      <p className="muted small">Based on citation structure only, not on paper text.</p>
      <div className="tabs" role="group" aria-label="Similarity method">
        <button type="button" className="btn tab" aria-pressed={method === "coupling"} onClick={() => setMethod("coupling")}>
          Shared references
        </button>
        <button type="button" className="btn tab" aria-pressed={method === "cocitation"} onClick={() => setMethod("cocitation")}>
          Cited together
        </button>
      </div>
      {similar.isPending && <Loading />}
      {similar.isError && <ErrorState error={similar.error} onRetry={() => void similar.refetch()} />}
      {similar.data &&
        (similar.data.length === 0 ? (
          <p className="muted">No structurally similar papers found for this method.</p>
        ) : (
          <SimilarList items={similar.data} />
        ))}

      <h2 style={{ marginTop: 16 }}>Reachable through citation paths</h2>
      {related.isPending && <Loading />}
      {related.isError && <ErrorState error={related.error} onRetry={() => void related.refetch()} />}
      {related.data &&
        (related.data.length === 0 ? (
          <p className="muted">No nearby papers found.</p>
        ) : (
          <SimilarList items={related.data} />
        ))}
    </section>
  );
}

function Details({ paper }: { paper: PaperDetail }) {
  return (
    <div className="stack">
      <div>
        <h1>{paperTitle(paper.title)}</h1>
        <div className="paper-meta">
          {paper.authors.length > 0 ? paper.authors.map((a) => a.name).join(", ") : "Unknown authors"}
          {paper.year != null && <> · {paper.year}</>}
          {paper.venue && <> · {paper.venue.name}</>}
        </div>
        <div className="paper-meta">
          {paper.doi && (
            <a href={`https://doi.org/${paper.doi}`} target="_blank" rel="noreferrer noopener">
              DOI {paper.doi}
            </a>
          )}
          {paper.arxiv_id && <> · arXiv:{paper.arxiv_id}</>}
        </div>
      </div>

      {paper.is_stub && (
        <p className="note">
          This paper is a stub: it is cited by ingested papers, but its own metadata has not been fetched.
        </p>
      )}
      {!paper.authors_complete && (
        <p className="note small">The author list from the source may be incomplete.</p>
      )}

      <div className="two-col">
        <div className="stack">
          <section className="card" aria-labelledby="abstract-heading">
            <h2 id="abstract-heading">Abstract</h2>
            {/* Source text is untrusted: rendered as plain text only, never as HTML. */}
            <p style={{ whiteSpace: "pre-wrap", margin: 0 }}>
              {paper.abstract ?? <span className="muted">No abstract available.</span>}
            </p>
          </section>
          {(paper.topics.length > 0 || paper.keywords.length > 0) && (
            <section className="card" aria-labelledby="topics-heading">
              <h2 id="topics-heading">Topics and keywords</h2>
              <div className="chips">
                {paper.topics.map((t) => (
                  <span key={t.id} className="badge">
                    {t.name}
                  </span>
                ))}
                {paper.keywords.map((k) => (
                  <span key={k} className="badge">
                    {k}
                  </span>
                ))}
              </div>
            </section>
          )}
          <CitationLists id={paper.id} />
          <SimilarPapers id={paper.id} />
        </div>
        <div className="stack">
          <Metrics paper={paper} />
        </div>
      </div>
    </div>
  );
}

export function PaperDetailPage() {
  const { paperId = "" } = useParams();
  const paper = usePaper(paperId);

  if (paper.isPending) return <Loading label="Loading paper" />;
  if (paper.isError) {
    if ("isNotFound" in paper.error && paper.error.isNotFound === true) {
      return (
        <Empty title="Paper not found">
          <Link to="/papers">Back to all papers</Link>
        </Empty>
      );
    }
    return <ErrorState error={paper.error} onRetry={() => void paper.refetch()} />;
  }
  return <Details paper={paper.data} />;
}
