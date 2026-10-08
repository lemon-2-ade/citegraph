import { Link, useParams } from "react-router-dom";

import { useCommunity } from "../api/queries";
import { ColumnChart, yearColumns } from "../components/Charts";
import { PageHeader } from "../components/PageHeader";
import { PaperList } from "../components/PaperList";
import { Section } from "../components/Section";
import { Empty, ErrorState, Loading } from "../components/StateViews";
import { plural } from "../lib/format";
import { useTokens } from "../graph/useTokens";

export function CommunityDetailPage() {
  const { communityId = "" } = useParams();
  const community = useCommunity(communityId);
  const tokens = useTokens();

  if (community.isPending) return <Loading label="Loading community" />;
  if (community.isError) {
    if ("isNotFound" in community.error && community.error.isNotFound === true) {
      return (
        <Empty title="Community not found">
          <Link to="/communities">Back to communities</Link>
        </Empty>
      );
    }
    return <ErrorState error={community.error} onRetry={() => void community.refetch()} />;
  }
  const c = community.data;
  const colour =
    c.scope === "papers" && c.rank <= 7 ? (tokens.series[c.rank - 1] ?? tokens.other) : (tokens.series[0] ?? tokens.other);
  const years = yearColumns(c.papers_per_year);
  const unit = c.scope === "papers" ? "papers" : "authors";
  return (
    <div className="stack">
      <PageHeader
        title={c.label ?? `Community ${c.rank}`}
        subtitle={
          <>
            <span className="dot" style={{ background: colour, marginRight: 8 }} aria-hidden="true" />
            {c.size} {unit} · detected with {c.algorithm}
          </>
        }
        actions={<Link className="btn" to="/communities">All communities</Link>}
      />
      {c.top_topics.length > 0 && (
        <div className="chips">
          {c.top_topics.map((t) => (
            <span key={t} className="chip chip-accent">
              {t}
            </span>
          ))}
        </div>
      )}
      {years.length > 0 && (
        <Section id="community-years" title="Papers per year">
          <ColumnChart data={years} colour={colour} unit="papers" caption="Papers in this community by publication year" />
        </Section>
      )}
      <div className="two-col">
        {c.top_papers.length > 0 && (
          <Section id="community-papers" title="Most influential papers">
            <PaperList papers={c.top_papers} showPagerank />
          </Section>
        )}
        <div className="stack">
          {c.top_authors.length > 0 && (
            <Section id="community-authors" title="Most active authors">
              <ul className="rows">
                {c.top_authors.map((a) => (
                  <li key={a.id ?? a.name} className="row">
                    {a.id ? (
                      <Link className="row-title" to={`/authors/${encodeURIComponent(a.id)}`}>
                        {a.name}
                      </Link>
                    ) : (
                      <span className="row-title">{a.name}</span>
                    )}
                    <span className="row-meta">{plural(a.count, "paper")}</span>
                  </li>
                ))}
              </ul>
            </Section>
          )}
          {c.connections.length > 0 && (
            <Section id="community-links" title="Citation links to other communities">
              <ul className="rows">
                {c.connections.map((l) => (
                  <li key={l.community_id} className="row">
                    <Link className="row-title" to={`/communities/${encodeURIComponent(l.community_id)}`}>
                      {l.label ?? l.community_id}
                    </Link>
                    <span className="row-meta">
                      {l.citations_out} cited · {l.citations_in} citing
                    </span>
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
