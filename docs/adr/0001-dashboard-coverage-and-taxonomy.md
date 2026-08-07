# ADR 0001: Dashboard coverage and taxonomy

## Status

Accepted

## Context

Malaysia Transit Live serves commuters who need current vehicle positions and operators
who need an honest view of feed coverage. Static GTFS coverage is broader than realtime
Vehicle Positions coverage, and the product must not imply ETA predictions or infer a
vehicle mode from a feed slug when route metadata is missing.

## Decisions

1. Deliver one read-only React dashboard with two switchable workspaces: Network
   overview and Service health. The same mode/operator/city-region filters and URL
   state apply to both.
2. Keep every official feed visible. Label feeds as available, awaiting first fetch,
   scheduled only, or unavailable; zero-vehicle feeds are not silently removed.
3. Store canonical operator and city/metro metadata on `TransitFeed` from the official
   registry. Preserve GTFS agency names as detail metadata instead of replacing them.
4. Normalize dashboard modes to `bus`, `mrt`, `lrt`, `monorail`, `rail`, and `unknown`.
   Missing or orphan route IDs remain visible as `unknown`/Unclassified.
5. Expose a new aggregate REST endpoint and matching dashboard SSE serializer. Use a
   global safety cap with opaque cursor pagination and make truncation explicit.
   Existing vehicle, data-status, and vehicle-stream contracts remain compatible.
6. Use positions and published timetable stop sequences only. Never expose ETA or
   live-arrival predictions from Vehicle Positions data.

## Consequences

The dashboard has more honest empty and partial states and requires batch metadata
queries, registry migration, and frontend schema validation. Operators get feed-level
health rather than an import-history console. A future write-capable operations surface
would require a separate security and authorization decision.
