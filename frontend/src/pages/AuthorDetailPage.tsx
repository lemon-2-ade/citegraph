import { Link, useParams } from "react-router-dom";

import { useAuthor } from "../api/queries";
import { PageHeader } from "../components/PageHeader";
import { PaperList } from "../components/PaperList";
import { Section } from "../components/Section";
import { Empty, ErrorState, Loading } from "../components/StateViews";
import { formatCount, formatScore } from "../lib/format";

export function AuthorDetailPage() {
  const { authorId = "" } = useParams();
  const author = useAuthor(authorId);

  if (author.isPending) return <Loading label="Loading author" />;
  if (author.isError) {
    if ("isNotFound" in author.error && author.error.isNotFound === true) {
      return (
        <Empty title="Author not found">
          <Link to="/authors">Back to authors</Link>
        </Empty>
      );
    }
    return <ErrorState error={author.error} onRetry={() => void author.refetch()} />;
  }
  const a = author.data;
  return (
    <div className="stack">
      <PageHeader
        title={a.name}
        subtitle={
          a.institutions.length > 0
            ? a.institutions.map((i) => i.name).join(" · ")
            : "No institution recorded in this graph"
        }
      />
      <div className="two-col">
        <div className="stack">
          <Section id="author-papers" title={`Papers (${formatCount(a.papers.length)})`}>
            {a.papers.length === 0 ? <p className="muted">No papers.</p> : <PaperList papers={a.papers} />}
          </Section>
        </div>
        <div className="stack">
          <section className="card card-pad" aria-labelledby="author-metrics">
            <h2 id="author-metrics">Collaboration metrics</h2>
            <dl className="kv">
              <dt>PageRank (collaboration graph)</dt>
              <dd>{formatScore(a.metrics.pagerank)}</dd>
              <dt>Betweenness</dt>
              <dd>{formatScore(a.metrics.betweenness)}</dd>
              <dt>Community</dt>
              <dd>
                {a.metrics.community_id ? (
                  <Link to={`/communities/${encodeURIComponent(a.metrics.community_id)}`}>View</Link>
                ) : (
                  "—"
                )}
              </dd>
            </dl>
            <p className="note small" style={{ marginTop: 12 }}>
              Metrics describe position in this collaboration graph, not the quality of the author&apos;s work.
            </p>
          </section>
          {a.topics.length > 0 && (
            <Section id="author-topics" title="Topics">
              <div className="chips">
                {a.topics.map((t) => (
                  <Link key={t.id} className="chip" to={`/topics/${encodeURIComponent(t.id)}`}>
                    {t.name}
                  </Link>
                ))}
              </div>
            </Section>
          )}
          {a.collaborators.length > 0 && (
            <Section id="author-collabs" title="Frequent collaborators">
              <ul className="rows">
                {a.collaborators.map((c) => (
                  <li key={c.id} className="row">
                    <Link className="row-title" to={`/authors/${encodeURIComponent(c.id)}`}>
                      {c.name}
                    </Link>
                    <span className="row-meta">{c.shared_papers} shared</span>
                  </li>
                ))}
              </ul>
            </Section>
          )}
        </div>
      </div>
    </div>
  );
}
