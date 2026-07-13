# Malaysia Transit Live

Malaysia Transit Live is a public, full-Malaysia GTFS information service with a KL/Klang Valley-first experience. Static GTFS schedules are authoritative; live locations are shown only after the backend validates a fresh GTFS Realtime vehicle position against the active static version.

The product contract is in [Architecture.md](Architecture.md) and [DESIGN.md](DESIGN.md).

## Local development

Use PowerShell from the repository root:

```powershell
pnpm install
Set-Location backend
uv sync --all-groups
Copy-Item .env.example .env
# Replace required values in .env, then load them into your shell by your normal secret workflow.
$env:DJANGO_SECRET_KEY = "development-only-secret"
$env:DJANGO_DEBUG = "true"
uv run python manage.py migrate
uv run python manage.py seed_transit_feeds
uv run uvicorn config.asgi:application --reload --port 8000
```

In a second terminal:

```powershell
pnpm --filter @malaysia-transit/web dev
pnpm --filter @malaysia-transit/edge dev
```

The local React preview intentionally labels fixture cards as a preview until an active static version is available through `/api/v1`. The browser never calls `data.gov.my` directly.

## Railway service commands

Create three Railway services with `backend/` as their root directory, sharing the same PostgreSQL, Redis, and secret variables. In each Railway service, set the **Config as Code** file explicitly:

```text
ASGI service:  /backend/railway.toml
Celery worker: /backend/railway.worker.toml
Celery Beat:   /backend/railway.beat.toml
```

The ASGI configuration runs migrations as its pre-deploy command and exposes `/api/v1/healthz`. After its first successful deploy, run `uv run python manage.py seed_transit_feeds` once. Add the Railway ASGI hostname to `DJANGO_ALLOWED_HOSTS`; `healthcheck.railway.app` is already accepted for Railway deployment checks. Keep `WORKER_ORIGIN_SECRET` identical to the Cloudflare Worker secret.

## Cloudflare boundary

1. Deploy `apps/web` to Cloudflare Pages with `pnpm --filter @malaysia-transit/web build` and output `apps/web/dist`.
2. Set the Worker’s `RAILWAY_ORIGIN` to the HTTPS Railway ASGI origin. Set `WORKER_ORIGIN_SECRET` with `wrangler secret put WORKER_ORIGIN_SECRET` from `apps/edge`; do not put it in `wrangler.jsonc`.
3. Route the Worker only for the Pages custom domain’s `/api/*` and `/stream/*`. `workers.dev` is disabled deliberately.
4. Set `VITE_MAPTILER_KEY` only in the Pages build environment and restrict that browser key to the production domain in MapTiler.
5. Protect any future `/ops/*` route with Cloudflare Access default-deny before publishing it.

No deployment is made by this repository: it requires the account-specific Railway domain, Cloudflare zone/routes, R2 credentials, and MapTiler key.
