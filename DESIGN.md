# Malaysia Transit Live Design System

## 1. Atmosphere & Identity

Malaysia Transit Live is a calm civic instrument: clear enough for a rushed commuter, disciplined enough for a public-data service. The signature is **signal clarity**—a cool, paper-like information surface interrupted only by meaningful transport colours: blue for action, amber for scheduled time, teal for verified live data, and red for failure. The map is a quiet geographical layer, never a decorative dashboard backdrop. This system recombines the restrained editorial structure of `minimalist-ui` with the token discipline, typographic precision, and tonal layering of IBM Carbon; it does not copy either brand.

Never use purple, gradients, glassmorphism, large rounded cards, emojis, generic AI language, or colour as the only status indicator. Use plain, specific labels such as “Scheduled only”, “Live 42s ago”, and “No active service for this date”.

## 2. Color

### Palette

| Role | Token | Light | Dark | Usage |
| --- | --- | --- | --- | --- |
| Canvas | `--surface-canvas` | `#F7F9FC` | `#101820` | Application background |
| Surface | `--surface-primary` | `#FFFFFF` | `#17232D` | Main panels and pages |
| Muted surface | `--surface-muted` | `#EDF1F5` | `#20303B` | Tables, grouped controls, map panels |
| Raised surface | `--surface-raised` | `#FFFFFF` | `#263845` | Menus and dialogs only |
| Text primary | `--text-primary` | `#14202B` | `#F0F5F8` | Headings and core content |
| Text secondary | `--text-secondary` | `#53616D` | `#B6C4CD` | Supporting content |
| Text disabled | `--text-disabled` | `#7B8791` | `#81909A` | Disabled controls only |
| Border | `--border-default` | `#CDD6DE` | `#334957` | Dividers and input baseline |
| Interactive | `--action-primary` | `#075EA8` | `#79BEFF` | Links, actions, selected state |
| Interactive hover | `--action-hover` | `#064A86` | `#B4DBFF` | Hover and active link state |
| Scheduled | `--status-scheduled` | `#9A5800` | `#FFC26B` | Planned time and scheduled-only state |
| Live | `--status-live` | `#00766D` | `#58D7C5` | Fresh validated vehicle data |
| Warning | `--status-warning` | `#8A5A00` | `#F2C46D` | Stale or incomplete source data |
| Error | `--status-error` | `#B42318` | `#FF9B94` | Failures and destructive actions |
| Info | `--status-info` | `#075EA8` | `#79BEFF` | Informational messages |
| Focus | `--focus-ring` | `#075EA8` | `#B4DBFF` | 3px visible focus outline |

### Rules

- Route colours from GTFS are informative only. Pair each with a route name/number and select foreground text that passes contrast requirements.
- `--status-live` never means an ETA. It means a validated Vehicle Position is recent enough for the documented freshness threshold.
- Use `--surface-*` tonal steps for depth; use shadows only for a truly overlapping menu, popover, or dialog.
- Map styles are low-saturation Civic signal variants. MapTiler attribution remains visible in every theme. The public MapTiler key is restricted to the production origin. See [MapTiler key protection](https://docs.maptiler.com/cloud/api/authentication-key/) and [attribution requirements](https://docs.maptiler.com/guides/map-design/attribution/add-attribution/).

## 3. Typography

### Font Stack

- Primary: `IBM Plex Sans, ui-sans-serif, system-ui, sans-serif`
- Mono: `IBM Plex Mono, ui-monospace, SFMono-Regular, monospace`

Use two font families only. Load self-hosted or trusted font files with `font-display: swap`; never fall back silently to Inter or Roboto as the intended product font.

### Scale

| Level | Size | Weight | Line height | Tracking | Usage |
| --- | --- | --- | --- | --- | --- |
| Display | `clamp(2rem, 4vw, 3.75rem)` | 300 | 1.17 | 0 | Page title |
| H1 | 2.625rem | 300 | 1.19 | 0 | Route/stop title |
| H2 | 2rem | 400 | 1.25 | 0 | Main section title |
| H3 | 1.5rem | 400 | 1.33 | 0 | Panel title |
| H4 | 1.25rem | 600 | 1.4 | 0 | Card title |
| Body | 1rem | 400 | 1.5 | 0 | Default content |
| Body compact | 0.875rem | 400 | 1.29 | 0.16px | Lists and search results |
| Label | 0.75rem | 600 | 1.33 | 0.32px | Labels and metadata |
| Time/meta | 0.875rem | 400 | 1.43 | 0.16px | Dates, times, feed IDs |

Times, route codes, feed IDs, freshness ages, and keyboard hints use the mono stack. Body copy never falls below 14px.

## 4. Spacing & Layout

### Base Unit

All spacing derives from 8px. Use `--space-1` 4px only for compact icon/text alignment.

| Token | Value | Usage |
| --- | --- | --- |
| `--space-1` | 4px | Icon gap, fine adjustment |
| `--space-2` | 8px | Compact inline group |
| `--space-3` | 12px | Row padding |
| `--space-4` | 16px | Standard panel padding |
| `--space-5` | 24px | Card padding |
| `--space-6` | 32px | Group separation |
| `--space-7` | 48px | Page section separation |
| `--space-8` | 64px | Major page separation |

### Grid and Breakpoints

- 375px: one column, 16px page gutter, persistent search, map/list switcher.
- 768px: 12-column grid, 24px gutter, results and contextual map may coexist.
- 1280px: 12-column grid, 32px gutter, max content width 1440px; map may occupy 5 columns beside a 7-column information panel.
- Respect device safe areas and use `min-height: 100dvh` for full-height application areas.
- Do not hide information behind a map. Every vehicle, route, and stop in a map layer has an equivalent list/detail path.

## 5. Components

Use shadcn/ui primitives first. Use `@phosphor-icons/react` for SVG icons; set icon size, stroke/weight, accessible name, and touch target through component tokens. The favicon is a hand-authored SVG signal mark, not a text glyph.

### AppShell

- **Structure:** skip link, compact masthead, primary search, route content, contextual map/list region, footer/source attribution.
- **Variants:** desktop split view, mobile stacked view, map-hidden detail view.
- **States:** default, navigation expanded, offline, dark mode.
- **Accessibility:** landmark regions, logical focus order, visible skip link, no auto-focus theft.

### CommandSearch

- **Structure:** labelled input, mode/feed filters, result list, empty and error message. Results group scheduled trips, static routes, stops, and validated live vehicles without conflating their freshness states.
- **Variants:** header compact, page large, keyboard-invoked overlay.
- **States:** idle, typing, loading, results, no match, partial static coverage, request error.
- **Accessibility:** native input semantics, listbox only where keyboard selection is implemented, result count announced without verbose live-region spam.
- **Interaction:** selecting a scheduled trip makes it the map focus; selecting a vehicle makes that vehicle the map focus. Each action replaces the prior focus so a route-card action always remains effective after a vehicle selection.

### ServiceJourneyCard

- **Structure:** mode icon, route badge, origin, destination, service date, planned start/end, stops summary, freshness status.
- **Variants:** search result, route list item, trip detail hero.
- **States:** scheduled only, live, stale, unavailable, no service for date.
- **Accessibility:** status icon and text; dates/times use localised semantic `<time>` values even while visible UI is English.

### StationBoard

- **Structure:** stop identity, selected service date, departure rows, route and headsign, planned departure, status.
- **States:** loading, active service, no departures, out-of-service date, partial feed coverage, source failure.
- **Accessibility:** table semantics on wide screens; equivalent labelled list on narrow screens.

### FreshnessBadge and DataStatusNotice

- **Structure:** semantic icon, concise status label, last update time, optional explanation link.
- **Variants:** live, stale, scheduled only, unavailable, import in progress.
- **Rules:** no pill larger than content; do not use colour alone; stale and unavailable cannot visually resemble live.

### TransitMap and VehicleMarker

- **Structure:** MapLibre canvas, SVG vehicle symbols, SVG route/station symbols, keyboard-accessible map controls, legend, list alternative.
- **Variants:** route shape, vehicle cluster, selected vehicle, no-live-data.
- **States:** loading tiles, loading vehicles, map unavailable, WebGL unavailable, reduced-data fallback.
- **Accessibility:** offer “View as list”; markers are not the sole control surface. A selected marker opens the same detail panel as its list row.
- **Commuter context:** selected vehicles show their current coordinates and next **scheduled** stop with planned time. This is never labelled as an ETA because upstream realtime data supplies positions, not arrival predictions.

### FilterPanel and LocalFavourite

- **Structure:** shadcn Sheet/Popover controls with feed, mode, date, and map visibility selectors; favourite toggle uses local browser storage only.
- **States:** default, selected, disabled, loading, persistence denied.
- **Accessibility:** Escape closes overlays, focus returns to trigger, every icon button has a text label for assistive technology.

### Dashboard workspaces

The AppShell exposes two switchable, URL-addressable workspaces that share one
cascading single-select filter row: mode → canonical operator → city/metro region.
Each select keeps an “All” option, clears child filters when its parent changes, and
has an inline no-results state.

- **Network overview:** summary counts, MapLibre vehicle context, an equivalent
  keyboard-accessible list, and selected-vehicle detail. Detail shows coordinates,
  route/trip, GTFS agency, freshness label, and the next timetable stop; it never says
  ETA. `Verified live`, `Live feed stale`, `Scheduled only`, and `Source unavailable`
  always include text and semantic status treatment.
- **Service health:** dense sortable table with feed, canonical operator, city, agency,
  normalized modes, static/realtime state, last successful fetch, and live/stale/
  unclassified vehicle counts. Scheduled-only, awaiting-first-fetch, and unavailable
  use distinct labelled status treatments.
- **Responsive behavior:** 375px and 768px stack the workspaces and expose a map/list
  switcher; the 1280px layout uses a 12-column split. A safety-cap notice offers
  “Load more vehicles”. Errors, empty data, partial coverage, SSE interruption, and
  map/WebGL failure use inline notices rather than modal-first recovery.

The product is read-only and public. Preserve Civic signal palette, IBM Plex, existing
light/dark/system tokens, tinted surfaces, hairline borders, 0–4px radii, and 44px
touch targets. Do not add purple, gradients, glassmorphism, decorative motion, nested
cards, or side-stripe vehicle controls. Motion is limited to transform/opacity at
150–220ms and disabled for reduced-motion users.

## 6. Motion & Interaction

| Type | Duration | Easing | Usage |
| --- | --- | --- | --- |
| Press | 100ms | ease-out | Button/row active response |
| Standard | 180–220ms | ease-in-out | Sheet, tab, and filter transitions |
| Emphasis | 300ms | cubic-bezier(0.16, 1, 0.3, 1) | Detail panel entry only |

- Animate only `transform`, `opacity`, and carefully bounded `filter`.
- Vehicle updates interpolate position only when a newer validated snapshot exists; never animate a stale vehicle as though it is live.
- `prefers-reduced-motion` disables non-essential transitions and all vehicle interpolation.
- Hover must not be the only way to reveal a label, status, or action.

## 7. Depth & Surface

### Strategy: Tonal Shift With Hairline Borders

- Default pages use `--surface-canvas` behind `--surface-primary` information regions.
- Grouped information uses `--surface-muted`; menus/dialogs use `--surface-raised` and may use `0 8px 24px rgba(20, 32, 43, 0.14)`.
- Cards, rows, buttons, and inputs use 0–4px corner radius. Tags may use a small capsule only when they are compact status labels.
- Inputs use a 2px bottom border as their resting and focus identity; do not draw heavy boxed fields.
- Primary controls are rectangular with a 48px standard height. Every pointer target is at least 44×44px.

## Accessibility and QA Contract

The implementation target is WCAG 2.2 AA. Test keyboard navigation, focus visibility, screen-reader labels, contrast, zoom, system dark mode, reduced motion, and text resizing for all listed components. Before a screen is accepted, verify default, hover, active, focus, disabled, loading, empty, error, stale, and dark states at 375px, 768px, and 1280px in a real browser.

Design debt is zero for v1: no placeholder UI, unexplained token, raw colour, arbitrary spacing value, raster icon, or unlabelled icon-only control may ship.
