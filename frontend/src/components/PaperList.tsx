import { Link } from "react-router-dom";

import type { PaperSummary } from "../api/types";
import { formatAuthors, formatCount, formatScore, paperTitle } from "../lib/format";

interface Props {
  papers: readonly PaperSummary[];
  /** Show the PageRank column (only meaningful once analytics have run). */
  showPagerank?: boolean;
}

export function PaperList({ papers, showPagerank = false }: Props) {
  return (
    <ul className="paper-list">
      {papers.map((paper) => (
        <li key={paper.id} className="paper-item">
          <Link className="paper-title" to={`/papers/${encodeURIComponent(paper.id)}`}>
            {paperTitle(paper.title)}
          </Link>{" "}
          {paper.is_stub && <span className="badge">stub</span>}
          <div className="paper-meta">
            {formatAuthors(paper.authors)}
            {paper.year != null && <> · {paper.year}</>}
            {paper.venue && <> · {paper.venue}</>}
          </div>
          <div className="paper-meta">
            Cited by {formatCount(paper.cited_by_in_graph)} in this graph
            {paper.citation_count != null && <> · {formatCount(paper.citation_count)} reported by source</>}
            {showPagerank && <> · PageRank {formatScore(paper.pagerank)}</>}
          </div>
        </li>
      ))}
    </ul>
  );
}
