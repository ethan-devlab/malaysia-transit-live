# Route Geometry and Civic Map Quality Implementation Plan

## 1. Document status

- **Status:** Proposed implementation specification
- **Product:** Malaysia Transit Live
- **Scope:** Selected-trip route geometry, map cartography, shape-less rail fallback, and network-scale rendering
- **Primary contracts:** `Architecture.md`, `DESIGN.md`, and ADR 0001
- **Last verified local feed sample:** 2026-07-13 archived static feeds

This document turns the route-geometry and map-quality proposal into an executable,
four-phase implementation plan. Each phase has a hard acceptance gate. A later phase
must not compensate for an unmet earlier gate: visual polish cannot make approximate
geometry authoritative, and a performance optimization cannot remove provenance or
accessibility information.

## 2. Problem statement

The current map constructs a route `LineString` by connecting scheduled stop
coordinates in stop-sequence order. That line is useful as a last-resort schematic,
but it is not the path travelled by the vehicle. It can cut across buildings, water,
roads, or railway curves and therefore must not look equivalent to an authoritative
route alignment.

The backend already stores `GtfsTrip.shape_id`, but it does not import the corresponding
`shapes.txt` points. The trip-detail API consequently returns stops but no geometry,
and the frontend has no alternative to joining those stops.

The local archived-feed sample contains `shapes.txt` for 15 of 16 feeds, including
`rapid-rail-kl` and every sampled bus feed. The sampled KTMB archive is the only feed
without shapes. This evidence supports the following priority:

1. Use official GTFS shapes wherever supplied.
2. Use a versioned, attributable infrastructure match only for a confirmed shape-less
   rail feed.
3. Keep the stop-sequence line as an explicitly approximate fallback.
4. Show no route line when even an approximate line would be misleading.

The GTFS Schedule reference defines `shapes.txt` as the ordered path a vehicle travels
along a route alignment. It remains the authority for official geometry:
<https://gtfs.org/documentation/schedule/reference/#shapestxt>.

## 3. Goals and non-goals

### 3.1 Goals

- Draw selected rail and bus trips along authoritative GTFS geometry when available.
- Preserve geometry provenance and quality from import through API, UI, and Service
  health.
- Make an approximate route visually distinguishable without relying on colour alone.
- Improve the map through disciplined civic cartography: a quiet basemap, clear route
  hierarchy, legible stops, mode-aware vehicles, and progressive disclosure.
- Keep the map and list/detail surfaces operationally equivalent and accessible.
- Establish a measured path from selected-route GeoJSON to network-scale vector tiles
  only when observed load justifies that complexity.

### 3.2 Non-goals

- ETA or live-arrival prediction.
- Inferring a vehicle's position between realtime reports.
- Browser-side road or rail routing.
- Treating a path matched from third-party infrastructure as official GTFS data.
- Replacing MapLibre GL JS.
- Adding decorative 3D, terrain, glassmorphism, gradients, glow effects, or continuous
  vehicle animation.
- Building a journey planner or transfer router.

## 4. Invariants and shared vocabulary

### 4.1 Geometry-quality contract

All layers use the same closed vocabulary:

| Value | Meaning | Permitted map treatment |
| --- | --- | --- |
| `official_shape` | Ordered points imported from the active version's GTFS `shapes.txt`. | Solid route core and casing; normal route emphasis. |
| `matched_infrastructure` | A versioned path derived from a documented rail or road graph. | Solid route with a visible `Derived alignment` label in details and legend. |
| `stop_sequence` | A straight-segment line joining valid scheduled stops. | Thin dashed line and an `Approximate alignment` label. |
| `unavailable` | No safe geometry can be produced. | Stops only; no route line. |

The quality value is data, not a frontend inference. The server chooses it and includes
the geometry source and static version. The client only maps that value to an approved
visual treatment.

### 4.2 Truthfulness rules

- `official_shape` may only come from `shapes.txt` in the active static feed version.
- `matched_infrastructure` must include the infrastructure dataset version, derivation
  version, and attribution.
- `stop_sequence` must never be rendered with the same solid treatment as an official
  or matched alignment.
- A vehicle position does not alter the static route geometry and does not create an
  ETA.
- Missing or invalid geometry must not remove the trip, vehicle, timetable, or stops.
- Route colour communicates line identity only. Freshness remains a separate labelled
  state.
- Every map selection must remain available through the equivalent list or detail
  control.

### 4.3 Source priority

```text
active GTFS version has a valid trip shape
  -> official_shape

no valid GTFS shape and an approved derived alignment exists
  -> matched_infrastructure

no approved derived alignment and at least two valid scheduled stops exist
  -> stop_sequence

fewer than two valid points or validation rejects the result
  -> unavailable
```

## 5. Target architecture

### 5.1 Static data model

Add a normalized shape-point model scoped to the immutable static feed version:

```text
GtfsShapePoint
  id
  feed_version_id          FK -> StaticFeedVersion
  shape_id                 string
  sequence                 non-negative integer
  latitude                 decimal
  longitude                decimal
  distance_travelled       nullable decimal
```

Required database rules:

- Unique constraint on `(feed_version_id, shape_id, sequence)`.
- Index on `(feed_version_id, shape_id, sequence)` for ordered retrieval.
- Optional index on `(feed_version_id, shape_id)` if the database does not satisfy
  prefix lookups efficiently through the ordered index.
- Cascade deletion with the static feed version.
- No geometry duplication per trip; trips continue to reference shapes through
  `shape_id`.

The schema migration creates only the table and indexes. It must not open ZIP files or
perform a long-running data backfill inside a Django migration. Existing active feeds
are repopulated by staging a new immutable version from the retained archive and then
using the existing atomic activation path.

### 5.2 Static importer

`shapes.txt` remains optional at the archive level. When present, the importer must:

1. Require `shape_id`, `shape_pt_lat`, `shape_pt_lon`, and `shape_pt_sequence`.
2. Parse latitude and longitude through the same bounded coordinate policy used for
   stops and realtime positions.
3. Reject a negative or duplicate sequence within one shape.
4. Accept an omitted `shape_dist_traveled`; validate it as numeric and non-decreasing
   when present.
5. Insert points in batches and avoid holding an entire nationwide feed in memory.
6. Reject a single shape that exceeds the configured shape-point safety limit rather
   than returning an unbounded API payload later.
7. Add validation-report counts for shapes, shape points, trips with a shape reference,
   orphan trip shape references, and trips without a shape reference.

An orphan `trip.shape_id` is a validation warning when the core timetable remains
usable. It makes that trip eligible for fallback geometry; it does not fail or remove
the trip.

### 5.3 Geometry service

Introduce one backend geometry resolver used by every API serializer:

```python
resolve_trip_geometry(feed_version, trip) -> TripGeometry
```

The resolver must:

- Batch or directly load ordered points for one selected `shape_id` without a
  per-point or per-stop query.
- Apply the source-priority rules in section 4.3.
- Validate that the final line has at least two distinct valid positions.
- Return immutable provenance metadata with the geometry.
- Never call an external routing service on a public request path.
- Allow caching by `static_version_id`, `shape_id`, and derivation version.

### 5.4 Public API extension

Extend the existing trip-detail response additively:

```json
{
  "trip_id": "example-trip",
  "route_id": "KJL",
  "headsign": "Putra Heights",
  "service_date": "2026-08-07",
  "is_scheduled": true,
  "route_color": "DC241F",
  "route_text_color": "FFFFFF",
  "geometry": {
    "type": "LineString",
    "coordinates": [[101.6869, 3.1390], [101.6874, 3.1401]],
    "quality": "official_shape",
    "shape_id": "KJL-OUTBOUND",
    "source": "gtfs",
    "source_version": "static-version-id",
    "attribution": null
  },
  "stops": [],
  "source": {}
}
```

Contract rules:

- Coordinates follow GeoJSON order: longitude, latitude.
- `geometry` is always present. Its coordinates are `null` when quality is
  `unavailable`.
- `shape_id` is nullable for derived, approximate, and unavailable geometry.
- `source` is `gtfs`, `derived_infrastructure`, `scheduled_stops`, or `none`.
- `attribution` is mandatory for `derived_infrastructure` and null otherwise.
- Route colours are normalized six-digit hexadecimal strings without `#`; invalid
  upstream values become empty strings.
- The endpoint remains timetable-only and must not expose ETA fields.

Extend each Service-health feed row additively with:

```json
{
  "geometry_coverage": {
    "trip_count": 120,
    "official_shape_count": 118,
    "matched_infrastructure_count": 0,
    "stop_sequence_count": 2,
    "unavailable_count": 0
  }
}
```

Counts are calculated from the active static version and cached or materialized during
activation. The dashboard request must not scan every trip on each call.

### 5.5 Frontend data model

The Zod schema mirrors the closed quality enum and rejects malformed geometry. The
frontend transforms the returned geometry into one GeoJSON source containing:

- One `LineString` feature with `quality`, route identity, route colour, and selected
  state properties.
- Stop `Point` features with stop identity, sequence, and station-role properties.
- No client-generated solid route when official geometry fails validation.

The existing stop-joining function remains only as a bounded representation of the
server-declared `stop_sequence` fallback. It must not independently upgrade or guess
geometry quality.

### 5.6 MapLibre layer order

The selected-route source is rendered through separate layers in this order:

1. Route casing line.
2. Route core line.
3. Stop circles and interchange symbols.
4. Route labels.
5. Vehicle clusters and vehicle symbols.
6. Selected vehicle and keyboard focus indication.

MapLibre supports GeoJSON sources, line layers, symbol layers, zoom expressions, and
data-driven paint values. Relevant specifications:

- <https://maplibre.org/maplibre-style-spec/sources/#geojson>
- <https://maplibre.org/maplibre-style-spec/layers/#line>
- <https://maplibre.org/maplibre-style-spec/layers/#symbol>
- <https://maplibre.org/maplibre-style-spec/expressions/>

## 6. Phase 1: Authoritative GTFS geometry

### 6.1 Deliverables

#### Backend and database

- Add `GtfsShapePoint`, migration, model export, constraints, and indexes.
- Add an optional `shapes.txt` loader to the staged static-import orchestrator.
- Extend validation reports with geometry coverage and orphan-reference counts.
- Add the shared geometry resolver with the source-priority contract.
- Extend trip detail with route colours and `geometry`.
- Add cached geometry-coverage counts to dashboard feed health.
- Preserve the existing atomic activation and previous-version rollback behavior.

#### Frontend

- Extend the trip-detail Zod schema and TypeScript types.
- Replace the selected route's solid stop-to-stop line with the server geometry.
- Render `official_shape` as a solid route and `stop_sequence` as a labelled dashed
  approximation.
- Render stops even when geometry is unavailable.
- Add geometry quality and source to the route detail/legend without introducing a
  modal.
- Keep next-stop wording timetable-derived and preserve the no-ETA contract.

#### Tests

- Static-import tests for a valid shape, missing optional `shapes.txt`, duplicate
  sequence, invalid coordinate, non-monotonic distance, orphan shape reference, and
  importer rollback.
- Resolver tests for all four quality values and source-priority ordering.
- API schema tests for coordinate order, provenance, route colours, unavailable
  geometry, and query count.
- Frontend schema and route-data tests for official, approximate, unavailable, and
  malformed payloads.

### 6.2 Phase 1 acceptance gate

Phase 1 is accepted only when all of the following are evidenced:

#### Data correctness

- A staged import containing `shapes.txt` persists every valid shape point in sequence
  and activates atomically.
- An archive without `shapes.txt` still activates and retains complete route, trip,
  stop, and timetable behavior.
- A duplicate `(feed_version, shape_id, sequence)` cannot be persisted.
- Invalid shape data rejects the staged version or produces the documented warning;
  the previously active version remains active.
- Re-importing the retained archive creates and activates a new immutable version; no
  data migration mutates the prior active version in place.
- A coverage report for the current local archive sample identifies official shapes
  for Rapid Rail and sampled bus feeds and identifies KTMB as shape-less unless the
  upstream archive has changed.

#### API correctness

- A known Rapid Rail trip returns `quality=official_shape`, GTFS provenance, at least
  two distinct coordinates, and the active static-version ID.
- A shape-less trip returns `stop_sequence` or `unavailable` without a server error.
- Longitude and latitude are not transposed.
- The first and last scheduled stops lie within the configured validation tolerance of
  the returned official shape, or the trip is downgraded with a recorded reason.
- Trip-detail query count is constant with respect to shape-point and stop count; there
  is no per-point or per-stop N+1 query.
- Existing search, journey, vehicle, dashboard, and SSE contracts remain compatible.
- No response contains ETA, predicted-arrival, or inferred intermediate-position data.

#### Observable map behavior

- A selected Rapid Rail trip follows the curves of its official alignment instead of
  drawing only straight segments between stations.
- An approximate route is dashed and accompanied by the visible text `Approximate
  alignment`; colour is not the only distinction.
- An unavailable route still shows its scheduled stops and a concise inline notice.
- Selecting a vehicle or journey still focuses the same detail and route from both map
  and list controls.
- Light mode, dark mode, and map fallback render without console errors.

#### Automated checks

- Focused backend import, geometry-resolver, trip-detail, dashboard, and regression
  tests pass.
- `pnpm --filter @malaysia-transit/web test` passes for the affected frontend tests.
- `pnpm --filter @malaysia-transit/web check` and `pnpm --filter
  @malaysia-transit/web build` exit successfully.
- `docker compose --env-file .env.local -f compose.local.yml config --quiet` succeeds.

## 7. Phase 2: Civic cartography and interaction polish

### 7.1 Deliverables

#### Basemap

- Create project-owned low-saturation light and dark MapTiler styles based on the
  existing Civic signal palette.
- Reduce low-value POIs, minor-road emphasis, and building contrast while retaining
  cities, water, major roads, railways, and orientation cues.
- Keep MapTiler and OpenStreetMap attribution visible.
- Keep the current inline MapTiler/WebGL fallback path.

MapTiler's Map Designer is the supported editing surface:
<https://docs.maptiler.com/guides/map-design/editor/>.

#### Route hierarchy

- Draw a neutral route casing below a GTFS-coloured route core.
- Use rounded caps and joins and zoom-dependent widths.
- Validate route-colour contrast against both basemap themes; rely on casing and labels
  rather than replacing an identity colour with an unrelated status colour.
- Dim non-selected routes while retaining geographic context.
- Keep approximate routes dashed and derived routes visibly attributed.

#### Stops, labels, and vehicles

- Distinguish ordinary stops, selected stops, termini, and verified interchanges only
  when corresponding static metadata exists.
- Add collision-aware route labels along authoritative geometry at appropriate zooms.
- Replace generic unclustered points with mode-aware SVG/sprite vehicle symbols.
- Rotate a vehicle only when a valid bearing exists.
- Make stale vehicles visually distinct using form and text as well as colour.
- Retain cluster aggregation and selected-vehicle focus.

#### Progressive disclosure

Use zoom ranges as a policy, tuned during browser QA rather than copied as magic values:

| View | Required emphasis |
| --- | --- |
| National/region | Service coverage, major rail corridors, vehicle clusters. |
| City | Selected routes, interchanges, clusters, and route identity. |
| Corridor | Stops, vehicles, route labels, and surrounding transport context. |
| Station | Stop names, selected vehicle, route detail, and precise alignment. |

All widths, radii, label sizes, and opacity changes use MapLibre expressions and tokens
documented in `DESIGN.md`. Motion is restricted to meaningful transform/opacity/filter
feedback at 150-220 ms, with a zero-duration reduced-motion path.

### 7.2 Phase 2 acceptance gate

Phase 2 is accepted only when all of the following are evidenced in a real browser:

#### Visual hierarchy

- The selected route is the first transit feature noticed, while place names, water,
  major roads, and relevant rail infrastructure remain sufficient for orientation.
- Route casing keeps the line legible when crossing roads, water labels, and light or
  dark basemap features.
- GTFS route colours remain identifiable in both themes and are paired with route
  names or codes.
- Ordinary stops, selected stops, verified interchanges, vehicles, stale vehicles, and
  clusters are distinguishable without relying on colour alone.
- Approximate and derived geometry cannot be mistaken for official geometry after
  reading the legend or detail panel.
- No purple, gradients, glassmorphism, decorative glow, ornamental 3D, or nested-card
  treatment is introduced.

#### Interaction and responsiveness

- At 1280 px the map and list/detail split preserves the documented 12-column hierarchy.
- Phase 2 is desktop-only. Mobile and tablet map/list-switcher design and QA are deferred
  to a later explicitly approved phase, rather than being implied by this desktop gate.
- Keyboard users can reach map controls, switch to the list, select a vehicle or
  journey, and identify the current focus.
- Selecting a route, stop, cluster, or vehicle does not steal focus or trap the user on
  the canvas.
- Light, dark, system-theme, 200% text zoom, and reduced-motion modes remain usable.
- Map transitions use the documented duration; reduced motion disables non-essential
  movement and vehicle interpolation.

#### Map reliability

- Missing MapTiler credentials, tile request failure, style failure, and unavailable
  WebGL each produce the documented inline fallback rather than an empty panel or
  modal-only recovery.
- Attribution remains visible and is not obscured by controls at any target breakpoint.
- A style reload or theme switch restores route, stop, cluster, and selected-vehicle
  layers exactly once without duplicate event handlers.
- There are zero console errors and no unhandled promise rejections during the full
  selection and theme-switch flow.

#### Automated and visual checks

- Map-layer unit tests cover quality-to-style mapping, route-colour validation, valid
  bearing rotation, and reduced-motion duration.
- Frontend test, check, and build commands pass.
- Real-browser visual QA passes at 1280 px for light/dark,
  official/derived/approximate/unavailable, selected/unselected, live/stale, loading,
  empty, and map-fallback states.
- WCAG 2.2 AA contrast and visible-focus checks pass for controls, labels, status text,
  and the non-map equivalent surface.

## 8. Phase 3: Shape-less KTMB derived alignment

Phase 3 begins only if the active KTMB upstream feed still lacks usable official
shapes and the product owner accepts a third-party infrastructure source. If official
KTMB shapes become available, they take priority and this phase may be reduced to a
fallback-recovery path.

### 8.1 Deliverables

#### Versioned infrastructure graph

- Select and document an attributable rail-infrastructure dataset, expected initially
  to be a dated OpenStreetMap extract.
- Record source date, geographic extent, license/attribution, content hash, and import
  status.
- Normalize railway edges and junctions into a graph suitable for offline pathfinding.
- Do not download, query, or route against this graph during a browser or public API
  request.

#### Constrained matching pipeline

- Resolve candidate graph nodes for ordered KTMB stops.
- Find a continuous railway path constrained by stop order, route/service identity,
  direction where known, and bounded detour distance.
- Prevent each station from independently snapping to an unrelated nearest track.
- Score endpoint proximity, stop-to-path distance, path continuity, detour ratio,
  railway-edge coverage, and ambiguous branches.
- Persist only results that pass the documented confidence threshold.
- Store the derived geometry separately from GTFS shape points with source and
  derivation versions.
- Recompute only when the active static version, infrastructure snapshot, matching
  configuration, or derivation code version changes.

#### Review and operations

- Provide a bounded review report listing accepted, rejected, and ambiguous KTMB
  alignments with reasons and map links or GeoJSON artifacts.
- Surface `matched_infrastructure` coverage and derivation age in Service health.
- Fall back to `stop_sequence` or `unavailable` when confidence is insufficient.
- Preserve OpenStreetMap attribution wherever a derived alignment is visible.

### 8.2 Phase 3 acceptance gate

Phase 3 is accepted only when all of the following are evidenced:

#### Provenance and licensing

- Every derived geometry row identifies its infrastructure snapshot, content hash,
  derivation version, and static GTFS version.
- API and UI attribution is present for every `matched_infrastructure` result.
- Official shapes automatically outrank derived shapes without manual intervention.
- Removing or invalidating a graph snapshot cannot silently relabel derived geometry as
  official or leave stale provenance behind.

#### Matching correctness

- The first and last KTMB stops are within the configured endpoint tolerance of the
  matched path.
- Scheduled stops occur along the path in stop-sequence order.
- The accepted path is continuous and uses only permitted railway graph edges.
- Detour ratio, stop-to-path distances, graph gaps, and ambiguous branch counts remain
  below the documented thresholds.
- A route with intentionally ambiguous or disconnected infrastructure is rejected and
  falls back safely rather than choosing an arbitrary branch.
- Re-running the matcher with identical versioned inputs produces the same geometry and
  confidence result.

#### Human review sample

- At least one accepted alignment from each distinct KTMB service pattern present in
  the active feed is visually reviewed against railway infrastructure and ordered
  stations.
- Every rejected or low-confidence service pattern is represented in the review report
  with a reason.
- The reviewer can distinguish official, derived, and approximate geometry from the map
  and detail text without consulting the database.

#### Operational behavior

- No public API request triggers external network access or graph pathfinding.
- Matching failure does not block GTFS activation or remove scheduled service.
- A new infrastructure or GTFS version invalidates only the affected derived-cache
  keys.
- Focused matcher, persistence, precedence, API, and fallback tests pass.
- Local Compose can rebuild derived alignments through a documented, idempotent command
  and can serve the last accepted alignment while a newer derivation is rejected.

## 9. Phase 4: Network-scale rendering and measured optimization

Phase 4 is conditional. It starts only after a captured performance trace shows that
selected-route GeoJSON or a requested all-network overlay misses the agreed budget.
The trace and baseline become part of the phase artifact.

### 9.1 Deliverables

#### Geometry preparation

- Deduplicate shared `shape_id` geometry across trips.
- Precompute zoom-appropriate simplifications from the authoritative or derived source
  while retaining the unsimplified stored geometry.
- Preserve endpoints, station proximity, provenance, quality, route identity, operator,
  mode, and static version through simplification.
- Reject simplification that moves a stop beyond the configured alignment tolerance or
  creates self-crossing/jump artifacts absent from the source.

#### Delivery

- Keep selected-trip geometry available through the existing trip-detail contract.
- Add viewport-bounded vector-tile delivery only for the all-network overlay.
- Include route ID, mode, operator, quality, route colour, and selection key as tile
  properties.
- Use immutable versioned tile URLs and cache headers keyed by static/derivation
  version.
- Bound zoom, tile coordinates, feature count, response size, and generation time.
- Do not ship one nationwide all-routes GeoJSON payload to the browser.

#### Rendering

- Use MapLibre filters and feature state for mode/operator/region visibility and
  selected-route emphasis.
- Keep labels collision-aware and progressively disclosed.
- Load only tiles intersecting the viewport and supported zoom range.
- Keep vehicles in their existing current-snapshot source; do not bake volatile
  vehicle positions into static route tiles.

### 9.2 Performance measurement protocol

Record the reference machine, browser version, viewport, dataset version, cache state,
network throttling, and test route before comparing results. Capture:

- Selected-trip API response size and p50/p95 server duration.
- Vector-tile compressed size and p50/p95 generation or cache-hit duration.
- Time from map creation to first usable route rendering.
- Main-thread long tasks and frame time during a scripted pan, zoom, filter, and
  selection sequence.
- Browser memory before and after ten repeated filter/selection cycles.

Budgets may be tightened after baseline capture, but phase acceptance requires at
least:

- A warm selected-trip geometry response at or below 500 ms p95 in local Compose.
- A compressed route tile at or below 500 KiB p95 for the defined reference dataset.
- No main-thread task longer than 200 ms caused by route decoding or layer updates.
- A p95 frame time at or below 33 ms during the defined pan/zoom interaction on the
  reference machine.
- Less than 20% retained-memory growth after ten identical filter/selection cycles once
  garbage collection and map idle are accounted for.

If the reference hardware cannot meet a budget for reasons outside the application,
the exception must include the trace, comparison baseline, and a replacement budget;
it cannot be waived by observation alone.

### 9.3 Phase 4 acceptance gate

Phase 4 is accepted only when all of the following are evidenced:

#### Geometry fidelity

- The selected trip uses unsimplified or fit-for-zoom geometry with the same provenance
  and quality as before Phase 4.
- Simplified lines keep all stops within the configured alignment tolerance and retain
  termini and significant junctions.
- A visual diff sample across MRT, LRT, Monorail, KTMB, Rapid Bus, and myBAS shows no
  route switching, large corner cutting, missing branch, or cross-water artifact
  introduced by simplification.
- Filtering and tile boundaries do not split visible routes with gaps or duplicate
  labels.

#### Contract and cache behavior

- The trip-detail response remains backward compatible with Phase 1.
- Tile requests outside documented bounds fail safely and do not generate unbounded
  work.
- A static or derivation version change produces a new immutable tile/cache key.
- Old tiles cannot be combined with new route metadata after activation.
- Vehicle SSE updates do not invalidate static route tiles.

#### Performance

- The complete measurement protocol is checked into the implementation evidence or
  linked from the delivery record.
- Every agreed response-size, latency, frame-time, long-task, and memory budget passes
  in both light and dark themes.
- The all-network overlay does not download a nationwide GeoJSON document.
- Repeated mode/operator/region filters reuse loaded tile data where safe and do not
  leak layers, sources, markers, or event handlers.

#### Product behavior

- The first usable map remains available while non-critical network-route tiles load.
- Slow or failed route-tile requests produce partial-coverage messaging and preserve
  vehicle list/detail operation.
- Keyboard, screen-reader, reduced-motion, map fallback, and attribution behavior from
  Phase 2 remains unchanged.
- Frontend test/check/build, focused backend tile/API tests, Compose smoke checks, and
  real-browser QA pass without console errors.

## 10. Cross-phase test matrix

| Surface | Required scenarios |
| --- | --- |
| Static import | Valid shapes, no shapes, orphan shape ID, duplicate sequence, invalid coordinate, distance regression, batch boundary, activation rollback. |
| Geometry resolver | Official precedence, derived precedence, approximate fallback, unavailable result, cache versioning, constant query count. |
| Trip API | GeoJSON coordinate order, provenance, route colours, unavailable geometry, malformed upstream data, no ETA fields. |
| Dashboard health | Official/derived/approximate/unavailable counts, active-version switch, zero-trip feed, cached summary. |
| Frontend schema | Every quality state, null geometry, malformed coordinates, invalid colour, unknown enum rejection. |
| Map layers | Casing/core order, dashed approximate style, derived attribution, station hierarchy, valid bearing, clusters, style reload. |
| Accessibility | Map/list equivalence, keyboard focus, visible status text, colour independence, reduced motion, 200% text zoom. |
| Browser reliability | Tile failure, missing key, WebGL failure, SSE interruption, dark mode, repeated theme/filter/selection cycles. |
| Performance | Cold/warm selected trip, tile cache miss/hit, national/city/station zooms, pan/zoom/filter trace, memory retention. |

## 11. Rollout and rollback

### 11.1 Rollout order

1. Apply the shape-point schema migration.
2. Deploy importer and geometry resolver with the existing frontend still using stops.
3. Re-import retained archives into staged immutable versions and inspect coverage.
4. Activate one representative bus feed and Rapid Rail; verify API and map artifacts.
5. Activate remaining feeds in bounded batches.
6. Deploy the frontend official/fallback treatments.
7. Add Phase 2 styles after Phase 1 geometry evidence is stable.
8. Run Phase 3 and Phase 4 only behind their documented entry gates.

### 11.2 Rollback

- Static data rollback uses the existing prior active feed version.
- Frontend rollback may stop consuming the new geometry field, but the additive API
  field can remain.
- A failed custom basemap style rolls back to the last known-good Civic signal style;
  it must not change route-geometry truth.
- A rejected derived alignment is deactivated independently and falls back through the
  source-priority rules.
- A vector-tile failure disables only the all-network overlay; selected-trip GeoJSON,
  stops, vehicles, list, and detail remain available.

No rollback may relabel approximate geometry as official or remove the required source
attribution.

## 12. Risks and mitigations

| Risk | Mitigation |
| --- | --- |
| Very large or malformed shapes exhaust memory. | Streaming/batched parsing, per-shape safety limit, bounded response, staged rejection. |
| Trip references a missing shape. | Warning plus explicit fallback; retain timetable and trip. |
| Route colour fails theme contrast. | Neutral casing, text label, contrast validation; never use colour alone. |
| Map style reload duplicates handlers or layers. | Stable layer IDs, idempotent add/remove lifecycle, repeated-theme test. |
| Derived KTMB path chooses the wrong branch. | Ordered-stop constraints, confidence gate, deterministic review report, safe fallback. |
| OSM-derived data is mistaken for official data. | Separate table/source value, visible attribution, `matched_infrastructure` label. |
| Premature vector-tile complexity delays correctness. | Phase 4 requires a performance trace and preserves selected-trip GeoJSON. |
| Geometry coverage computation slows dashboard requests. | Calculate during activation and cache/materialize by active version. |
| Upstream archive changes shape availability. | Report coverage on every activation; source priority automatically adopts valid official shapes. |

## 13. Completion definition

The overall initiative is complete when every entered phase has passed its acceptance
gate and the latest production-equivalent Compose build demonstrates:

- authoritative shapes for feeds that provide them;
- truthful and attributable fallback for feeds that do not;
- Civic signal map hierarchy in light and dark themes;
- map/list equivalence and WCAG 2.2 AA interaction behavior;
- no ETA or inferred movement semantics;
- bounded, measured performance at the implemented scale; and
- a rollback path that never weakens geometry provenance.

Phases 3 and 4 are optional entry-gated capabilities. Deferring either phase does not
block completion of Phases 1 and 2, provided KTMB remains visibly approximate or
unavailable and measured performance remains within the current selected-route
GeoJSON budget.
