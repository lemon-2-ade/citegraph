import { useState } from "react";
import { Link } from "react-router-dom";

import { useTopicTrends } from "../api/queries";
import type { TopicTrend } from "../api/types";
import { PageHeader } from "../components/PageHeader";
import { Empty, ErrorState, Loading } from "../components/StateViews";
import { plural } from "../lib/format";

const LABELS: Record<TopicTrend["label"], { text: string; symbol: string; help: string }> = {
  emerging: { text: "Emerging", symbol: "✦", help: "No papers in the earlier window, at least two in the recent one" },
  rising: { text: "Rising", symbol: "▲", help: "Share of papers grew by 1.5× or more" },
  steady: { text: "Steady", symbol: "●", help: "Share roughly unchanged" },
  declining: { text: "Declining", symbol: "▼", help: "Share fell to 0.67× or less" },
};

/** Tiny per-topic column chart over the whole year range; values are in the table too. */
function Spark({ trend, first, last }: { trend: TopicTrend; first: number; last: number }) {
  const byYear = new Map(trend.series.map((s) => [s.year, s.papers]));
  const years = Array.from({ length: last - first + 1 }, (_, i) => first + i);
  const max = Math.max(1, ...trend.series.map((s) => s.papers));
  const w = 6;
  return (
    <svg width={years.length * (w + 2)} height={28} role="img" aria-label={`${trend.name}: ${trend.series.map((s) => `${s.year} ${s.papers}`).join(", ")}`}>
      {years.map((y, i) => {
        const v = byYear.get(y) ?? 0;
        const h = v === 0 ? 1 : Math.max(2, (v / max) * 26);
        return <rect key={y} x={i * (w + 2)} y={28 - h} width={w} height={h} rx={1.5} fill="var(--accent)" opacity={v === 0 ? 0.25 : 1} />;
      })}
    </svg>
  );
}

export function TrendsPage() {
  const [windowYears, setWindow] = useState(3);
  const trends = useTopicTrends(windowYears);
  const data = trends.data;
  return (
    <div className="stack">
      <PageHeader
        title="Research trends"
        subtitle="Which topics are gaining or losing share of the papers in this graph, comparing the latest years to the years before."
      />
      <div className="card filters">
        <div className="seg" role="group" aria-label="Window length">
          {[2, 3, 5].map((w) => (
            <button key={w} type="button" aria-pressed={windowYears === w} onClick={() => setWindow(w)}>
              {w} years
            </button>
          ))}
        </div>
        {data && data.last_year != null && (
          <span className="muted small">
            Recent: {data.recent_years[0]}–{data.last_year} · Before: {data.previous_years[0]}–{data.previous_years[data.previous_years.length - 1]}
          </span>
        )}
      </div>
      {trends.isPending && <Loading label="Computing trends" />}
      {trends.isError && <ErrorState error={trends.error} onRetry={() => void trends.refetch()} />}
      {data &&
        (data.topics.length === 0 ? (
          <Empty title="Not enough data for trends">Topics need at least two dated papers. Run <code>researchgraph seed</code> or ingest more.</Empty>
        ) : (
          <section className="card card-pad" aria-labelledby="trends-heading">
            <h2 id="trends-heading">Topics</h2>
            <div className="scroll-x">
              <table className="tbl">
                <thead>
                  <tr>
                    <th scope="col">Topic</th>
                    <th scope="col">Trend</th>
                    <th scope="col" className="num">Recent</th>
                    <th scope="col" className="num">Before</th>
                    <th scope="col" className="num">Share change</th>
                    <th scope="col">By year</th>
                  </tr>
                </thead>
                <tbody>
                  {data.topics.map((t) => (
                    <tr key={t.topic_id}>
                      <td>
                        <Link to={`/topics/${encodeURIComponent(t.topic_id)}`}>{t.name}</Link>
                        <div className="small faint">{plural(t.total, "paper")} in total</div>
                      </td>
                      <td title={LABELS[t.label].help}>
                        <span aria-hidden="true">{LABELS[t.label].symbol}</span> {LABELS[t.label].text}
                      </td>
                      <td className="num">{t.recent}</td>
                      <td className="num">{t.previous}</td>
                      <td className="num">{t.growth.toFixed(2)}×</td>
                      <td>
                        <Spark trend={t} first={data.first_year ?? 0} last={data.last_year ?? 0} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="note small">{data.note}</p>
          </section>
        ))}
    </div>
  );
}
