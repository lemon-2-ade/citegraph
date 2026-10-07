import { toApiError } from "./errors";

describe("toApiError", () => {
  it("reads the backend error envelope", () => {
    const err = toApiError(404, { error: { code: "not_found", message: "Paper x not found" } });
    expect(err.status).toBe(404);
    expect(err.code).toBe("not_found");
    expect(err.message).toBe("Paper x not found");
    expect(err.isNotFound).toBe(true);
  });

  it("maps FastAPI validation errors to a generic message without echoing input", () => {
    const err = toApiError(422, { detail: [{ loc: ["query", "page"], msg: "bad", input: "secret" }] });
    expect(err.code).toBe("validation_failed");
    expect(err.message).not.toContain("secret");
  });

  it("falls back for unknown bodies", () => {
    const err = toApiError(500, "<html>boom</html>");
    expect(err.code).toBe("http_error");
    expect(err.message).toContain("500");
  });
});
