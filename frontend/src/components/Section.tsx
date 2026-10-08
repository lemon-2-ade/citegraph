import type { ReactNode } from "react";

/** A titled card; the heading labels the region for assistive technology. */
export function Section({
  id,
  title,
  action,
  children,
}: {
  id: string;
  title: string;
  action?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="card" aria-labelledby={id}>
      <div className="card-head">
        <h2 id={id}>{title}</h2>
        {action}
      </div>
      <div className="card-body">{children}</div>
    </section>
  );
}

/** Renders a query's loading and error states, or the data once it exists. */
export function QueryBoundary<T>({
  query,
  children,
}: {
  query: { isPending: boolean; isError: boolean; error: unknown; data: T | undefined; refetch: () => unknown };
  children: (data: T) => ReactNode;
}) {
  if (query.isPending) return <div role="status" className="skeleton" style={{ width: "60%" }} />;
  if (query.isError)
    return (
      <div role="alert">
        <p className="error">Could not load this section.</p>
        <button type="button" className="btn btn-sm" onClick={() => void query.refetch()}>
          Try again
        </button>
      </div>
    );
  return query.data === undefined ? null : <>{children(query.data)}</>;
}
