import { lazy, Suspense, useState } from "react";
import { Link, useParams } from "react-router-dom";

import {
  useCitations,
  useGraphNeighbourhood,
  usePaper,
  usePaperCommunities,
  useReferences,
  useRelatedPapers,
  useSimilarPapers,
} from "../api/queries";
import type { PaperDetail, SimilarPaper } from "../api/types";
import { PaperList } from "../components/PaperList";
import { Pagination } from "../components/Pagination";
import { Empty, ErrorState, Loading } from "../components/StateViews";
import { formatCount, formatScore, paperTitle } from "../lib/format";

const GraphCanvas = lazy(() => import("../graph/GraphCanvas").then((m) => ({ default: m.GraphCanvas })));

function Neighbourhood({ id }: { id: string }) {
  const [depth, setDepth] = useState<1 | 2>(1);
  const hood = useGraphNeighbourhood(id, depth, 40);
  const communities = usePaperCommunities();
  return (
    <section className="card" aria-labelledby="hood-heading">
      <div className="card-head">
        <h2 id="hood-heading">Citation neighbourhood</h2>
        <Link to={`/graph?focus=${encodeURIComponent(id)}&depth=${depth}`}>Open in explorer →</Link>
      </div>
      <div className="card-body">
        <div className="seg" role="group" aria-label="Neighbourhood depth" style={{ marginBottom: 12 }}>
          {([1, 2] as const).map((d) => (
            <button key={d} type="button" aria-pressed={depth === d} onClick={() => setDepth(d)}>
              {d} hop{d > 1 ? "s" : ""}
            </button>
          ))}
        </div>
        {hood.isPending && <Loading label="Loading neighbourhood" />}
        {hood.isError && <ErrorState error={hood.error} onRetry={() => void hood.refetch()} />}
        {hood.data &&
          (hood.data.nodes.length <= 1 ? (
            <p className="muted">This paper has no citation links to other papers in the graph.</p>
          ) : (
            <div className="embed">
              <Suspense fallback={<Loading />}>
                <GraphCanvas
                  view={hood.data}
                  sizeBy="pagerank"
                  colorBy="community"
                  communities={communities.data}
                  interactive={false}
                  labelCount={5}
                />
              </Suspense>
            </div>
          ))}
        <p className="small faint">Arrows point from the citing paper to the cited paper. The outlined node is this paper.</p>
      </div>
    </section>
  );
}

function Metrics({ paper }: { paper: PaperDetail }) {
  const m = paper.metrics;
  return (
    <section className="card card-pad" aria-labelledby="metrics-heading">
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
        <dd>
          {m.community_id ? (
            <Link to={`/communities/${encodeURIComponent(m.community_id)}`}>View community</Link>
          ) : (
            "—"
          )}
        </dd>
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
    <section className="card card-pad" aria-labelledby="links-heading">
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
    <ul className="rows">
      {items.map((item) => (
        <li key={item.paper.id} className="row">
          <div>
          <Link className="row-title" to={`/papers/${encodeURIComponent(item.paper.id)}`}>
            {paperTitle(item.paper.title)}
          </Link>
          <div className="row-meta">{item.explanation}</div>
          </div>
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
    <section className="card card-pad" aria-labelledby="similar-heading">
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
      <div className="card hero">
        <p className="small faint">
          <Link to="/papers">Papers</Link> / {paper.year ?? "Undated"}
        </p>
        <h1>{paperTitle(paper.title)}</h1>
        <div className="row-meta">
          {paper.authors.length > 0
            ? paper.authors.map((a, i) => (
                <span key={a.id}>
                  {i > 0 && ", "}
                  <Link to={`/authors/${encodeURIComponent(a.id)}`}>{a.name}</Link>
                </span>
              ))
            : "Unknown authors"}
          {paper.year != null && <> · {paper.year}</>}
          {paper.venue && <> · {paper.venue.name}</>}
        </div>
        <div className="row-meta">
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
          <section className="card card-pad" aria-labelledby="abstract-heading">
            <h2 id="abstract-heading">Abstract</h2>
            {/* Source text is untrusted: rendered as plain text only, never as HTML. */}
            <p className="abstract" style={{ margin: 0 }}>
              {paper.abstract ?? <span className="muted">No abstract available.</span>}
            </p>
          </section>
          {(paper.topics.length > 0 || paper.keywords.length > 0) && (
            <section className="card card-pad" aria-labelledby="topics-heading">
              <h2 id="topics-heading">Topics and keywords</h2>
              <div className="chips">
                {paper.topics.map((t) => (
                  <Link key={t.id} className="chip" to={`/topics/${encodeURIComponent(t.id)}`}>
                    {t.name}
                  </Link>
                ))}
                {paper.keywords.map((k) => (
                  <span key={k} className="chip">
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
          <Neighbourhood id={paper.id} />
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
