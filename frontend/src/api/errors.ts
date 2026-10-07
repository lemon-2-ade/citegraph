/** A failed API call, normalised from the backend's error envelope. */
export class ApiError extends Error {
  readonly status: number;
  readonly code: string;

  constructor(status: number, code: string, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }

  get isNotFound(): boolean {
    return this.status === 404;
  }
}

interface DomainErrorBody {
  error: { code: string; message: string };
}

function isDomainError(body: unknown): body is DomainErrorBody {
  if (typeof body !== "object" || body === null || !("error" in body)) return false;
  const err = (body as { error: unknown }).error;
  return (
    typeof err === "object" &&
    err !== null &&
    typeof (err as { code?: unknown }).code === "string" &&
    typeof (err as { message?: unknown }).message === "string"
  );
}

/** Turn an error body (domain error, FastAPI validation error or unknown) into an ApiError. */
export function toApiError(status: number, body: unknown): ApiError {
  if (isDomainError(body)) return new ApiError(status, body.error.code, body.error.message);
  if (typeof body === "object" && body !== null && "detail" in body) {
    return new ApiError(status, "validation_failed", "The request parameters were not valid.");
  }
  return new ApiError(status, "http_error", `The API returned an error (HTTP ${status}).`);
}
