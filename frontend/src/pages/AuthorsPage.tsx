import { Link } from "react-router-dom";

import { useInfluentialAuthors } from "../api/queries";
import { PageHeader } from "../components/PageHeader";
import { plural } from "../lib/format";
import { Empty, ErrorState, Loading } from "../components/StateViews";

export function AuthorsPage() {
  const authors = useInfluentialAuthors(50);
  return (
    <div className="stack">
      <PageHeader title="Authors" subtitle="The most prolific authors in the ingested graph, by number of papers." />
      {authors.isPending && <Loading label="Loading authors" />}
      {authors.isError && <ErrorState error={authors.error} onRetry={() => void authors.refetch()} />}
      {authors.data && (
        <>
          <p className="note">{authors.data.note}</p>
          {authors.data.authors.length === 0 ? (
            <Empty title="No authors yet">Load data with <code>researchgraph seed</code>.</Empty>
          ) : (
            <div className="page-list">
              {authors.data.authors.map((a) => (
                <Link key={a.id} className="card link-card" to={`/authors/${encodeURIComponent(a.id)}`}>
                  <strong>{a.name}</strong>
                  <span>{plural(a.paper_count ?? 0, "paper")} in this graph</span>
                </Link>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}
