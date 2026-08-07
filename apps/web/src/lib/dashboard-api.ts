import { z } from "zod"

const dashboardOptionSchema = z.object({
  key: z.string(),
  label: z.string(),
  count: z.number().int(),
})
const dashboardVehicleSchema = z.object({
  feed: z.string(),
  feed_display_name: z.string(),
  operator_key: z.string(),
  operator_name: z.string(),
  region_key: z.string(),
  region_name: z.string(),
  agency_names: z.array(z.string()),
  mode: z.enum(["bus", "mrt", "lrt", "monorail", "rail", "unknown"]),
  vehicle_id: z.string(),
  trip_id: z.string(),
  route_id: z.string(),
  route_name: z.string(),
  trip_headsign: z.string(),
  latitude: z.number(),
  longitude: z.number(),
  bearing: z.number().nullable(),
  speed_metres_per_second: z.number().nullable(),
  position_reported_at: z.string().datetime().nullable(),
  fetched_at: z.string().datetime(),
  freshness: z.enum(["live", "stale"]),
  static_version_id: z.string().nullable(),
  next_scheduled_stop: z.string().nullable(),
})
const dashboardSourceSchema = z.object({
  feed: z.string(),
  display_name: z.string(),
  operator_key: z.string(),
  operator_name: z.string(),
  region_key: z.string(),
  region_name: z.string(),
  agency_names: z.array(z.string()),
  modes: z.array(z.enum(["bus", "mrt", "lrt", "monorail", "rail", "unknown"])),
  static_state: z.enum(["active", "unavailable"]),
  realtime_state: z.enum(["available", "awaiting_first_fetch", "scheduled_only", "unavailable"]),
  last_successful_static_fetch_at: z.string().datetime().nullable(),
  last_successful_realtime_fetch_at: z.string().datetime().nullable(),
  vehicle_count: z.number().int().nonnegative(),
  live_vehicle_count: z.number().int().nonnegative(),
  stale_vehicle_count: z.number().int().nonnegative(),
  unknown_vehicle_count: z.number().int().nonnegative(),
  geometry_coverage: z.object({
    trip_count: z.number().int().nonnegative(),
    official_shape_count: z.number().int().nonnegative(),
    matched_infrastructure_count: z.number().int().nonnegative(),
    stop_sequence_count: z.number().int().nonnegative(),
    unavailable_count: z.number().int().nonnegative(),
  }),
})
const dashboardSchema = z.object({
  generated_at: z.string().datetime(),
  filters: z.object({
    mode: z.string(),
    operator: z.string().nullable(),
    region: z.string().nullable(),
  }),
  options: z.record(z.string(), z.array(dashboardOptionSchema)),
  summary: z.object({
    feed_count: z.number().int().nonnegative(),
    vehicle_count: z.number().int().nonnegative(),
    live_vehicle_count: z.number().int().nonnegative(),
    stale_vehicle_count: z.number().int().nonnegative(),
    unknown_vehicle_count: z.number().int().nonnegative(),
    scheduled_only_feed_count: z.number().int().nonnegative(),
    unavailable_feed_count: z.number().int().nonnegative(),
    awaiting_first_fetch_feed_count: z.number().int().nonnegative(),
  }),
  sources: z.array(dashboardSourceSchema),
  vehicles: z.object({
    items: z.array(dashboardVehicleSchema),
    total_count: z.number().int().nonnegative(),
    returned_count: z.number().int().nonnegative(),
    next_cursor: z.string().nullable(),
    truncated: z.boolean(),
  }),
})

export type Dashboard = z.infer<typeof dashboardSchema>
export type DashboardVehicle = z.infer<typeof dashboardVehicleSchema>
export type DashboardSource = z.infer<typeof dashboardSourceSchema>
export type DashboardMode = "all" | "bus" | "mrt" | "lrt" | "monorail" | "rail" | "unknown"

export interface DashboardQuery {
  readonly mode: DashboardMode
  readonly operator: string
  readonly region: string
  readonly cursor?: string
  readonly limit?: number
}

export class DashboardApiError extends Error {
  readonly status: number

  constructor(status: number) {
    super("Dashboard data is temporarily unavailable.")
    this.name = "DashboardApiError"
    this.status = status
  }
}

export async function fetchDashboard(
  query: DashboardQuery,
  signal?: AbortSignal,
): Promise<Dashboard> {
  const params = new URLSearchParams()
  if (query.mode !== "all") params.set("mode", query.mode)
  if (query.operator) params.set("operator", query.operator)
  if (query.region) params.set("region", query.region)
  if (query.cursor) params.set("cursor", query.cursor)
  params.set("limit", String(query.limit ?? 100))
  const response = await fetch(`/api/v1/dashboard?${params.toString()}`, {
    headers: { Accept: "application/json" },
    ...(signal ? { signal } : {}),
  })
  if (!response.ok) throw new DashboardApiError(response.status)
  const payload: unknown = await response.json()
  return dashboardSchema.parse(payload)
}

export function parseDashboardSnapshot(payload: string): Dashboard {
  return dashboardSchema.parse(JSON.parse(payload))
}
