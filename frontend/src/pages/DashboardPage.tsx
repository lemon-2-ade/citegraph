import { Link } from "react-router-dom";

import { useInfluentialPapers, useSummary } from "../api/queries";
import type { GraphSummary } from "../api/types";
import { PaperList } from "../components/PaperList";
import { Empty, ErrorState, Loading } from "../components/StateViews";
import { formatCount, formatTimestamp } from "../lib/format";

function Tile({ label, value }: { label: string; value: number }) {
  return (
    <div className="tile">
      <div className="tile-value">{formatCount(value)}</div>
      <div className="tile-label">{label}</div>
    </div>
  );
}

function SummaryTiles({ summary }: { summary: GraphSummary }) {
  return (
    <>
      <div className="tiles">
        <Tile label="Papers" value={summary.papers} />
        <Tile label="Authors" value={summary.authors} />
        <Tile label="Citations" value={summary.citations} />
        <Tile label="Topics" value={summary.topics} />
        <Tile label="Venues" value={summary.venues} />
        <Tile label="Paper communities" value={summary.paper_communities} />
        <Tile label="Author communities" value={summary.author_communities} />
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

export function DashboardPage() {
  const summary = useSummary();
  const influential = useInfluentialPapers(10);

  return (
    <div className="stack">
      <h1>Dashboard</h1>

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

      <section className="card" aria-labelledby="influential-heading">
        <h2 id="influential-heading">Most structurally influential papers</h2>
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
              <PaperList papers={influential.data.papers.map((r) => r.paper)} showPagerank />
            )}
            <p className="small">
              <Link to="/papers?sort=pagerank">Browse all papers by PageRank</Link>
            </p>
          </>
        )}
      </section>
    </div>
  );
}
