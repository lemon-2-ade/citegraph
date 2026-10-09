import json
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.ai.llm import LLMCache
from app.core.config import Settings
from app.core.limits import SlidingWindowLimiter
from app.main import create_app
from tests.fakes import ScriptedGraph, ScriptedLLM


def _settings(**kw: Any) -> Settings:
    return Settings(log_json=False, _env_file=None, **kw)  # type: ignore[call-arg]


def _client(settings: Settings, graph: ScriptedGraph | None = None) -> TestClient:
    app = create_app(settings)
    app.state.graph = graph or ScriptedGraph()
    app.state.llm = LLMCache(settings, ScriptedLLM([json.dumps({"summary": "S."})] * 20))
    return TestClient(app)


def test_limiter_window_and_retry_after() -> None:
    now = [0.0]
    limiter = SlidingWindowLimiter(clock=lambda: now[0])
    assert [limiter.check("a", "x", 2) for _ in range(2)] == [0.0, 0.0]
    assert limiter.check("a", "x", 2) == pytest.approx(60.0)
    assert limiter.check("b", "x", 2) == 0.0  # other clients are independent
    now[0] = 61.0
    assert limiter.check("a", "x", 2) == 0.0  # the window slid


def test_ai_endpoints_have_a_stricter_limit_than_ordinary_ones() -> None:
    client = _client(_settings(rate_limit_ai_per_minute=2, rate_limit_per_minute=100))
    body = {"question": "what is attention?"}
    statuses = [client.post("/api/ask", json=body).status_code for _ in range(4)]
    assert statuses[2:] == [429, 429]
    blocked = client.post("/api/ask", json=body)
    assert int(blocked.headers["retry-after"]) >= 1
    assert blocked.json()["error"]["code"] == "rate_limited"
    assert (
        "x-request-id" in blocked.headers and blocked.headers["x-content-type-options"] == "nosniff"
    )
    # Ordinary reads are unaffected by the AI bucket.
    assert client.get("/api/analytics/years").status_code != 429


def test_health_checks_are_never_limited() -> None:
    client = _client(_settings(rate_limit_per_minute=1))
    assert all(client.get("/api/health").status_code == 200 for _ in range(5))


def test_rate_limit_can_be_disabled() -> None:
    client = _client(_settings(rate_limit_enabled=False, rate_limit_ai_per_minute=1))
    assert all(
        client.post("/api/ask", json={"question": "attention?"}).status_code != 429
        for _ in range(3)
    )


def test_forwarded_for_is_ignored_unless_trusted() -> None:
    def run(trust: bool) -> list[int]:
        client = _client(_settings(rate_limit_per_minute=2, trust_forwarded_for=trust))
        return [
            client.get(
                "/api/analytics/years", headers={"X-Forwarded-For": f"10.0.0.{i}"}
            ).status_code
            for i in range(4)
        ]

    assert 429 in run(False)  # spoofing the header does not buy a fresh bucket
    assert 429 not in run(True)  # a trusted proxy's per-client addresses are separate buckets


def test_oversized_bodies_are_rejected() -> None:
    client = _client(_settings(max_request_bytes=100))
    res = client.post("/api/ask", content=b'{"question": "' + b"x" * 500 + b'"}',
                      headers={"content-type": "application/json"})  # fmt: skip
    assert res.status_code == 413 and res.json()["error"]["code"] == "payload_too_large"
    ok = client.post("/api/ask", json={"question": "short one"})
    assert ok.status_code != 413


def test_security_headers_and_hsts_only_in_production() -> None:
    dev = _client(_settings()).get("/api/health")
    assert dev.headers["content-security-policy"] == "default-src 'none'; frame-ancestors 'none'"
    assert (
        dev.headers["cache-control"] == "no-store"
        and "strict-transport-security" not in dev.headers
    )
    prod = _client(_settings(app_env="production")).get("/api/health")
    assert "max-age=" in prod.headers["strict-transport-security"]
    docs = _client(_settings()).get("/api/docs")
    assert "content-security-policy" not in docs.headers


def test_cors_allows_only_listed_origin_methods_and_headers() -> None:
    client = _client(_settings(cors_origins=["http://localhost:5173"]))
    ok = client.options("/api/papers", headers={
        "Origin": "http://localhost:5173", "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "x-admin-token"})  # fmt: skip
    assert ok.headers["access-control-allow-origin"] == "http://localhost:5173"
    bad = client.options("/api/papers", headers={
        "Origin": "http://evil.example", "Access-Control-Request-Method": "GET"})  # fmt: skip
    assert "access-control-allow-origin" not in bad.headers
    delete = client.options("/api/papers", headers={
        "Origin": "http://localhost:5173", "Access-Control-Request-Method": "DELETE"})  # fmt: skip
    assert delete.status_code == 400


@pytest.mark.parametrize(
    "settings, token, expected",
    [
        ({}, None, True),  # development without a token: open
        ({"app_env": "production"}, None, False),  # production without a token: disabled
        ({"admin_api_token": "s3cret"}, None, False),
        ({"admin_api_token": "s3cret"}, "wrong", False),
        ({"admin_api_token": "s3cret"}, "s3cret", True),
        ({"app_env": "production", "public_ai": True}, None, True),  # explicit opt-in
    ],
)
def test_ai_access_rules(settings: dict[str, Any], token: str | None, expected: bool) -> None:
    client = _client(_settings(rate_limit_enabled=False, **settings))
    headers = {"X-Admin-Token": token} if token else {}
    res = client.post("/api/ask", json={"question": "attention?"}, headers=headers)
    assert (res.status_code not in {401, 403}) is expected


def test_secrets_never_appear_in_settings_repr() -> None:
    s = _settings(openai_api_key="sk-very-secret", admin_api_token="tok-secret",
                  neo4j_password="pw-secret")  # fmt: skip
    text = repr(s) + str(s.model_dump())
    for secret in ("sk-very-secret", "tok-secret", "pw-secret"):
        assert secret not in text
