import { useEffect, useId, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";

import { useSearch } from "../api/queries";

type Hit = { id: string; title: string; subtitle?: string | null };

const GROUPS = [
  { key: "papers", label: "Papers", base: "/papers" },
  { key: "authors", label: "Authors", base: "/authors" },
  { key: "topics", label: "Topics", base: "/topics" },
] as const;

function useDebounced(value: string, ms: number): string {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return debounced;
}

export function SearchBox() {
  const [text, setText] = useState("");
  const [open, setOpen] = useState(false);
  const debounced = useDebounced(text, 200);
  const results = useSearch(debounced);
  const listId = useId();
  const root = useRef<HTMLDivElement>(null);
  const navigate = useNavigate();

  useEffect(() => {
    const onDown = (e: MouseEvent) => {
      if (root.current && !root.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, []);

  const data = results.data;
  const total = data ? data.papers.length + data.authors.length + data.topics.length : 0;
  const show = open && text.trim().length >= 2;

  return (
    <div className="search" ref={root} role="search">
      <input
        type="search"
        value={text}
        placeholder="Search…"
        aria-label="Search papers, authors and topics"
        aria-controls={listId}
        aria-expanded={show}
        onChange={(e) => {
          setText(e.target.value);
          setOpen(true);
        }}
        onFocus={() => setOpen(true)}
        onKeyDown={(e) => {
          if (e.key === "Escape") setOpen(false);
          if (e.key === "Enter" && text.trim().length >= 2) {
            setOpen(false);
            navigate(`/search?q=${encodeURIComponent(text.trim())}`);
          }
        }}
      />
      {show && (
        <div className="search-pop card" id={listId}>
          {results.isPending && debounced.trim().length >= 2 && <p className="small muted">Searching…</p>}
          {results.isError && <p className="small error">Search is unavailable right now.</p>}
          {data && total === 0 && <p className="small muted">No matches for “{data.query}”.</p>}
          {data &&
            GROUPS.map((g) => {
              const hits: readonly Hit[] = data[g.key];
              return hits.length === 0 ? null : (
                <div key={g.key}>
                  <div className="search-group">{g.label}</div>
                  {hits.map((h) => (
                    <Link key={h.id} to={`${g.base}/${encodeURIComponent(h.id)}`} className="search-hit" onClick={() => setOpen(false)}>
                      <span>{h.title}</span>
                      {h.subtitle && <small>{h.subtitle}</small>}
                    </Link>
                  ))}
                </div>
              );
            })}
          <Link to={`/search?q=${encodeURIComponent(text.trim())}`} className="search-hit" onClick={() => setOpen(false)}>
            <span>Search papers by meaning too →</span>
            <small>Press Enter for keyword, meaning and hybrid results</small>
          </Link>
        </div>
      )}
    </div>
  );
}
