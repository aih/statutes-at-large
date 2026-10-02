# ADR-0029: OpenTelemetry from FastAPI to Grafana Cloud

Date: 2026-10-02. Status: accepted. The US Code site makes the same change
under its ADR-0089; both export to one stack, told apart by service name.

## Context

The box's monitoring is CloudWatch: the watchdog, `statutes-site-down` and
`statutes-disk-high`, mailed through the `statutes-alerts` SNS topic. None of
it says which routes are called, how long they take, or which raise.

FastAPI 0.142.0 added built-in OpenTelemetry (`FastAPI(telemetry=...)`): a
server span per request with child spans for dependency resolution, the
endpoint, serialization and background tasks; the
`http.server.request.duration` histogram and `http.server.active_requests`;
and log records for unhandled exceptions (with stack traces) and validation
failures (route and error count). It adds OTLP/HTTP exporters at lifespan
startup when `OTEL_EXPORTER_OTLP_ENDPOINT` is set and does nothing when it is
not. Spans carry `url.path` and `url.query`; no attribute carries the client
address or User-Agent. This repository locked 0.141.1, which has no
`fastapi.telemetry` module.

## Decision

1. `fastapi[opentelemetry]>=0.142.2`. `main.py` passes
   `telemetry={"exclude": _untraced}`, which skips `/health`.
2. The api exports directly to the US Code site's Grafana Cloud stack over
   OTLP/HTTP, as `statutes-api`. No collector runs on the box, so nothing new
   joins the `uscode-redesign_default` network (gotcha 14).
   `docker-compose.prod.yml` sets the service name, the deployment
   environment and the image tag, `parentbased_traceidratio` at 0.25, and a
   60 s metric interval; the endpoint and its `Authorization` header come from
   `.env`.
3. Traces are sampled at 25%. Metrics and logs are not sampled.

## Consequences

- `make test` and the dev stack export nothing; `tests/test_telemetry.py`
  checks the route template on the server span and the `/health` exclusion
  against an in-memory exporter.
- Requests the edge answers itself never reach FastAPI and are not counted.
  Database and search calls appear only as time inside the endpoint span.
- Peak RSS of `main:app` serving one request locally is 94 MB without an
  endpoint and 98 MB with one, against the api's `mem_limit: 512m`.
