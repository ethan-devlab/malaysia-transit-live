import { List, MapTrifold, Table, WarningCircle } from "@phosphor-icons/react"
import { useEffect, useMemo, useState } from "react"

import { type DashboardFilterState, DashboardFilters } from "@/components/dashboard-filters"
import { NetworkMapPanel } from "@/components/network-map-panel"
import { Button } from "@/components/ui/button"
import type { NetworkFocus } from "@/domain/transit"
import { useDashboard } from "@/hooks/use-dashboard"
import { toValidatedVehicle } from "@/hooks/use-transit-board"
import {
  type DashboardMode,
  type DashboardSource,
  type DashboardVehicle,
  fetchDashboard,
} from "@/lib/dashboard-api"

type WorkspaceView = "network" | "health"
type SortKey = "feed" | "realtime_state" | "vehicle_count"

const modeLabels: Readonly<Record<DashboardMode, string>> = {
  all: "All services",
  bus: "Bus",
  mrt: "MRT",
  lrt: "LRT",
  monorail: "Monorail",
  rail: "Rail",
  unknown: "Unclassified",
}

const stateLabels = {
  available: "Verified live",
  awaiting_first_fetch: "Awaiting first fetch",
  scheduled_only: "Scheduled only",
  unavailable: "Source unavailable",
} as const

// allow: SIZE_OK — one workspace state machine coordinates its views and local state.
export function DashboardWorkspace({ isDark }: { readonly isDark: boolean }) {
  const [view, setView] = useState<WorkspaceView>(() => readView())
  const [filters, setFilters] = useState<DashboardFilterState>(() => readFilters())
  const [selectedVehicleId, setSelectedVehicleId] = useState("")
  const [focus, setFocus] = useState<NetworkFocus>()
  const [mapVisible, setMapVisible] = useState(true)
  const [sortKey, setSortKey] = useState<SortKey>("feed")
  const [sortAscending, setSortAscending] = useState(true)
  const [extraVehicles, setExtraVehicles] = useState<readonly DashboardVehicle[]>([])
  const [nextCursor, setNextCursor] = useState<string | null>(null)
  const [loadError, setLoadError] = useState(false)
  const query = {
    mode: filters.mode,
    operator: filters.operator,
    region: filters.region,
    limit: 100,
  }
  const dashboardQuery = useDashboard(query)
  const data = dashboardQuery.data
  useEffect(() => {
    setExtraVehicles([])
    setNextCursor(data?.vehicles.next_cursor ?? null)
  }, [data?.vehicles.next_cursor])
  const vehicles = useMemo(() => {
    const base = data?.vehicles.items ?? []
    const known = new Set(base.map((vehicle) => `${vehicle.feed}:${vehicle.vehicle_id}`))
    return [
      ...base,
      ...extraVehicles.filter((vehicle) => !known.has(`${vehicle.feed}:${vehicle.vehicle_id}`)),
    ]
  }, [data?.vehicles.items, extraVehicles])
  const selectedVehicle = vehicles.find(
    (vehicle) => `${vehicle.feed}:${vehicle.vehicle_id}` === selectedVehicleId,
  )
  const mapVehicles = useMemo(
    () =>
      vehicles.map((vehicle) =>
        toValidatedVehicle({
          bearing: vehicle.bearing,
          fetched_at: vehicle.fetched_at,
          feed: vehicle.feed,
          freshness: vehicle.freshness,
          latitude: vehicle.latitude,
          longitude: vehicle.longitude,
          mode: vehicle.mode,
          position_reported_at: vehicle.position_reported_at,
          route_id: vehicle.route_id,
          speed_metres_per_second: vehicle.speed_metres_per_second,
          static_version_id: vehicle.static_version_id,
          trip_id: vehicle.trip_id,
          vehicle_id: vehicle.vehicle_id,
        }),
      ),
    [vehicles],
  )
  const sources = useMemo(
    () => sortSources(data?.sources ?? [], sortKey, sortAscending),
    [data?.sources, sortAscending, sortKey],
  )

  function changeView(nextView: WorkspaceView) {
    setView(nextView)
    writeUrl(nextView, filters)
  }

  function changeFilters(next: DashboardFilterState) {
    setFilters(next)
    setExtraVehicles([])
    setNextCursor(null)
    setSelectedVehicleId("")
    setFocus(undefined)
    writeUrl(view, next)
  }

  function selectVehicle(vehicle: DashboardVehicle) {
    const id = `${vehicle.feed}:${vehicle.vehicle_id}`
    setSelectedVehicleId(id)
    setFocus((current) => ({ id, kind: "vehicle", revision: (current?.revision ?? 0) + 1 }))
    setMapVisible(true)
  }

  async function loadMore() {
    if (!nextCursor) return
    setLoadError(false)
    try {
      const next = await fetchDashboard({ ...query, cursor: nextCursor })
      setExtraVehicles((current) => [...current, ...next.vehicles.items])
      setNextCursor(next.vehicles.next_cursor)
    } catch {
      setLoadError(true)
    }
  }

  return (
    <section aria-labelledby="dashboard-heading" className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4 border-b border-border pb-5">
        <div>
          <p className="font-mono text-xs font-semibold tracking-wide text-primary uppercase">
            Network monitor
          </p>
          <h2 id="dashboard-heading" className="mt-1 text-2xl font-semibold">
            Live vehicles and source health
          </h2>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-muted-foreground">
            Complete filtered coverage for when you need to inspect all services, including
            scheduled-only sources.
          </p>
        </div>
        <fieldset className="flex gap-2">
          <legend className="sr-only">Network monitor workspace</legend>
          <Button
            aria-pressed={view === "network"}
            className={
              view === "network"
                ? "bg-[color:var(--action-hover)] hover:bg-[color:var(--action-primary)]"
                : undefined
            }
            onClick={() => changeView("network")}
            type="button"
            variant={view === "network" ? "default" : "outline"}
          >
            <MapTrifold aria-hidden="true" /> Network overview
          </Button>
          <Button
            aria-pressed={view === "health"}
            className={
              view === "health"
                ? "bg-[color:var(--action-hover)] hover:bg-[color:var(--action-primary)]"
                : undefined
            }
            onClick={() => changeView("health")}
            type="button"
            variant={view === "health" ? "default" : "outline"}
          >
            <Table aria-hidden="true" /> Service health
          </Button>
        </fieldset>
      </div>
      <DashboardFilters data={data} onChange={changeFilters} value={filters} />
      {dashboardQuery.isError ? (
        <InlineNotice tone="error">
          Dashboard data is unavailable. The last valid snapshot remains safe to use when available.
        </InlineNotice>
      ) : null}
      {data && view === "network" ? (
        <NetworkOverview
          data={data}
          isDark={isDark}
          loadError={loadError}
          mapVisible={mapVisible}
          onLoadMore={loadMore}
          hasMore={nextCursor !== null}
          onSelectVehicle={selectVehicle}
          onToggleMap={() => setMapVisible((visible) => !visible)}
          focus={focus}
          mapVehicles={mapVehicles}
          selectedVehicle={selectedVehicle}
          vehicles={vehicles}
        />
      ) : null}
      {data && view === "health" ? (
        <HealthOverview
          onSort={(nextKey) => {
            if (sortKey === nextKey) setSortAscending((ascending) => !ascending)
            else {
              setSortKey(nextKey)
              setSortAscending(true)
            }
          }}
          sortAscending={sortAscending}
          sortKey={sortKey}
          sources={sources}
        />
      ) : null}
      {import.meta.env.PROD && dashboardQuery.isPending && !data ? (
        <p aria-live="polite" className="text-sm text-muted-foreground">
          Loading dashboard snapshot…
        </p>
      ) : null}
      {data && data.summary.vehicle_count === 0 ? (
        <InlineNotice tone="neutral">
          No vehicles match these filters. Scheduled services and source health remain available in
          Service health.
        </InlineNotice>
      ) : null}
    </section>
  )
}

function NetworkOverview({
  data,
  focus,
  isDark,
  loadError,
  mapVisible,
  mapVehicles,
  onLoadMore,
  hasMore,
  onSelectVehicle,
  onToggleMap,
  selectedVehicle,
  vehicles,
}: {
  readonly data: NonNullable<ReturnType<typeof useDashboard>["data"]>
  readonly focus: NetworkFocus | undefined
  readonly isDark: boolean
  readonly loadError: boolean
  readonly mapVisible: boolean
  readonly mapVehicles: ReturnType<typeof toValidatedVehicle>[]
  readonly onLoadMore: () => void
  readonly hasMore: boolean
  readonly onSelectVehicle: (vehicle: DashboardVehicle) => void
  readonly onToggleMap: () => void
  readonly selectedVehicle: DashboardVehicle | undefined
  readonly vehicles: readonly DashboardVehicle[]
}) {
  return (
    <div className="grid gap-6 xl:grid-cols-12">
      <div className="space-y-4 xl:col-span-7">
        <dl className="grid grid-cols-2 border-y border-border sm:grid-cols-4 sm:divide-x sm:divide-border">
          <Metric label="Vehicles" value={data.summary.vehicle_count} />
          <Metric label="Verified live" value={data.summary.live_vehicle_count} />
          <Metric label="Stale" value={data.summary.stale_vehicle_count} />
          <Metric label="Feeds" value={data.summary.feed_count} />
        </dl>
        <div className="flex items-center justify-between gap-3 sm:hidden">
          <p className="text-sm font-medium">{mapVisible ? "Map" : "Vehicle list"}</p>
          <Button onClick={onToggleMap} type="button" variant="outline">
            <List aria-hidden="true" /> {mapVisible ? "Show list" : "Show map"}
          </Button>
        </div>
        <div className={mapVisible ? "block min-h-72" : "hidden sm:block"}>
          <NetworkMapPanel
            afterMapCanvas={
              selectedVehicle ? <SelectedVehicleDetail vehicle={selectedVehicle} /> : undefined
            }
            eyebrow="Network coverage"
            focus={focus}
            heading="Live vehicle positions"
            isDark={isDark}
            landmarkLabel="Dashboard network map"
            onSelectVehicle={(id) => {
              const vehicle = vehicles.find(
                (candidate) => `${candidate.feed}:${candidate.vehicle_id}` === id,
              )
              if (vehicle) onSelectVehicle(vehicle)
            }}
            selectedJourney={undefined}
            showVehicleControls={false}
            vehicles={mapVehicles}
          />
        </div>
      </div>
      <section aria-labelledby="vehicle-list-heading" className="space-y-3 xl:col-span-5">
        <div className="flex items-end justify-between gap-3 border-b border-border pb-3">
          <div>
            <p className="font-mono text-xs font-semibold tracking-wide text-muted-foreground uppercase">
              Equivalent list
            </p>
            <h3 id="vehicle-list-heading" className="mt-1 text-xl font-semibold">
              Vehicle positions
            </h3>
          </div>
          <p className="text-sm text-muted-foreground">
            {vehicles.length} shown / {data.vehicles.total_count} total
          </p>
        </div>
        {hasMore ? (
          <InlineNotice tone="neutral">
            Safety cap reached for this snapshot. Load more from the list to retrieve the remaining
            positions.
          </InlineNotice>
        ) : null}
        {loadError ? (
          <InlineNotice tone="error">The next vehicle page could not be loaded.</InlineNotice>
        ) : null}
        <div className="grid h-[34rem] min-h-0 grid-rows-[minmax(0,1fr)_auto] overflow-hidden border border-border bg-muted/20">
          <section
            aria-label="Vehicle position rows"
            className="min-h-0 overflow-y-auto overscroll-contain [scrollbar-gutter:stable]"
          >
            <ul className="space-y-2 p-3">
              {vehicles.map((vehicle) => {
                const id = `${vehicle.feed}:${vehicle.vehicle_id}`
                return (
                  <li key={id}>
                    <button
                      aria-pressed={
                        selectedVehicle?.vehicle_id === vehicle.vehicle_id &&
                        selectedVehicle.feed === vehicle.feed
                      }
                      className="flex min-h-16 w-full items-start justify-between gap-3 border border-border bg-muted/20 p-3 text-left hover:bg-muted/45 focus-visible:outline-3 focus-visible:outline-offset-2 focus-visible:outline-[color:var(--focus-ring)]"
                      onClick={() => onSelectVehicle(vehicle)}
                      type="button"
                    >
                      <span className="min-w-0">
                        <span className="block break-words font-medium [overflow-wrap:anywhere]">
                          {vehicle.route_id || "Unclassified route"} · {vehicle.vehicle_id}
                        </span>
                        <span className="mt-1 block break-words text-xs text-muted-foreground [overflow-wrap:anywhere]">
                          {[
                            vehicle.operator_name,
                            vehicle.region_name,
                            modeLabels[vehicle.mode],
                          ].join(" · ")}
                        </span>
                      </span>
                      <StatusBadge
                        status={vehicle.freshness === "live" ? "available" : "awaiting_first_fetch"}
                      >
                        {vehicle.freshness === "live" ? "Verified live" : "Live feed stale"}
                      </StatusBadge>
                    </button>
                  </li>
                )
              })}
            </ul>
          </section>
          {hasMore ? (
            <div className="border-t border-border bg-[color:var(--surface-primary)] p-3 shadow-[0_-8px_16px_color-mix(in_srgb,var(--surface-primary)_85%,transparent)]">
              <Button className="w-full" onClick={onLoadMore} type="button" variant="outline">
                Load more vehicles
              </Button>
            </div>
          ) : null}
        </div>
      </section>
    </div>
  )
}

function SelectedVehicleDetail({ vehicle }: { readonly vehicle: DashboardVehicle }) {
  return (
    <section
      aria-labelledby="selected-vehicle-heading"
      className="border-t border-border pt-4"
      data-selected-vehicle-detail=""
    >
      <p className="font-mono text-xs tracking-wide text-muted-foreground uppercase">
        Selected vehicle
      </p>
      <h3 className="mt-1 font-semibold" id="selected-vehicle-heading">
        {vehicle.vehicle_id}
      </h3>
      <div className="mt-2">
        <StatusBadge status={vehicle.freshness === "live" ? "live" : "stale"}>
          {vehicle.freshness === "live" ? "Verified live" : "Live feed stale"}
        </StatusBadge>
      </div>
      <dl className="mt-3 grid gap-3 text-sm sm:grid-cols-2">
        <div className="min-w-0">
          <dt className="text-muted-foreground">Coordinates</dt>
          <dd className="mt-0.5 font-mono">
            {vehicle.latitude.toFixed(5)}, {vehicle.longitude.toFixed(5)}
          </dd>
        </div>
        <div className="min-w-0">
          <dt className="text-muted-foreground">Route / trip</dt>
          <dd className="mt-0.5 break-words [overflow-wrap:anywhere]">
            {vehicle.route_id || "Unclassified"} / {vehicle.trip_id || "Not reported"}
          </dd>
        </div>
        <div className="min-w-0">
          <dt className="text-muted-foreground">Agency</dt>
          <dd className="mt-0.5 break-words [overflow-wrap:anywhere]">
            {vehicle.agency_names.join(", ") || "Not in static metadata"}
          </dd>
        </div>
        <div className="min-w-0">
          <dt className="text-muted-foreground">Next scheduled stop</dt>
          <dd className="mt-0.5 break-words [overflow-wrap:anywhere]">
            {vehicle.next_scheduled_stop ?? "No timetable stop supplied"}
          </dd>
        </div>
      </dl>
      <p className="mt-3 text-xs text-muted-foreground">
        Times and next stop are timetable/source timestamps, never ETA predictions.
      </p>
    </section>
  )
}

function HealthOverview({
  onSort,
  sortAscending,
  sortKey,
  sources,
}: {
  readonly onSort: (key: SortKey) => void
  readonly sortAscending: boolean
  readonly sortKey: SortKey
  readonly sources: readonly DashboardSource[]
}) {
  return (
    <section aria-labelledby="health-table-heading" className="space-y-4">
      <div className="flex items-end justify-between gap-3 border-b border-border pb-3">
        <div>
          <p className="font-mono text-xs font-semibold tracking-wide text-muted-foreground uppercase">
            Feed coverage
          </p>
          <h3 id="health-table-heading" className="mt-1 text-xl font-semibold">
            Source health summary
          </h3>
        </div>
        <p className="text-sm text-muted-foreground">{sources.length} feeds</p>
      </div>
      <div className="overflow-x-auto border border-border">
        <table className="w-full min-w-[66rem] text-left text-sm">
          <caption className="sr-only">
            Static, realtime, and route geometry health for each official transit feed
          </caption>
          <thead className="bg-muted/45 text-xs uppercase tracking-wide text-muted-foreground">
            <tr>
              <SortableHeader
                label="Feed"
                sortKey="feed"
                activeKey={sortKey}
                ascending={sortAscending}
                onSort={onSort}
              />
              <th className="px-3 py-3">Operator / city</th>
              <th className="px-3 py-3">Modes</th>
              <SortableHeader
                label="Realtime"
                sortKey="realtime_state"
                activeKey={sortKey}
                ascending={sortAscending}
                onSort={onSort}
              />
              <SortableHeader
                label="Vehicles"
                sortKey="vehicle_count"
                activeKey={sortKey}
                ascending={sortAscending}
                onSort={onSort}
              />
              <th className="px-3 py-3">Route geometry</th>
              <th className="px-3 py-3">Last success</th>
            </tr>
          </thead>
          <tbody>
            {sources.map((source) => (
              <tr className="border-t border-border align-top" key={source.feed}>
                <td className="px-3 py-3 font-medium">
                  {source.display_name}
                  <span className="mt-1 block font-mono text-xs text-muted-foreground">
                    {source.feed}
                  </span>
                </td>
                <td className="px-3 py-3">
                  {source.operator_name}
                  <span className="mt-1 block text-muted-foreground">{source.region_name}</span>
                  {source.agency_names.length ? (
                    <span className="mt-1 block text-xs text-muted-foreground">
                      {source.agency_names.join(", ")}
                    </span>
                  ) : null}
                </td>
                <td className="px-3 py-3">
                  {source.modes.length
                    ? source.modes.map((mode) => modeLabels[mode]).join(", ")
                    : "Unclassified"}
                </td>
                <td className="px-3 py-3">
                  <StatusBadge status={source.realtime_state}>
                    {stateLabels[source.realtime_state]}
                  </StatusBadge>
                  <span className="mt-2 block text-xs text-muted-foreground">
                    Static: {source.static_state === "active" ? "Active" : "Unavailable"}
                  </span>
                </td>
                <td className="px-3 py-3">
                  {source.vehicle_count}
                  <span className="mt-1 block text-xs text-muted-foreground">
                    {source.live_vehicle_count} live · {source.stale_vehicle_count} stale ·{" "}
                    {source.unknown_vehicle_count} unknown
                  </span>
                </td>
                <td className="px-3 py-3">
                  {source.geometry_coverage.official_shape_count} /{" "}
                  {source.geometry_coverage.trip_count} official
                  <span className="mt-1 block text-xs text-muted-foreground">
                    {source.geometry_coverage.matched_infrastructure_count} matched ·{" "}
                    {source.geometry_coverage.stop_sequence_count} approximate ·{" "}
                    {source.geometry_coverage.unavailable_count} unavailable
                  </span>
                </td>
                <td className="px-3 py-3 text-xs text-muted-foreground">
                  <span className="block">
                    Realtime:{" "}
                    {source.last_successful_realtime_fetch_at
                      ? formatTime(source.last_successful_realtime_fetch_at)
                      : "No successful fetch"}
                  </span>
                  <span className="mt-1 block">
                    Static:{" "}
                    {source.last_successful_static_fetch_at
                      ? formatTime(source.last_successful_static_fetch_at)
                      : "No successful fetch"}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}

function SortableHeader({
  activeKey,
  ascending,
  label,
  onSort,
  sortKey,
}: {
  readonly activeKey: SortKey
  readonly ascending: boolean
  readonly label: string
  readonly onSort: (key: SortKey) => void
  readonly sortKey: SortKey
}) {
  return (
    <th className="px-3 py-3">
      <button
        className="min-h-8 font-semibold hover:underline"
        onClick={() => onSort(sortKey)}
        type="button"
      >
        {label}
        {activeKey === sortKey ? ` ${ascending ? "↑" : "↓"}` : ""}
      </button>
    </th>
  )
}

function StatusBadge({
  children,
  status,
}: {
  readonly children: string
  readonly status: keyof typeof stateLabels | "live" | "stale"
}) {
  const tone =
    status === "available" || status === "live"
      ? "border-[color:var(--status-live-border)] bg-[color:var(--status-live-background)] text-[color:var(--status-live-foreground)]"
      : status === "scheduled_only" || status === "awaiting_first_fetch" || status === "stale"
        ? "border-[color:var(--status-warning-border)] bg-[color:var(--status-warning-background)] text-[color:var(--status-warning-foreground)]"
        : "border-[color:var(--status-error-border)] bg-[color:var(--status-error-background)] text-[color:var(--status-error-foreground)]"
  return (
    <span className={`inline-flex items-center border px-2 py-1 text-xs font-medium ${tone}`}>
      {children}
    </span>
  )
}

function Metric({ label, value }: { readonly label: string; readonly value: number }) {
  return (
    <div className="p-3 sm:px-4">
      <dt className="font-mono text-xs tracking-wide text-muted-foreground uppercase">{label}</dt>
      <dd className="mt-1 text-2xl font-semibold tabular-nums">{value}</dd>
    </div>
  )
}

function InlineNotice({
  children,
  tone,
}: {
  readonly children: string
  readonly tone: "error" | "neutral"
}) {
  return (
    <div
      className={`flex items-start gap-2 border px-3 py-3 text-sm ${tone === "error" ? "border-[color:var(--status-error-border)] bg-[color:var(--status-error-background)] text-[color:var(--status-error-foreground)]" : "border-border bg-muted/30 text-muted-foreground"}`}
      role="status"
    >
      <WarningCircle aria-hidden="true" size={18} /> <span>{children}</span>
    </div>
  )
}

function sortSources(
  sources: readonly DashboardSource[],
  key: SortKey,
  ascending: boolean,
): readonly DashboardSource[] {
  return [...sources].sort((left, right) => {
    const leftValue =
      key === "feed"
        ? left.feed
        : key === "realtime_state"
          ? left.realtime_state
          : left.vehicle_count
    const rightValue =
      key === "feed"
        ? right.feed
        : key === "realtime_state"
          ? right.realtime_state
          : right.vehicle_count
    const comparison =
      typeof leftValue === "number" && typeof rightValue === "number"
        ? leftValue - rightValue
        : String(leftValue).localeCompare(String(rightValue))
    return ascending ? comparison : -comparison
  })
}

function formatTime(value: string): string {
  return new Intl.DateTimeFormat("en-MY", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "Asia/Kuala_Lumpur",
  }).format(new Date(value))
}

function readView(): WorkspaceView {
  return new URLSearchParams(window.location.search).get("view") === "health" ? "health" : "network"
}

function readFilters(): DashboardFilterState {
  const params = new URLSearchParams(window.location.search)
  const value = params.get("mode")
  const mode: DashboardMode =
    value === "bus" ||
    value === "mrt" ||
    value === "lrt" ||
    value === "monorail" ||
    value === "rail" ||
    value === "unknown"
      ? value
      : "all"
  return { mode, operator: params.get("operator") ?? "", region: params.get("region") ?? "" }
}

function writeUrl(view: WorkspaceView, filters: DashboardFilterState) {
  const params = new URLSearchParams(window.location.search)
  params.set("view", view)
  if (filters.mode === "all") params.delete("mode")
  else params.set("mode", filters.mode)
  if (filters.operator) params.set("operator", filters.operator)
  else params.delete("operator")
  if (filters.region) params.set("region", filters.region)
  else params.delete("region")
  window.history.replaceState({}, "", `${window.location.pathname}?${params.toString()}`)
}
