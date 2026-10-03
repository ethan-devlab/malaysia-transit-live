# Malaysia Transit Live — Development Handoff

**Prepared:** 2026-07-16  
**Workspace:** `C:\Users\JC\Desktop\program\CurrentWorkspace\gtfs_realtime`  
**Runtime:** Windows + Docker Desktop, local-only at `http://127.0.0.1:8080`

## Purpose for the next agent

Continue development safely from the current local-only Transit Live implementation. Start by confirming the local stack and current uncommitted diff; do not reset, discard, or assume the working tree is clean.

## Authoritative project artifacts

Do not restate these documents unless changing their underlying decision:

- `README.md` — first-run, normal operation, recovery, data inspection, and credential-volume reset.
- `Architecture.md` — GTFS data model, API contracts, local-only boundary, and future cloud profile.
- `DESIGN.md` — Civic signal design system, accessibility, breakpoints, and map semantics.
- `compose.local.yml`, `infra/` — actual local runtime and egress boundary.
- `apps/web/src/` and `backend/transit/` — current implementation.

## Current implementation state

- The supported runtime is Docker Compose on one Windows machine. Only the egress proxy publishes `127.0.0.1:8080`; web, Django ASGI, Celery worker/beat, PostgreSQL, and Redis are not directly exposed.
- `init` applies migrations, seeds the official registry, and queues initial/missed static refresh. Static GTFS is versioned, atomically activated after validation, and locally retains active plus one previous good version.
- Static refresh runs daily at `04:00 Asia/Kuala_Lumpur`; GTFS Realtime polling uses the shared four-request-per-minute budget, prioritizing KL feeds and rotating remaining eligible feeds.
- Realtime is vehicle-position only. Never claim ETA or live next-stop prediction. The selected vehicle’s **next scheduled stop** is derived from static GTFS only when the realtime payload includes a linked trip. If no trip ID is supplied, the UI explicitly says it can show the current position only.
- `/api/v1/search` is additive and returns matching scheduled journeys, routes, stops, and retained validated vehicle positions. Search results are no longer limited to the default board samples.
- Vehicle and journey actions use one explicit map-focus state. Selecting a vehicle then selecting `View route` or a scheduled search result switches the map to that journey and clears the selected-vehicle context.
- KTMB is presented as `Rail`; the official static feed reports a route type that would otherwise be shown as tram/LRT.
- The map is large at desktop (`42–52rem` height), remains accessible from mobile via the network-view control, and uses MapLibre + MapTiler attribution.
- The PWA service worker bypasses `/api/*`, `/stream/*`, cross-origin requests, and its own `/sw.js`. This prevents future releases from self-caching the worker script.
- The default-deny egress proxy permits only the official API host and its official static archive redirect host. The same allowlist is documented in `README.md` and `Architecture.md`.

## Last verified behavior

The local stack was healthy after rebuilding `web`:

- `api`, `worker`, `beat`, `web`, `egress-proxy`, PostgreSQL, and Redis reported healthy.
- `GET /api/v1/healthz` returned `{"status":"ok"}`.
- `GET /api/v1/search?q=ktmb&limit=5` returned scheduled journeys and validated vehicles; its journey mode was `rail`.
- Fresh Chrome QA at 375px, 768px, and 1280px had zero horizontal overflow and zero console errors.
- Chrome QA verified: select validated vehicle `2919` → see timetable-derived next stop and coordinates → select a Padang Besar scheduled journey → map status changes to the journey and the selected-vehicle panel disappears.
- Focused backend tests passed: `tests/test_network_search.py`, `tests/test_route_modes.py`, and `tests/test_vehicle_stream.py` (five tests total in that run).
- `pnpm --dir apps/web check`, `pnpm --dir apps/web build`, focused Ruff, `manage.py check`, and `git diff --check` passed.
- Independent goal, QA, code-quality, security, and context review lanes passed after remediation.

## Operational commands

Run PowerShell from the repository root:

```powershell
.\Start-Transit.ps1
.\Status-Transit.ps1
.\Stop-Transit.ps1
```

Use this only after source, Dockerfile, or Compose changes:

```powershell
.\Start-Transit.ps1 -Rebuild
```

Useful diagnostics:

```powershell
docker compose --env-file .env.local -f compose.local.yml ps
docker compose --env-file .env.local -f compose.local.yml logs --tail 120 <service>
Invoke-RestMethod http://127.0.0.1:8080/api/v1/healthz
Invoke-RestMethod 'http://127.0.0.1:8080/api/v1/data-status'
```

Focused development validation:

```powershell
pnpm --dir apps/web check
pnpm --dir apps/web build
uv run --directory backend --group dev ruff check transit tests
uv run --directory backend --group dev pytest tests/test_network_search.py tests/test_route_modes.py tests/test_vehicle_stream.py -q
docker exec -e PYTHONDONTWRITEBYTECODE=1 malaysia-transit-local-api-1 /app/.venv/bin/python manage.py check
```

## Important operator notes

- `.env.local` is local and must never be committed. Do not copy secrets, MapTiler keys, or database credentials into tickets, handoffs, logs, or commits.
- Changing PostgreSQL credentials after first initialization requires the documented destructive volume reset in `README.md`; merely editing `.env.local` does not update an existing database volume.
- There are intentionally no database backups. Data recovery means rebuilding volumes and importing GTFS again.
- An already-open old `127.0.0.1:8080` PWA tab may retain the pre-fix service worker. Use Chrome DevTools → Application → Storage → **Clear site data** for that origin once, then reload. The current worker avoids this on future updates.
- MapTiler’s browser key must remain restricted to `http://localhost:8080` and `http://127.0.0.1:8080`.

## Working-tree and delivery status

- The implementation remains **uncommitted**. The current tree contains both modified tracked files and new local-runtime files. Preserve all existing changes; use `git diff`/`git status` before making edits.
- No branch, commit, or pull request was created during the last implementation pass.
- The root package’s `build`, `check`, and `test` scripts include an `apps/edge` package, while the active local-only runtime uses Compose, Django, and `apps/web`. Check the exact command scope before declaring a full-repository release validation.

## Suggested next-phase priorities

1. **Add regression coverage for the proxy allowlist.** The documented allowlist is correct but lacks an automated contract test against `infra/egress_proxy.py`.
2. **Add component/E2E coverage for commuter flow.** Cover vehicle → journey focus replacement, trip-less vehicle disclosure, search categories, and map/list behavior at all three breakpoints.
3. **Reduce the MapLibre production chunk.** Vite still reports a MapLibre chunk above 500 kB. Keep lazy loading, then investigate style/dependency splitting without breaking map fallback or attribution.
4. **Make route and stop search records actionable.** Search already returns them, but scheduled trips and vehicles are the primary clickable result types. Decide whether route/stop results should open dedicated detail views or focus map geometry.
5. **Re-evaluate feed-specific mode overrides as feeds change.** `ktmb` is intentionally overridden to `rail`; future GTFS imports may need similarly evidence-based display normalization.
6. **Before any cloud deployment, reopen the future-cloud decisions in `Architecture.md`.** The active security model is deliberately loopback-only and must not be treated as production internet exposure.

## Suggested skills for the next agent

- `omo:programming` — required for Python/TypeScript edits.
- `omo:debugging` — runtime, Docker, import, or freshness failures.
- `omo:frontend` and `omo:visual-qa` — any UI, layout, or map change.
- `playwright` or `agent-browser` — real browser validation after web changes.
- `powershell-safe-workflow` — Windows/Docker command execution.
- `review-work` — required post-implementation review for significant changes.
- `grill-me` — use when a decision materially changes commuter UX, data semantics, or deployment scope.

## Safe first actions

1. Read `README.md`, `Architecture.md`, `DESIGN.md`, and this handoff.
2. Run `.\Status-Transit.ps1`; if not healthy, inspect Compose logs before changing code.
3. Run `git status --short` and inspect only the relevant diff.
4. Use CodeGraph before text search/source exploration when `.codegraph/` exists.
5. Keep repository artifacts in English; communicate with the user in Traditional Chinese.
