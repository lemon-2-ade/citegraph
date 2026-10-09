import { type FormEvent, useState } from "react";

import { useGraphQuery } from "../api/queries";
import type { NLQueryResponse } from "../api/types";
import { PageHeader } from "../components/PageHeader";
import { ErrorState, Loading } from "../components/StateViews";

const EXAMPLES = [
  "Who are the most influential authors?",
  "How many papers per year are about graphs?",
  "Which papers cite the most papers in the graph?",
];

function cell(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function Result({ data }: { data: NLQueryResponse }) {
  if (!data.answerable) {
    return (
      <div className="card card-pad">
        <p className="note">{data.message}</p>
      </div>
    );
  }
  return (
    <div className="stack">
      <section className="card card-pad" aria-labelledby="query-result-heading">
        <h2 id="query-result-heading">Result</h2>
        {data.explanation && <p className="muted">{data.explanation}</p>}
        {data.rows.length === 0 ? (
          <p className="muted">The query ran but returned no rows.</p>
        ) : (
          <div className="scroll-x">
            <table className="tbl">
              <caption className="sr-only">Query result, {data.row_count} rows</caption>
              <thead>
                <tr>
                  {data.columns.map((c) => (
                    <th key={c} scope="col">
                      {c}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {data.rows.map((row, i) => (
                  <tr key={i}>
                    {data.columns.map((c) => (
                      <td key={c}>{cell(row[c])}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {data.truncated && (
          <p className="note small">Showing the first {data.row_count} rows; there may be more.</p>
        )}
      </section>
      <section className="card card-pad" aria-labelledby="cypher-heading">
        <h2 id="cypher-heading">The query that was run</h2>
        <pre className="code">{data.cypher}</pre>
        <p className="small faint">
          Written by {data.model}
          {data.attempts > 1 && " after one rejected draft"}. Checked to be read-only and run with a
          time limit and row cap. Read it to confirm it answers what you meant.
        </p>
      </section>
    </div>
  );
}

export function QueryPage() {
  const [question, setQuestion] = useState("");
  const query = useGraphQuery();
  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    const text = question.trim();
    if (text.length >= 3) query.mutate(text);
  };
  return (
    <div className="stack">
      <PageHeader
        title="Query the graph"
        subtitle="Ask about counts, rankings and relationships in plain English. The generated Cypher is shown with the result."
      />
      <form className="card filters" onSubmit={onSubmit}>
        <label className="field" style={{ flex: 1, minWidth: 260 }}>
          Question
          <input
            type="text"
            maxLength={500}
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            placeholder="e.g. Who are the most influential authors?"
          />
        </label>
        <button type="submit" className="btn btn-primary" disabled={query.isPending || question.trim().length < 3}>
          {query.isPending ? "Running…" : "Run"}
        </button>
      </form>
      {!query.data && !query.isPending && !query.isError && (
        <div className="card card-pad">
          <p className="muted">Try one of these:</p>
          <div className="chips">
            {EXAMPLES.map((e) => (
              <button key={e} type="button" className="chip chip-button" onClick={() => setQuestion(e)}>
                {e}
              </button>
            ))}
          </div>
        </div>
      )}
      {query.isPending && <Loading label="Writing and running the query" />}
      {query.isError && <ErrorState error={query.error} />}
      {query.data && <Result data={query.data} />}
    </div>
  );
}
