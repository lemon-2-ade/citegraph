import { Link } from "react-router-dom";

import { usePaper } from "../api/queries";
import { formatCount, formatScore, paperTitle } from "../lib/format";
import type { GraphNode } from "./types";

interface Props {
  node: GraphNode;
  focused: boolean;
  onFocus: (id: string) => void;
  colour: string;
}

export function SelectionPanel({ node, focused, onFocus, colour }: Props) {
  const detail = usePaper(node.id);
  const abstract = detail.data?.abstract;
  return (
    <section className="stack" aria-label="Selected paper">
      <div>
        <h2>{paperTitle(node.title)}</h2>
        <p className="row-meta">
          {node.authors.join(", ") || "Unknown authors"}
          {node.year != null && <> · {node.year}</>}
        </p>
      </div>
      <p className="small">
        <span className="dot" style={{ background: colour, marginRight: 8 }} aria-hidden="true" />
        {node.community_label ?? "Not in a large community"}
      </p>
      <dl className="kv">
        <dt>Cited by (in this graph)</dt>
        <dd>{formatCount(node.cited_by_in_graph)}</dd>
        <dt>PageRank</dt>
        <dd>{formatScore(node.pagerank)}</dd>
      </dl>
      {node.is_stub && <p className="note small">Stub: cited by ingested papers, metadata not fetched.</p>}
      {/* Source text is untrusted: plain text only. */}
      {abstract && <p className="small muted">{abstract.length > 360 ? `${abstract.slice(0, 359).trimEnd()}…` : abstract}</p>}
      <div className="chips">
        <Link className="btn btn-primary btn-sm" to={`/papers/${encodeURIComponent(node.id)}`}>
          Open paper
        </Link>
        {!focused && (
          <button type="button" className="btn btn-sm" onClick={() => onFocus(node.id)}>
            Focus neighbourhood
          </button>
        )}
      </div>
    </section>
  );
}
