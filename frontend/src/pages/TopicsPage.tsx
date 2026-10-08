import { Link } from "react-router-dom";

import { useTopics } from "../api/queries";
import { PageHeader } from "../components/PageHeader";
import { plural } from "../lib/format";
import { Empty, ErrorState, Loading } from "../components/StateViews";

export function TopicsPage() {
  const topics = useTopics();
  return (
    <div className="stack">
      <PageHeader title="Topics" subtitle="Research topics assigned to papers in the ingested graph." />
      {topics.isPending && <Loading label="Loading topics" />}
      {topics.isError && <ErrorState error={topics.error} onRetry={() => void topics.refetch()} />}
      {topics.data &&
        (topics.data.items.length === 0 ? (
          <Empty title="No topics yet">Load data with <code>researchgraph seed</code>.</Empty>
        ) : (
          <div className="page-list">
            {[...topics.data.items]
              .sort((a, b) => b.paper_count - a.paper_count || a.name.localeCompare(b.name))
              .map((t) => (
                <Link key={t.id} className="card link-card" to={`/topics/${encodeURIComponent(t.id)}`}>
                  <strong>{t.name}</strong>
                  <span>{plural(t.paper_count, "paper")}</span>
                </Link>
              ))}
          </div>
        ))}
    </div>
  );
}
