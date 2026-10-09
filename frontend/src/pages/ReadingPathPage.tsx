import { Link, useSearchParams } from "react-router-dom";

import { useReadingPath, useTopics } from "../api/queries";
import { PageHeader } from "../components/PageHeader";
import { Empty, ErrorState, Loading } from "../components/StateViews";
import { formatAuthors, paperTitle } from "../lib/format";

export function ReadingPathPage() {
  const [params, setParams] = useSearchParams();
  const topicId = params.get("topic_id") ?? undefined;
  const paperId = params.get("paper_id") ?? undefined;
  const topics = useTopics();
  const path = useReadingPath({ topicId, paperId: topicId ? undefined : paperId }, 8);

  return (
    <div className="stack">
      <PageHeader
        title="Reading paths"
        subtitle="An order to read papers in: the work others build on comes first, the newer work after."
      />
      <div className="card filters">
        <label className="field">
          Topic
          <select
            value={topicId ?? ""}
            onChange={(e) => setParams(e.target.value ? { topic_id: e.target.value } : {})}
          >
            <option value="">Choose a topic…</option>
            {topics.data?.items.map((t) => (
              <option key={t.id} value={t.id}>
                {t.name}
              </option>
            ))}
          </select>
        </label>
        {paperId && !topicId && (
          <span className="muted small">
            Starting from a paper. <Link to="/reading-path">Clear</Link>
          </span>
        )}
      </div>
      {!topicId && !paperId && <Empty title="Pick a topic">Or open a paper and choose “Reading path from this paper”.</Empty>}
      {path.isPending && (topicId || paperId) && <Loading label="Building reading path" />}
      {path.isError && <ErrorState error={path.error} onRetry={() => void path.refetch()} />}
      {path.data && (
        <section className="card card-pad" aria-labelledby="path-heading">
          <h2 id="path-heading">{path.data.focus}</h2>
          {path.data.steps.length === 0 ? (
            <p className="muted">No papers found for this starting point.</p>
          ) : (
            <ol className="sources">
              {path.data.steps.map((s) => (
                <li key={s.paper.id} className="source">
                  <span className="source-n">{s.position}.</span>
                  <div>
                    <Link to={`/papers/${encodeURIComponent(s.paper.id)}`}>{paperTitle(s.paper.title)}</Link>
                    <div className="row-meta">
                      {formatAuthors(s.paper.authors)}
                      {s.paper.year != null && <> · {s.paper.year}</>}
                    </div>
                    <p className="small muted" style={{ margin: "4px 0 0" }}>
                      {s.reason}
                    </p>
                    {s.builds_on.length > 0 && <p className="small faint" style={{ margin: "2px 0 0" }}>Builds on: {s.builds_on.join("; ")}</p>}
                  </div>
                </li>
              ))}
            </ol>
          )}
          <p className="note small">
            Considered {path.data.candidates} papers. {path.data.note}
          </p>
        </section>
      )}
    </div>
  );
}
