import { lazy, Suspense } from "react";
import { Link } from "react-router-dom";

import {
  useGraphOverview,
  useInfluentialPapers,
  usePaperCommunities,
  usePapersPerYear,
  useSummary,
} from "../api/queries";
import type { GraphSummary } from "../api/types";
import { BarList, ColumnChart } from "../components/Charts";
import { BookIcon, DocIcon, LayersIcon, LinkIcon, TagIcon, UsersIcon } from "../components/Icons";
import { PageHeader } from "../components/PageHeader";
import { PaperList } from "../components/PaperList";
import { Empty, ErrorState, Loading } from "../components/StateViews";
import { useTokens } from "../graph/useTokens";
import { formatCount, formatTimestamp } from "../lib/format";

const GraphCanvas = lazy(() => import("../graph/GraphCanvas").then((m) => ({ default: m.GraphCanvas })));

function Tile({ label, value, icon }: { label: string; value: number; icon: React.ReactNode }) {
  return (
    <div className="card tile">
      <div className="tile-top">{icon}</div>
      <div className="tile-value">{formatCount(value)}</div>
      <div className="tile-label">{label}</div>
    </div>
  );
}

function SummaryTiles({ summary }: { summary: GraphSummary }) {
  return (
    <>
      <div className="tiles">
        <Tile label="Papers" value={summary.papers} icon={<DocIcon />} />
        <Tile label="Authors" value={summary.authors} icon={<UsersIcon />} />
        <Tile label="Citations" value={summary.citations} icon={<LinkIcon />} />
        <Tile label="Topics" value={summary.topics} icon={<TagIcon />} />
        <Tile label="Venues" value={summary.venues} icon={<BookIcon />} />
        <Tile label="Paper communities" value={summary.paper_communities} icon={<LayersIcon />} />
        <Tile label="Author communities" value={summary.author_communities} icon={<UsersIcon />} />
      </div>
      <p className="muted small">
        {summary.stub_papers > 0 && (
          <>
            {formatCount(summary.stub_papers)} additional papers are stubs: cited by an ingested paper but
            without fetched metadata.{" "}
          </>
        )}
        Analytics last computed: {formatTimestamp(summary.analytics_computed_at)}.
      </p>
    </>
  );
}

function GraphPreview() {
  const overview = useGraphOverview(40);
  const communities = usePaperCommunities();
  return (
    <section className="card" aria-labelledby="preview-heading">
      <div className="card-head">
        <h2 id="preview-heading">Citation graph</h2>
        <Link to="/graph">Open explorer →</Link>
      </div>
      <div className="card-body">
        {overview.isPending && <Loading label="Loading graph" />}
        {overview.isError && <ErrorState error={overview.error} onRetry={() => void overview.refetch()} />}
        {overview.data && overview.data.nodes.length > 0 && (
          <div className="embed embed--dash">
            <Suspense fallback={<Loading label="Loading graph" />}>
              <GraphCanvas
                view={overview.data}
                sizeBy="pagerank"
                colorBy="community"
                communities={communities.data}
                interactive={false}
                labelCount={6}
              />
            </Suspense>
          </div>
        )}
        {overview.data && overview.data.nodes.length === 0 && (
          <p className="muted">No papers to draw yet.</p>
        )}
        <p className="small faint">The 40 most influential papers by PageRank. Colour = research community.</p>
      </div>
    </section>
  );
}

function Communities() {
  const communities = usePaperCommunities();
  const tokens = useTokens();
  return (
    <section className="card" aria-labelledby="communities-heading">
      <div className="card-head">
        <h2 id="communities-heading">Research communities</h2>
      </div>
      <div className="card-body">
        {communities.isPending && <Loading />}
        {communities.isError && <ErrorState error={communities.error} onRetry={() => void communities.refetch()} />}
        {communities.data &&
          (communities.data.length === 0 ? (
            <p className="muted">
              No communities yet. Run <code>researchgraph analyze</code>.
            </p>
          ) : (
            <BarList
              unit="papers"
              data={communities.data.slice(0, 8).map((c) => ({
                key: c.id,
                label: c.label ?? `Community ${c.rank}`,
                value: c.size,
                colour: c.rank <= 7 ? (tokens.series[c.rank - 1] ?? tokens.other) : tokens.other,
                detail: c.top_topics.join(", "),
              }))}
            />
          ))}
      </div>
    </section>
  );
}

/** Every year in the range, so gaps show as empty columns and the axis stays evenly spaced. */
function fillYears(rows: readonly { year: number; papers: number }[]) {
  const counts = new Map(rows.map((r) => [r.year, r.papers]));
  const years = rows.map((r) => r.year);
  const out: { label: string; value: number }[] = [];
  for (let y = Math.min(...years); y <= Math.max(...years); y += 1) out.push({ label: String(y), value: counts.get(y) ?? 0 });
  return out;
}

function PerYear() {
  const years = usePapersPerYear();
  const tokens = useTokens();
  return (
    <section className="card" aria-labelledby="years-heading">
      <div className="card-head">
        <h2 id="years-heading">Papers per year</h2>
      </div>
      <div className="card-body">
        {years.isPending && <Loading />}
        {years.isError && <ErrorState error={years.error} onRetry={() => void years.refetch()} />}
        {years.data && years.data.length > 0 && (
          <ColumnChart
            data={fillYears(years.data)}
            colour={tokens.series[0] ?? tokens.accent}
            unit="papers"
            caption="Number of ingested papers by publication year"
          />
        )}
        {years.data?.length === 0 && <p className="muted">No dated papers yet.</p>}
      </div>
    </section>
  );
}

export function DashboardPage() {
  const summary = useSummary();
  const influential = useInfluentialPapers(10);

  return (
    <div className="stack">
      <PageHeader
        title="Dashboard"
        subtitle="An overview of the ingested citation graph: its size, structure and most central papers."
        actions={
          <Link className="btn btn-primary" to="/graph">
            Explore the graph
          </Link>
        }
      />

      {summary.isPending && <Loading label="Loading graph summary" />}
      {summary.isError && <ErrorState error={summary.error} onRetry={() => void summary.refetch()} />}
      {summary.data &&
        (summary.data.papers === 0 && summary.data.stub_papers === 0 ? (
          <Empty title="The graph is empty">
            Load the sample dataset with <code>researchgraph seed</code>, then run{" "}
            <code>researchgraph analyze</code>.
          </Empty>
        ) : (
          <SummaryTiles summary={summary.data} />
        ))}

      <div className="grid-2">
        <GraphPreview />
        <Communities />
      </div>
      <PerYear />

      <section className="card" aria-labelledby="influential-heading">
        <div className="card-head">
          <h2 id="influential-heading">Most structurally influential papers</h2>
          <Link to="/papers?sort=pagerank">All papers by PageRank →</Link>
        </div>
        <div className="card-body">
          {influential.isPending && <Loading label="Loading rankings" />}
          {influential.isError && (
            <ErrorState error={influential.error} onRetry={() => void influential.refetch()} />
          )}
          {influential.data && (
            <>
              <p className="note">{influential.data.note}</p>
              {influential.data.papers.length === 0 ? (
                <p className="muted">
                  No rankings yet. Run <code>researchgraph analyze</code> to compute them.
                </p>
              ) : (
                <PaperList papers={influential.data.papers.map((r) => r.paper)} showPagerank ranked />
              )}
            </>
          )}
        </div>
      </section>
    </div>
  );
}
