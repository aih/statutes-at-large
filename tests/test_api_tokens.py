"""API tokens (ADR-0038): a bearer token keys a caller's budgets on its name
and scales them; an unknown one is a 401."""

import hashlib

import pytest
from fastapi import HTTPException, Request

import params
from params import client_key, parse_api_tokens, rate_limit

TOKEN = "stat_test-token"


def _request(token: str | None = None, client=("47.82.52.29", 1234)) -> Request:
    headers = [(b"authorization", f"Bearer {token}".encode())] if token else []
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/v1/us/pl/81/740/s3",
            "query_string": b"",
            "headers": headers,
            "client": client,
        }
    )


@pytest.fixture
def a_token(monkeypatch):
    digest = hashlib.sha256(TOKEN.encode()).hexdigest()
    monkeypatch.setattr(
        params, "API_TOKENS", parse_api_tokens(f'{{"reintro": {{"sha256": "{digest}", "scale": 4}}}}')
    )
    return TOKEN


def test_a_token_scales_the_budget_and_keys_it_on_the_token(a_token):
    limit = rate_limit("t-token", capacity=2, per_second=0.01)
    assert client_key(_request(a_token)) == "token:reintro"

    for _ in range(8):  # 2 x scale 4
        limit(_request(a_token))
    with pytest.raises(HTTPException) as refused:
        limit(_request(a_token))
    assert refused.value.status_code == 429

    # The same address without the token has its own two.
    limit(_request())
    limit(_request())


def test_the_same_token_shares_one_bucket_across_addresses(a_token):
    limit = rate_limit("t-token-addresses", capacity=1, per_second=0.01)
    for i in range(4):
        limit(_request(a_token, client=(f"47.82.52.{i}", 1)))
    with pytest.raises(HTTPException):
        limit(_request(a_token, client=("39.109.2.7", 1)))


def test_an_unknown_token_is_refused(a_token):
    limit = rate_limit("t-token-unknown", capacity=100, per_second=1.0)
    with pytest.raises(HTTPException) as refused:
        limit(_request("stat_not-a-token"))
    assert refused.value.status_code == 401
    assert refused.value.headers["WWW-Authenticate"].startswith("Bearer")


def test_an_unknown_token_is_a_401_on_a_limited_route(client, a_token):
    response = client.get("/api/v1/us/pl/81/740", headers={"Authorization": "Bearer stat_wrong"})
    assert response.status_code == 401


def test_another_scheme_is_ignored(a_token):
    request = Request({"type": "http", "headers": [(b"authorization", b"Basic dXNlcjpwdw==")],
                       "client": ("47.82.52.29", 1)})
    assert client_key(request) == "47.82.52.29"


def test_the_tokens_setting_is_checked_at_start_up():
    assert parse_api_tokens("") == {}
    with pytest.raises(ValueError):
        parse_api_tokens('{"x": {"sha256": "abc"}}')
    with pytest.raises(ValueError):
        parse_api_tokens('{"x": {"sha256": "' + "0" * 64 + '", "scale": 0.5}}')
    token = parse_api_tokens('{"x": {"sha256": "' + "A" * 64 + '"}}')
    assert next(iter(token.values())).scale == 10
