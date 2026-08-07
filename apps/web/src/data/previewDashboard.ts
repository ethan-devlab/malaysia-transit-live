import type { Dashboard, DashboardMode, DashboardQuery } from "@/lib/dashboard-api"

const previewNow = new Date().toISOString()
const previewStale = new Date(Date.now() - 180_000).toISOString()

const previewSources: Dashboard["sources"] = [
  {
    feed: "rapid-kl",
    display_name: "Rapid KL",
    operator_key: "rapid-kl",
    operator_name: "Rapid KL",
    region_key: "kuala-lumpur",
    region_name: "Kuala Lumpur",
    agency_names: ["Rapid Rail Sdn Bhd", "Rapid Bus Sdn Bhd"],
    modes: ["bus", "mrt", "lrt", "monorail"],
    static_state: "active",
    realtime_state: "available",
    last_successful_static_fetch_at: previewNow,
    last_successful_realtime_fetch_at: previewNow,
    vehicle_count: 2,
    live_vehicle_count: 1,
    stale_vehicle_count: 1,
    unknown_vehicle_count: 0,
  },
  {
    feed: "ktmb",
    display_name: "KTMB",
    operator_key: "ktmb",
    operator_name: "KTMB",
    region_key: "national",
    region_name: "Malaysia",
    agency_names: ["Keretapi Tanah Melayu Berhad"],
    modes: ["rail"],
    static_state: "active",
    realtime_state: "awaiting_first_fetch",
    last_successful_static_fetch_at: previewNow,
    last_successful_realtime_fetch_at: null,
    vehicle_count: 1,
    live_vehicle_count: 0,
    stale_vehicle_count: 1,
    unknown_vehicle_count: 0,
  },
  {
    feed: "rapid-penang",
    display_name: "Rapid Penang",
    operator_key: "rapid-penang",
    operator_name: "Rapid Penang",
    region_key: "penang",
    region_name: "Penang",
    agency_names: ["Rapid Penang Sdn Bhd"],
    modes: ["bus"],
    static_state: "active",
    realtime_state: "scheduled_only",
    last_successful_static_fetch_at: previewNow,
    last_successful_realtime_fetch_at: null,
    vehicle_count: 0,
    live_vehicle_count: 0,
    stale_vehicle_count: 0,
    unknown_vehicle_count: 0,
  },
  {
    feed: "mybas-kuching",
    display_name: "myBAS Kuching",
    operator_key: "bas-my",
    operator_name: "myBAS",
    region_key: "kuching",
    region_name: "Kuching",
    agency_names: [],
    modes: ["unknown"],
    static_state: "unavailable",
    realtime_state: "unavailable",
    last_successful_static_fetch_at: null,
    last_successful_realtime_fetch_at: null,
    vehicle_count: 0,
    live_vehicle_count: 0,
    stale_vehicle_count: 0,
    unknown_vehicle_count: 0,
  },
]

const previewVehicles: Dashboard["vehicles"]["items"] = [
  {
    feed: "rapid-kl",
    feed_display_name: "Rapid KL",
    operator_key: "rapid-kl",
    operator_name: "Rapid KL",
    region_key: "kuala-lumpur",
    region_name: "Kuala Lumpur",
    agency_names: ["Rapid Rail Sdn Bhd"],
    mode: "mrt",
    vehicle_id: "PREVIEW-1001",
    trip_id: "rapid-kl-mrt-kajang-0714",
    route_id: "MRT-KAJANG",
    route_name: "Kajang Line",
    trip_headsign: "Kajang",
    latitude: 3.139,
    longitude: 101.6869,
    bearing: 90,
    speed_metres_per_second: 11.2,
    position_reported_at: previewNow,
    fetched_at: previewNow,
    freshness: "live",
    static_version_id: "preview-static",
    next_scheduled_stop: "Pasar Seni",
  },
  {
    feed: "rapid-kl",
    feed_display_name: "Rapid KL",
    operator_key: "rapid-kl",
    operator_name: "Rapid KL",
    region_key: "kuala-lumpur",
    region_name: "Kuala Lumpur",
    agency_names: ["Rapid Bus Sdn Bhd"],
    mode: "bus",
    vehicle_id: "PREVIEW-1002",
    trip_id: "rapid-kl-bus-t851-0725",
    route_id: "T851",
    route_name: "TTDI - Bandar Utama",
    trip_headsign: "Bandar Utama",
    latitude: 3.132,
    longitude: 101.628,
    bearing: 180,
    speed_metres_per_second: 5.4,
    position_reported_at: previewStale,
    fetched_at: previewStale,
    freshness: "stale",
    static_version_id: "preview-static",
    next_scheduled_stop: "TTDI MRT",
  },
  {
    feed: "ktmb",
    feed_display_name: "KTMB",
    operator_key: "ktmb",
    operator_name: "KTMB",
    region_key: "national",
    region_name: "Malaysia",
    agency_names: ["Keretapi Tanah Melayu Berhad"],
    mode: "rail",
    vehicle_id: "PREVIEW-2001",
    trip_id: "ktmb-komuter-seremban-0732",
    route_id: "KOM-SEREMBAN",
    route_name: "Seremban Line",
    trip_headsign: "Pulau Sebang / Tampin",
    latitude: 3.053,
    longitude: 101.691,
    bearing: 135,
    speed_metres_per_second: null,
    position_reported_at: null,
    fetched_at: previewStale,
    freshness: "stale",
    static_version_id: "preview-static",
    next_scheduled_stop: "Batu Caves",
  },
]

const modes: readonly Exclude<DashboardMode, "all">[] = [
  "bus",
  "mrt",
  "lrt",
  "monorail",
  "rail",
  "unknown",
]

export function previewDashboard(query: DashboardQuery): Dashboard {
  const sources = previewSources.filter(
    (source) =>
      (query.mode === "all" || source.modes.includes(query.mode)) &&
      (!query.operator || source.operator_key === query.operator) &&
      (!query.region || source.region_key === query.region),
  )
  const sourceFeeds = new Set(sources.map((source) => source.feed))
  const vehicles = previewVehicles.filter(
    (vehicle) =>
      sourceFeeds.has(vehicle.feed) && (query.mode === "all" || vehicle.mode === query.mode),
  )
  const limit = query.limit ?? 100
  const offset = query.cursor ? Number.parseInt(atob(query.cursor), 10) : 0
  const page = Number.isFinite(offset) ? vehicles.slice(offset, offset + limit) : vehicles
  const nextOffset = offset + page.length
  const nextCursor = nextOffset < vehicles.length ? btoa(String(nextOffset)) : null
  const count = (predicate: (source: Dashboard["sources"][number]) => boolean) =>
    previewSources.filter(predicate).length
  return {
    generated_at: previewNow,
    filters: {
      mode: query.mode,
      operator: query.operator || null,
      region: query.region || null,
    },
    options: {
      modes: modes.map((mode) => ({
        key: mode,
        label: mode.toUpperCase(),
        count: count((source) => source.modes.includes(mode)),
      })),
      operators: [
        ...new Map(sources.map((source) => [source.operator_key, source.operator_name])).entries(),
      ].map(([key, label]) => ({
        key,
        label,
        count: count((source) => source.operator_key === key),
      })),
      regions: [
        ...new Map(sources.map((source) => [source.region_key, source.region_name])).entries(),
      ].map(([key, label]) => ({
        key,
        label,
        count: count((source) => source.region_key === key),
      })),
    },
    summary: {
      feed_count: sources.length,
      vehicle_count: vehicles.length,
      live_vehicle_count: vehicles.filter((vehicle) => vehicle.freshness === "live").length,
      stale_vehicle_count: vehicles.filter((vehicle) => vehicle.freshness === "stale").length,
      unknown_vehicle_count: vehicles.filter((vehicle) => vehicle.mode === "unknown").length,
      scheduled_only_feed_count: sources.filter(
        (source) => source.realtime_state === "scheduled_only",
      ).length,
      unavailable_feed_count: sources.filter((source) => source.realtime_state === "unavailable")
        .length,
      awaiting_first_fetch_feed_count: sources.filter(
        (source) => source.realtime_state === "awaiting_first_fetch",
      ).length,
    },
    sources,
    vehicles: {
      items: page,
      total_count: vehicles.length,
      returned_count: page.length,
      next_cursor: nextCursor,
      truncated: nextCursor !== null,
    },
  }
}
