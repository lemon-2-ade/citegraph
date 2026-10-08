import { useState } from "react";
import { Link } from "react-router-dom";

import { useCommunities } from "../api/queries";
import { BarList } from "../components/Charts";
import { PageHeader } from "../components/PageHeader";
import { Section } from "../components/Section";
import { Empty, ErrorState, Loading } from "../components/StateViews";
import { useTokens } from "../graph/useTokens";

export function CommunitiesPage() {
  const [scope, setScope] = useState<"papers" | "authors">("papers");
  const communities = useCommunities(scope);
  const tokens = useTokens();
  return (
    <div className="stack">
      <PageHeader
        title="Communities"
        subtitle="Groups of papers (by citation links) or authors (by co-authorship) that are more densely connected to each other than to the rest of the graph."
        actions={
          <div className="seg" role="group" aria-label="Community type">
            <button type="button" aria-pressed={scope === "papers"} onClick={() => setScope("papers")}>
              Paper communities
            </button>
            <button type="button" aria-pressed={scope === "authors"} onClick={() => setScope("authors")}>
              Author communities
            </button>
          </div>
        }
      />
      {communities.isPending && <Loading label="Loading communities" />}
      {communities.isError && <ErrorState error={communities.error} onRetry={() => void communities.refetch()} />}
      {communities.data &&
        (communities.data.length === 0 ? (
          <Empty title="No communities yet">
            Run <code>researchgraph analyze</code> to detect them.
          </Empty>
        ) : (
          <>
            <Section id="community-sizes" title="Largest communities">
              <BarList
                unit={scope === "papers" ? "papers" : "authors"}
                data={communities.data.slice(0, 8).map((c) => ({
                  key: c.id,
                  label: c.label ?? `Community ${c.rank}`,
                  value: c.size,
                  colour: scope === "papers" && c.rank <= 7 ? (tokens.series[c.rank - 1] ?? tokens.other) : tokens.series[0] ?? tokens.other,
                }))}
              />
            </Section>
            <div className="page-list">
              {communities.data.map((c) => (
                <Link key={c.id} className="card link-card" to={`/communities/${encodeURIComponent(c.id)}`}>
                  <strong>{c.label ?? `Community ${c.rank}`}</strong>
                  <span>
                    {c.size} {scope} · {c.top_topics.slice(0, 3).join(", ") || "no dominant topic"}
                  </span>
                </Link>
              ))}
            </div>
          </>
        ))}
    </div>
  );
}
