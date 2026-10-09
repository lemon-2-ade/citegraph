import { Link, useParams } from "react-router-dom";

import { useTopic } from "../api/queries";
import { ColumnChart, yearColumns } from "../components/Charts";
import { PageHeader } from "../components/PageHeader";
import { PaperList } from "../components/PaperList";
import { Section } from "../components/Section";
import { Empty, ErrorState, Loading } from "../components/StateViews";
import { plural } from "../lib/format";
import { useTokens } from "../graph/useTokens";

export function TopicDetailPage() {
  const { topicId = "" } = useParams();
  const topic = useTopic(topicId);
  const tokens = useTokens();

  if (topic.isPending) return <Loading label="Loading topic" />;
  if (topic.isError) {
    if ("isNotFound" in topic.error && topic.error.isNotFound === true) {
      return (
        <Empty title="Topic not found">
          <Link to="/topics">Back to topics</Link>
        </Empty>
      );
    }
    return <ErrorState error={topic.error} onRetry={() => void topic.refetch()} />;
  }
  const t = topic.data;
  const years = yearColumns(t.papers_per_year);
  return (
    <div className="stack">
      <PageHeader
        title={t.name}
        subtitle={t.description ?? `${t.paper_count} papers carry this topic.`}
        actions={<Link to={`/reading-path?topic_id=${encodeURIComponent(t.id)}`}>Reading path →</Link>}
      />
      {years.length > 0 && (
        <Section id="topic-years" title="Papers per year">
          <ColumnChart
            data={years}
            colour={tokens.series[0] ?? tokens.accent}
            unit="papers"
            caption={`Papers on ${t.name} by publication year`}
          />
        </Section>
      )}
      <div className="two-col">
        <Section id="topic-papers" title="Most influential papers in this topic">
          {t.top_papers.length === 0 ? (
            <p className="muted">No papers.</p>
          ) : (
            <PaperList papers={t.top_papers} showPagerank />
          )}
        </Section>
        <div className="stack">
          {t.top_authors.length > 0 && (
            <Section id="topic-authors" title="Most active authors">
              <ul className="rows">
                {t.top_authors.map((a) => (
                  <li key={a.id} className="row">
                    <Link className="row-title" to={`/authors/${encodeURIComponent(a.id)}`}>
                      {a.name}
                    </Link>
                    <span className="row-meta">{plural(a.paper_count, "paper")}</span>
                  </li>
                ))}
              </ul>
            </Section>
          )}
          {t.related_topics.length > 0 && (
            <Section id="topic-related" title="Related topics">
              <div className="chips">
                {t.related_topics.map((r) => (
                  <Link key={r.id} className="chip" to={`/topics/${encodeURIComponent(r.id)}`}>
                    {r.name} · {r.shared_papers}
                  </Link>
                ))}
              </div>
            </Section>
          )}
        </div>
      </div>
    </div>
  );
}
