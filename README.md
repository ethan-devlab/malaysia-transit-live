# Malaysia Transit Live

Malaysia Transit Live is a full-Malaysia GTFS schedule service with a KL/Klang Valley-first live experience. Static GTFS schedules are authoritative; a vehicle appears live only after a fresh official GTFS Realtime position matches an active static feed version.

## Local-only internal runtime

The supported runtime is Docker Compose on one Windows computer. It exposes only `http://127.0.0.1:8080`; PostgreSQL, Redis, Django, Celery, and Nginx have no other host ports. It does not use Railway, Cloudflare, R2, or a public domain.

The unexposed Celery worker reaches the official Malaysian GTFS APIs only through an internal default-deny proxy that permits `api.data.gov.my:443` and its official static-archive redirect host `openapi-malaysia-transport.s3.ap-southeast-1.amazonaws.com:443`. Nginx shares the proxy's restricted network namespace: its process can reach only Django's internal port and Docker DNS, while the proxy process alone can open HTTPS tunnels. Map tiles are fetched directly by the browser from MapTiler; every route and vehicle remains available in the accessible service board.

### First setup

1. Ensure Docker Desktop is running.
2. Copy the environment template and replace the three placeholder secrets:

   ```powershell
   Copy-Item .env.local.example .env.local
   notepad .env.local
   ```

   `POSTGRES_PASSWORD` must use only letters, numbers, `_`, and `-`. Generate a unique `DJANGO_SECRET_KEY`. Set `VITE_MAPTILER_KEY` to a MapTiler browser key restricted to both `http://localhost:8080` and `http://127.0.0.1:8080`.

3. Start the service:

   ```powershell
   .\Start-Transit.ps1
   ```

The first start creates the schema, seeds every official feed, and queues a serial full-Malaysia static import. The UI correctly shows unavailable data until a valid feed becomes active. Existing data remains available while later daily imports are staged and validated.

### Daily use

```powershell
.\Start-Transit.ps1
.\Status-Transit.ps1
.\Stop-Transit.ps1
```

`Start-Transit.ps1` normally preserves running containers so it does not interrupt a static import. Use `./Start-Transit.ps1 -Rebuild` only after changing application, Compose, or Dockerfile source.

Starting is manual. Once started, Celery Beat refreshes static GTFS at `04:00 Asia/Kuala_Lumpur` and polls the validated realtime priority feeds once per minute. If the stack was stopped during the daily refresh, startup queues one catch-up refresh. Redis enforces four requests per minute separately for GTFS Static and GTFS Realtime.

### Local data and recovery

- PostgreSQL and Redis use Docker named volumes.
- Changing `POSTGRES_PASSWORD` after PostgreSQL first initializes does not change the password stored in its volume. Restore the original value in `.env.local` to preserve data, or use the intentional destructive reset below.
- Original GTFS ZIPs are stored in the ignored `local-data/archives/` directory.
- Each feed retains the active static version and one previous valid version. Older GTFS rows and ZIPs are removed only after a later version activates successfully.
- Fetch attempts and rejected-import metadata are retained for seven days.
- No database backup is created. If the computer or Docker volumes fail, start from a clean local runtime and download the feeds again.

`Stop-Transit.ps1` does not delete any data. Do not run `docker compose down --volumes` unless you intend to erase the local database and queue state.

### Rebuild volumes after changing PostgreSQL credentials

If you change `POSTGRES_USER` or `POSTGRES_PASSWORD` in `.env.local`, PostgreSQL cannot apply those credentials to its existing volume. Rebuild the local volumes before starting again:

```powershell
.\Stop-Transit.ps1
docker compose --env-file .env.local -f compose.local.yml down --volumes
Remove-Item -LiteralPath .\local-data\archives -Recurse -Force -ErrorAction SilentlyContinue
.\Start-Transit.ps1
```

This permanently removes the local PostgreSQL database, Redis queue state, and downloaded GTFS archives. The final start initializes PostgreSQL with the new credentials and downloads fresh GTFS data.

Use the same sequence for an intentional destructive reset after volume loss or unusable local data. Backups are intentionally disabled, so deleted historical data cannot be restored.

### Inspect the PostgreSQL volume and imported data

`malaysia-transit-local_postgres-data` is a Docker named volume, not a browsable Windows folder. Inspect its Docker metadata with:

```powershell
docker volume inspect malaysia-transit-local_postgres-data
```

Run SQL through the PostgreSQL container, which reads the configured account and database name without printing the password:

```powershell
docker compose --env-file .env.local -f compose.local.yml exec -T postgres `
  sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT f.slug, v.status, v.activated_at FROM transit_transitfeed AS f LEFT JOIN transit_staticfeedversion AS v ON v.feed_id = f.id AND v.status = ''active'' ORDER BY f.slug;"'
```

An imported feed has `status` `active` and a non-empty `activated_at` value.

### Security boundary

- The only published port is `127.0.0.1:8080`; the stack is unavailable to other devices on the LAN.
- Nginx serves the React build and same-origin proxies `/api/*` and `/stream/*` to Django. SSE proxy buffering is disabled.
- Django runs with `DEBUG=false`. Its local-only mode permits the Docker-internal route without the Cloudflare origin secret, disables HTTPS-only cookies solely for loopback HTTP, and accepts only `localhost` or `127.0.0.1` hosts. Nginx rejects every other Host before it can serve static assets.
- No public cookies, analytics, accounts, or behaviour tracking are added.

## Development workflow

For hot-reload development, the existing native workflow remains available:

```powershell
pnpm install
Set-Location backend
uv sync --all-groups
$env:DJANGO_SECRET_KEY = "development-only-secret"
$env:DJANGO_DEBUG = "true"
uv run python manage.py migrate
uv run python manage.py seed_transit_feeds
uv run uvicorn config.asgi:application --reload --port 8000
```

In another terminal, run `pnpm --filter @malaysia-transit/web dev`. The development browser uses explicit preview data until an active static version is available; the local Compose production build always calls the real local API.

## Optional future cloud profile

The Railway and Cloudflare files remain in the repository for a future deployment profile, but the local Compose workflow does not read them. The source contracts remain in [Architecture.md](Architecture.md) and [DESIGN.md](DESIGN.md).
