FROM node:24-bookworm-slim AS build

WORKDIR /workspace
RUN corepack enable && corepack prepare pnpm@11.9.0 --activate

COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY apps/web/package.json apps/web/package.json
COPY apps/edge/package.json apps/edge/package.json
RUN pnpm install --frozen-lockfile --filter @malaysia-transit/web...

COPY apps/web apps/web
ARG VITE_MAPTILER_KEY
ENV VITE_MAPTILER_KEY=${VITE_MAPTILER_KEY}
RUN pnpm --filter @malaysia-transit/web build

FROM nginxinc/nginx-unprivileged:1.28-alpine

COPY --chown=nginx:nginx infra/nginx.local.conf /etc/nginx/conf.d/default.conf
COPY --chown=nginx:nginx --from=build /workspace/apps/web/dist /usr/share/nginx/html
