import { z } from "zod"

const sourceSchema = z.object({
  feed: z.string(),
  freshness: z.enum(["scheduled_only", "unavailable"]),
  last_successful_fetch_at: z.string().datetime().nullable(),
  static_version_id: z.string(),
})

const dataStatusSchema = z.object({
  feed: z.string(),
  static_state: z.enum(["active", "unavailable"]),
  realtime_state: z.enum(["available", "awaiting_first_fetch", "scheduled_only", "unavailable"]),
  active_version_id: z.string().nullable(),
  last_successful_static_fetch_at: z.string().datetime().nullable(),
  last_successful_realtime_fetch_at: z.string().datetime().nullable(),
})

const scheduledJourneySchema = z.object({
  feed: z.string(),
  trip_id: z.string(),
  route_id: z.string(),
  mode: z.string(),
  route_label: z.string(),
  route_name: z.string(),
  origin: z.string(),
  destination: z.string(),
  service_date: z.string().date(),
  planned_start: z.string(),
  planned_end: z.string(),
  stop_count: z.number().int().nonnegative(),
  source: sourceSchema,
})

const vehicleLocationSchema = z.object({
  feed: z.string(),
  vehicle_id: z.string(),
  trip_id: z.string(),
  route_id: z.string(),
  latitude: z.number(),
  longitude: z.number(),
  bearing: z.number().nullable(),
  speed_metres_per_second: z.number().nullable(),
  position_reported_at: z.string().datetime().nullable(),
  fetched_at: z.string().datetime(),
  freshness: z.enum(["live", "stale"]),
  static_version_id: z.string().nullable(),
})

const routeSearchItemSchema = z.object({
  kind: z.literal("route"),
  route_id: z.string(),
  label: z.string(),
  name: z.string(),
  mode: z.string(),
  source: sourceSchema,
})

const stopSearchItemSchema = z.object({
  kind: z.literal("stop"),
  stop_id: z.string(),
  name: z.string(),
  latitude: z.number(),
  longitude: z.number(),
  source: sourceSchema,
})

const tripStopSchema = z.object({
  sequence: z.number().int().nonnegative(),
  stop_id: z.string(),
  name: z.string(),
  latitude: z.number().nullable(),
  longitude: z.number().nullable(),
  arrival_time: z.string(),
  departure_time: z.string(),
})

const coordinateSchema = z.tuple([z.number().min(-180).max(180), z.number().min(-90).max(90)])
const lineCoordinatesSchema = z
  .array(coordinateSchema)
  .min(2)
  .refine(
    (coordinates) =>
      new Set(coordinates.map(([longitude, latitude]) => `${longitude}:${latitude}`)).size > 1,
    "Route geometry requires at least two distinct coordinates.",
  )
const routeColourSchema = z.string().regex(/^(?:[0-9A-F]{6})?$/)
const tripGeometrySchema = z.discriminatedUnion("quality", [
  z.object({
    type: z.literal("LineString"),
    coordinates: lineCoordinatesSchema,
    quality: z.literal("official_shape"),
    shape_id: z.string().min(1),
    source: z.literal("gtfs"),
    source_version: z.string().min(1),
    attribution: z.null(),
  }),
  z.object({
    type: z.literal("LineString"),
    coordinates: lineCoordinatesSchema,
    quality: z.literal("matched_infrastructure"),
    shape_id: z.null(),
    source: z.literal("derived_infrastructure"),
    source_version: z.string().min(1),
    attribution: z.string().min(1),
    attribution_url: z.string().url().optional(),
    derivation_version: z.string().min(1).optional(),
    derived_at: z.string().datetime().optional(),
    infrastructure_content_sha256: z
      .string()
      .regex(/^[a-f0-9]{64}$/)
      .optional(),
    infrastructure_snapshot: z.string().min(1).optional(),
  }),
  z.object({
    type: z.literal("LineString"),
    coordinates: lineCoordinatesSchema,
    quality: z.literal("stop_sequence"),
    shape_id: z.null(),
    source: z.literal("scheduled_stops"),
    source_version: z.string().min(1),
    attribution: z.null(),
  }),
  z.object({
    type: z.literal("LineString"),
    coordinates: z.null(),
    quality: z.literal("unavailable"),
    shape_id: z.null(),
    source: z.literal("none"),
    source_version: z.string().min(1),
    attribution: z.null(),
  }),
])

const tripDetailSchema = z.object({
  trip_id: z.string(),
  route_id: z.string(),
  headsign: z.string(),
  service_date: z.string().date(),
  is_scheduled: z.boolean(),
  route_color: routeColourSchema,
  route_text_color: routeColourSchema,
  geometry: tripGeometrySchema,
  stops: z.array(tripStopSchema),
  source: sourceSchema,
})

const dataStatusesSchema = z.array(dataStatusSchema)
const scheduledJourneysSchema = z.array(scheduledJourneySchema)
const vehicleLocationsSchema = z.array(vehicleLocationSchema)
const vehicleSnapshotSchema = z.object({
  generated_at: z.string().datetime(),
  vehicles: vehicleLocationsSchema,
})
const networkSearchSchema = z.object({
  query: z.string(),
  journeys: scheduledJourneysSchema,
  routes: z.array(routeSearchItemSchema),
  stops: z.array(stopSearchItemSchema),
  vehicles: vehicleLocationsSchema,
})

export type DataStatus = z.infer<typeof dataStatusSchema>
export type ScheduledJourney = z.infer<typeof scheduledJourneySchema>
export type VehicleLocation = z.infer<typeof vehicleLocationSchema>
export type TripDetail = z.infer<typeof tripDetailSchema>
export type NetworkSearch = z.infer<typeof networkSearchSchema>

class TransitApiError extends Error {
  readonly status: number

  constructor(status: number) {
    super("Transit data is temporarily unavailable.")
    this.name = "TransitApiError"
    this.status = status
  }
}

export async function fetchDataStatus(signal?: AbortSignal): Promise<readonly DataStatus[]> {
  const response = await fetch("/api/v1/data-status", requestOptions(signal))
  if (!response.ok) {
    throw new TransitApiError(response.status)
  }
  const payload: unknown = await response.json()
  return dataStatusesSchema.parse(payload)
}

export async function fetchScheduledJourneys(
  signal?: AbortSignal,
): Promise<readonly ScheduledJourney[]> {
  const response = await fetch("/api/v1/journeys?limit=20", requestOptions(signal))
  if (!response.ok) {
    throw new TransitApiError(response.status)
  }
  const payload: unknown = await response.json()
  return scheduledJourneysSchema.parse(payload)
}

export async function fetchVehicleLocations(
  signal?: AbortSignal,
): Promise<readonly VehicleLocation[]> {
  const response = await fetch("/api/v1/vehicles?limit=100", requestOptions(signal))
  if (!response.ok) {
    throw new TransitApiError(response.status)
  }
  const payload: unknown = await response.json()
  return vehicleLocationsSchema.parse(payload)
}

export async function fetchNetworkSearch(
  query: string,
  signal?: AbortSignal,
): Promise<NetworkSearch> {
  const response = await fetch(
    `/api/v1/search?q=${encodeURIComponent(query)}&limit=20`,
    requestOptions(signal),
  )
  if (!response.ok) {
    throw new TransitApiError(response.status)
  }
  const payload: unknown = await response.json()
  return networkSearchSchema.parse(payload)
}

export async function fetchTripDetail(
  feed: string,
  tripId: string,
  serviceDate: string,
  signal?: AbortSignal,
): Promise<TripDetail> {
  const response = await fetch(
    `/api/v1/trips/${encodeURIComponent(feed)}/${encodeURIComponent(tripId)}?service_date=${encodeURIComponent(serviceDate)}`,
    requestOptions(signal),
  )
  if (!response.ok) {
    throw new TransitApiError(response.status)
  }
  const payload: unknown = await response.json()
  return parseTripDetail(payload)
}

export function parseTripDetail(payload: unknown): TripDetail {
  return tripDetailSchema.parse(payload)
}

export function parseVehicleSnapshot(payload: string): readonly VehicleLocation[] {
  return vehicleSnapshotSchema.parse(JSON.parse(payload)).vehicles
}

function requestOptions(signal: AbortSignal | undefined): RequestInit {
  const headers = { Accept: "application/json" }
  return signal ? { headers, signal } : { headers }
}
