import { Link } from "react-router-dom";

import type { PaperSummary } from "../api/types";
import { formatAuthors, formatCount, formatScore, paperTitle } from "../lib/format";

interface Props {
  papers: readonly PaperSummary[];
  /** Show the PageRank value and meter (only meaningful once analytics have run). */
  showPagerank?: boolean;
  /** Number the rows, for ranked lists. */
  ranked?: boolean;
}

export function PaperList({ papers, showPagerank = false, ranked = false }: Props) {
  const top = Math.max(0, ...papers.map((p) => p.pagerank ?? 0));
  return (
    <ul className="rows">
      {papers.map((paper, i) => (
        <li key={paper.id} className={ranked ? "row row--ranked" : "row"}>
          {ranked && <span className="row-rank">{i + 1}</span>}
          <div>
            <Link className="row-title" to={`/papers/${encodeURIComponent(paper.id)}`}>
              {paperTitle(paper.title)}
            </Link>
            {paper.is_stub && <span className="chip">stub</span>}
            <div className="row-meta">
              {formatAuthors(paper.authors)}
              {paper.year != null && <> · {paper.year}</>}
              {paper.venue && <> · {paper.venue}</>}
            </div>
          </div>
          <div className="row-side">
            <span>Cited by {formatCount(paper.cited_by_in_graph)} in this graph</span>
            {paper.citation_count != null && <span>{formatCount(paper.citation_count)} reported by source</span>}
            {showPagerank && (
              <>
                <span>PageRank {formatScore(paper.pagerank)}</span>
                <span className="meter" aria-hidden="true">
                  <span style={{ width: `${top > 0 ? ((paper.pagerank ?? 0) / top) * 100 : 0}%` }} />
                </span>
              </>
            )}
          </div>
        </li>
      ))}
    </ul>
  );
}
