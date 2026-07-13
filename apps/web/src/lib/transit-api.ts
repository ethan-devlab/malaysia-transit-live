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
  active_version_id: z.string().nullable(),
  last_successful_static_fetch_at: z.string().datetime().nullable(),
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

const dataStatusesSchema = z.array(dataStatusSchema)
const scheduledJourneysSchema = z.array(scheduledJourneySchema)
const vehicleLocationsSchema = z.array(vehicleLocationSchema)
const vehicleSnapshotSchema = z.object({
  generated_at: z.string().datetime(),
  vehicles: vehicleLocationsSchema,
})

export type DataStatus = z.infer<typeof dataStatusSchema>
export type ScheduledJourney = z.infer<typeof scheduledJourneySchema>
export type VehicleLocation = z.infer<typeof vehicleLocationSchema>

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

export function parseVehicleSnapshot(payload: string): readonly VehicleLocation[] {
  return vehicleSnapshotSchema.parse(JSON.parse(payload)).vehicles
}

function requestOptions(signal: AbortSignal | undefined): RequestInit {
  const headers = { Accept: "application/json" }
  return signal ? { headers, signal } : { headers }
}
