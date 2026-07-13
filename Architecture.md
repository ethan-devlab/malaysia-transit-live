# Malaysia Transit Live Architecture

## 1. Purpose and Scope

Malaysia Transit Live is an independent, public, English-language transit information website built with Django and React. It uses Malaysia's Official Open API as its upstream source and must visibly attribute that source without implying government affiliation.

The product has a **full-Malaysia static-data foundation** and a **KL/Klang Valley-first live experience**. It provides search and deep-linkable route, stop, and scheduled-trip pages. Every scheduled trip view must show the mode, route, origin, destination, service date, planned start/end time, calling stops, and the current data-quality state.

Out of scope for v1:

- Journey planning and transfer recommendations.
- Estimated arrival times.
- User accounts, cross-device sync, behavioural analytics, or location retention.
- Service alerts and trip updates, unless the upstream API adds them and the data contract is extended deliberately.

## 2. Upstream Facts and Product Rules

| Source | Contract | Product rule |
| --- | --- | --- |
| GTFS Static | ZIP feeds contain schedules, stops, routes, trips, stop times, calendars, and optional GTFS files. | Static GTFS is the authority for route, origin, destination, timetable, and service-date information. |
| GTFS Realtime | The official service currently exposes Vehicle Positions protobuf feeds only. | A vehicle can be marked live only after a valid, fresh vehicle-position record is decoded and linked to a feed. |
| Rate limit | GTFS Static and GTFS Realtime are limited to 4 requests/minute. | No browser calls the government API. Django owns all upstream access through a Redis-backed, shared 15-second request gate per upstream API class. |

The implementation must support all current official static agencies and Prasarana categories through a feed registry. It must not assume that a realtime feed exists whenever a static feed exists. In particular, `rapid-rail-kl` is scheduled-only until its realtime feed becomes stable.

Authoritative references:

- [GTFS Static API](https://developer.data.gov.my/realtime-api/gtfs-static)
- [GTFS Realtime API](https://developer.data.gov.my/realtime-api/gtfs-realtime)
- [Open API rate limits](https://developer.data.gov.my/rate-limit)
- [GTFS Schedule reference](https://gtfs.org/documentation/schedule/reference/)
- [GTFS Realtime reference](https://gtfs.org/documentation/realtime/reference/)

## 3. Repository and Runtime Topology

### 3.1 Bootstrap Order

1. Initialise the Git repository and run `codegraph init .` before source exploration; run `codegraph sync .` after every coherent source change.
2. Create a pnpm workspace with a Vite + React + TypeScript application and a Django application managed by `uv` and `pyproject.toml`.
3. Create `DESIGN.md` before implementing React components. Use it as the sole source for visual tokens and reusable component behaviour.

### 3.2 Production Topology

```text
Browser
  |-- Cloudflare Pages: React application and PWA assets
  |-- Cloudflare Worker: /api/* and /stream/* gateway
  |-- Cloudflare Access: /ops/* default-deny protection
  |-- MapTiler Cloud: browser vector map tiles
  `-- Cloudflare R2: versioned raw GTFS ZIPs

Cloudflare Worker
  `-- Railway Singapore public Django ASGI service
        |-- Railway private Redis
        |-- Railway managed PostgreSQL
        |-- Railway Celery worker service
        `-- Railway Celery Beat service
```

All Railway services are deployed in Southeast Asia (Singapore). Only the Django ASGI service has a public Railway domain. The Celery worker, Beat scheduler, Redis, and PostgreSQL use Railway private networking.

Cloudflare Pages serves `/`. The Worker serves same-origin `/api/*` and `/stream/*`; it forwards `/ops/*` only after Cloudflare Access authentication. Same-origin routing avoids CORS, cookie, and PWA-scope complexity.

## 4. Data Architecture

### 4.1 Feed Registry

`FeedRegistryEntry` is configuration, not user input. It contains a stable `feed_id`, agency, mode/category, static URL, optional realtime URL, priority tier, source timezone, and enabled state. Every persisted external identifier is namespaced by `feed_id`.

### 4.2 Versioned Static Import

- Schedule a daily import at 04:00 `Asia/Kuala_Lumpur`.
- Fetch feeds serially through a 4-request/minute limiter and use `Accept: application/zip, application/octet-stream, */*`.
- Store the original ZIP in R2 before parsing and retain its content-hash manifest with the staged database version.
- Parse into a staged `feed_version`; validate required columns, foreign references, coordinates, dates, and times before activation.
- Atomically switch the feed's `active_version_id` only when validation passes. Keep the last successful active version available on error.
- Treat orphan or malformed optional records as warnings where they do not make core route, stop, trip, or stop-time data unusable. Persist a validation report.

The relational model includes feed versions, agencies, routes, stops, trips, stop times, service calendars, calendar exceptions, source artifacts, validation issues, realtime fetches, and vehicle snapshots. Store locations as indexed `latitude`/`longitude` numeric columns. Nearby-stop queries first apply a latitude/longitude bounding box and then compute Haversine distance; no PostGIS extension is required.

Service resolution applies `calendar.txt` plus optional `calendar_dates.txt` in the agency timezone. GTFS time values may exceed `24:00:00`; preserve the raw value and resolve the display day offset instead of rejecting it.

### 4.3 Realtime Import and Freshness

Use a shared Redis 15-second request gate across every worker replica, which limits each official API class to four requests per minute. Reserve the first three realtime selections in each cycle for `ktmb`, `rapid-bus-kl`, and `rapid-bus-mrtfeeder`; use the fourth selection to round-robin every other enabled realtime feed. If Redis is unavailable, skip rather than make an ungoverned upstream request.

For every fetch:

1. Apply connect, read, body-size, and total-time limits.
2. Decode the GTFS Realtime protobuf, validate coordinates and timestamps, and capture feed-level failures.
3. Keep raw identifiers for auditability and link to a scheduled trip only when the match is valid.
4. Retain the latest bounded snapshot in PostgreSQL; the read-only SSE endpoint emits a compact reconnectable snapshot.
5. Record `last_successful_fetch_at`, freshness age, source error, and quality state.

The only user-facing realtime states are `live`, `stale`, `scheduled_only`, and `unavailable`. A GPS outlier is hidden from map rendering and explained in data status; it never becomes an ETA. If a feed is unavailable, the route and timetable remain visible from the active static version.

## 5. Public API Contract

All public endpoints are read-only, versioned under `/api/v1`, use feed-scoped IDs, validate and bound every query parameter, emit JSON UTF-8, and attach source/freshness metadata to schedule and search results.

| Endpoint | Purpose |
| --- | --- |
| `GET /api/v1/search?q=&limit=` | Search active routes and stops. |
| `GET /api/v1/routes/{feedSlug}/{routeId}` | Route identity and static source metadata. |
| `GET /api/v1/stops/{feedSlug}/{stopId}` | Active stop metadata and source state. |
| `GET /api/v1/stops/nearby?latitude=&longitude=&radius_metres=&limit=` | Bounded nearby stops using a bounding box plus Haversine filter. |
| `GET /api/v1/trips/{feedSlug}/{tripId}?service_date=` | Mode, route, service date, planned times, and stop sequence; never an ETA. |
| `GET /api/v1/journeys?service_date=&limit=` | Bounded planned journey cards for the selected service date. |
| `GET /api/v1/vehicles?feed=&limit=` | Bounded, validated current vehicle snapshots. |
| `GET /api/v1/data-status` | Feed capability, active static version, and successful upstream-fetch timestamps. |
| `GET /stream/v1/vehicles` | Read-only SSE snapshot with a reconnect retry directive. |

SSE responses use `Cache-Control: no-store, no-transform` and a retry directive. The browser never receives upstream credentials or a government API URL constructed from user input.

## 6. Security and Privacy

- The Cloudflare Worker injects an `X-Transit-Edge-Secret`. Django performs constant-time verification and rejects all direct Railway-origin traffic without it.
- Disable production `workers.dev`; use a custom-domain Worker route. Never expose a Railway domain in frontend configuration.
- Cloudflare Access protects `/ops/*` with default-deny Email OTP allowlisting. Django requires `is_staff` and records the actor, timestamp, correlation ID, action, and before/after state.
- Enforce HTTPS, HSTS, CSP, `frame-ancestors 'none'`, `object-src 'none'`, `base-uri 'self'`, strict `connect-src`, secure referrer policy, and explicit permissions policy. CSP permits only the selected Cloudflare, Railway, and MapTiler endpoints.
- Apply Cloudflare WAF managed rules and route-specific rate limits to search, SSE connection setup, and operations routes. Do not add a public feedback form in v1, so Turnstile is unnecessary.
- Do not use public cookies. Local favourites, theme, and opt-in location remain in browser storage or memory. A location is requested only by an explicit "Find stops near me" action and is never transmitted, logged, or persisted.
- Redact IP addresses, query strings, coordinates, credentials, and email addresses from application logs and error events.

## 7. Reliability, Operations, and Delivery

- Configure Railway health checks for the ASGI service and restart policies for every service.
- Run database migrations as a Railway pre-deploy step; deploy workers only after migrations succeed.
- Configure managed PostgreSQL backups, test restore instructions, and document a quarterly recovery drill.
- Use idempotent Celery tasks, bounded exponential retry with jitter, and a dead-letter queue/report for failed static or realtime processing.
- Monitor API availability, import success, active-version age, realtime freshness, request-gate deferrals, SSE connections, error rate, and p95 API latency. Do not add product or advertising analytics.
- Keep a rollback path for Pages, Worker, Railway application release, and active GTFS feed version.

Cloudflare and Railway configuration must be declarative where the provider supports it. Secrets live only in Cloudflare Worker secrets or Railway service variables, never in Git or a frontend build artifact.

## 8. Verification Matrix

| Area | Required checks |
| --- | --- |
| Static ingest | Valid and malformed ZIPs, version activation/rollback, date exceptions, after-midnight times, and warning-only orphan references. |
| Realtime | Token-bucket limit, protobuf parse failures, trip-ID mismatch, stale feed, GPS outlier, and static-only rail behaviour. |
| API/SSE | Schema contract tests, query bounds, same-origin headers, SSE retry/reconnects, and `no-store` responses. |
| Security | Direct Railway rejection, Worker secret rotation, Access deny/allow, CSP, WAF/rate-limit behaviour, secret scanning, and audit records. |
| Frontend | Unit tests, route-level integration tests, and Playwright checks at 375px, 768px, and 1280px for default, hover, focus, loading, empty, error, stale, and dark-mode states. |
| Operations | Deployment health check, backup restore rehearsal, failure alert, and rollback rehearsal. |

## 9. Implementation Sequence

1. Establish repository, CodeGraph, workspace tooling, environment templates, and CI checks.
2. Build the feed registry, versioned static importer, validation report, and static search/read APIs.
3. Add the shared Redis request gate, realtime poller, freshness model, bounded vehicle API, and SSE gateway.
4. Provision the Cloudflare/Railway boundary, R2 archival, Access-protected operations console, and monitoring.
5. Implement the React application strictly against `DESIGN.md`, then complete browser, security, data-pipeline, recovery, and deployment verification.
