import type { ReactNode } from "react";

import { ApiError } from "../api/errors";

export function Loading({ label = "Loading" }: { label?: string }) {
  return (
    <div role="status" aria-live="polite">
      <span className="muted">{label}…</span>
      <div className="skeleton" style={{ width: "70%" }} />
      <div className="skeleton" style={{ width: "50%" }} />
    </div>
  );
}

export function ErrorState({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const message = error instanceof ApiError ? error.message : "Something went wrong.";
  return (
    <div role="alert" className="card card-pad">
      <p className="error" style={{ marginTop: 0 }}>
        {message}
      </p>
      {onRetry && (
        <button type="button" className="btn" onClick={onRetry}>
          Try again
        </button>
      )}
    </div>
  );
}

export function Empty({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="card empty">
      <strong>{title}</strong>
      {children && <div className="muted">{children}</div>}
    </div>
  );
}
