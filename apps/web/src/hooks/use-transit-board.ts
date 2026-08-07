import { useQuery } from "@tanstack/react-query"
import { useMemo } from "react"

import { previewJourneys } from "@/data/previewTransit"
import type { TransitJourney, TransitMode } from "@/domain/transit"
import { useLiveVehicles } from "@/hooks/use-live-vehicles"
import {
  type DataStatus,
  fetchDataStatus,
  fetchScheduledJourneys,
  type ScheduledJourney,
  type VehicleLocation,
} from "@/lib/transit-api"

export type BoardDataState = "loading" | "preview" | "ready" | "unavailable"

export interface TransitBoardData {
  readonly journeys: readonly TransitJourney[]
  readonly realtime: RealtimeCoverage
  readonly vehicles: readonly ValidatedVehicle[]
  readonly serviceDate: string
  readonly state: BoardDataState
}

export interface RealtimeCoverage {
  readonly availableFeedCount: number
  readonly awaitingFirstFetchCount: number
  readonly scheduledOnlyFeedCount: number
  readonly validatedVehicleCount: number
}

export interface ValidatedVehicle {
  readonly feed: string
  readonly freshness: "live" | "stale"
  readonly id: string
  readonly label: string
  readonly latitude: number
  readonly longitude: number
  readonly routeId: string
  readonly tripId: string
  readonly updatedAt: string
}

const displayDateFormatter = new Intl.DateTimeFormat("en-MY", {
  day: "2-digit",
  month: "short",
  timeZone: "Asia/Kuala_Lumpur",
  year: "numeric",
})

export function useTransitBoard(): TransitBoardData {
  const apiEnabled = import.meta.env.PROD
  const statusQuery = useQuery({
    enabled: apiEnabled,
    queryFn: ({ signal }) => fetchDataStatus(signal),
    queryKey: ["transit-data-status"],
    refetchInterval: 60_000,
  })
  const hasActiveStaticVersion = statusQuery.data?.some(
    (status) => status.static_state === "active",
  )
  const journeyQuery = useQuery({
    enabled: hasActiveStaticVersion === true,
    queryFn: ({ signal }) => fetchScheduledJourneys(signal),
    queryKey: ["scheduled-journeys"],
    refetchInterval: 60_000,
  })
  const vehicles = useLiveVehicles(apiEnabled && hasActiveStaticVersion === true)
  const validatedVehicles = useMemo(() => vehicles.map(toValidatedVehicle), [vehicles])
  const vehicleByTrip = useMemo(
    () =>
      new Map(
        validatedVehicles
          .filter((vehicle) => vehicle.tripId.length > 0)
          .map((vehicle) => [`${vehicle.feed}:${vehicle.tripId}`, vehicle]),
      ),
    [validatedVehicles],
  )
  const apiJourneys = useMemo(
    () => (journeyQuery.data ?? []).map((journey) => toTransitJourney(journey, vehicleByTrip)),
    [journeyQuery.data, vehicleByTrip],
  )
  const realtime = useMemo(
    () => realtimeCoverage(validatedVehicles, statusQuery.data ?? []),
    [statusQuery.data, validatedVehicles],
  )

  if (hasActiveStaticVersion && journeyQuery.isPending) {
    return {
      journeys: [],
      realtime,
      vehicles: [],
      serviceDate: todayDisplayDate(),
      state: "loading",
    }
  }
  if (hasActiveStaticVersion && !journeyQuery.isError) {
    return {
      journeys: apiJourneys,
      realtime,
      vehicles: validatedVehicles,
      serviceDate: apiJourneys.at(0)?.serviceDate ?? todayDisplayDate(),
      state: "ready",
    }
  }
  if (!apiEnabled && hasActiveStaticVersion !== true) {
    return {
      journeys: previewJourneys,
      realtime,
      vehicles: [],
      serviceDate: previewJourneys.at(0)?.serviceDate ?? todayDisplayDate(),
      state: "preview",
    }
  }
  return {
    journeys: [],
    realtime,
    vehicles: [],
    serviceDate: todayDisplayDate(),
    state: statusQuery.isPending ? "loading" : "unavailable",
  }
}

export function toValidatedVehicle(vehicle: VehicleLocation): ValidatedVehicle {
  return {
    feed: vehicle.feed,
    freshness: vehicle.freshness,
    id: `${vehicle.feed}:${vehicle.vehicle_id}`,
    label: `Vehicle ${vehicle.vehicle_id}`,
    latitude: vehicle.latitude,
    longitude: vehicle.longitude,
    routeId: vehicle.route_id,
    tripId: vehicle.trip_id,
    updatedAt: vehicle.fetched_at,
  }
}

function realtimeCoverage(
  vehicles: readonly ValidatedVehicle[],
  statuses: readonly DataStatus[],
): RealtimeCoverage {
  return {
    availableFeedCount: statuses.filter((status) => status.realtime_state === "available").length,
    awaitingFirstFetchCount: statuses.filter(
      (status) => status.realtime_state === "awaiting_first_fetch",
    ).length,
    scheduledOnlyFeedCount: statuses.filter((status) => status.realtime_state === "scheduled_only")
      .length,
    validatedVehicleCount: vehicles.length,
  }
}

export function toTransitJourney(
  journey: ScheduledJourney,
  vehicleByTrip: ReadonlyMap<string, ValidatedVehicle>,
): TransitJourney {
  const vehicle = vehicleByTrip.get(`${journey.feed}:${journey.trip_id}`)
  return {
    agency: journey.source.feed,
    destination: journey.destination,
    feedId: journey.feed,
    freshness: vehicle?.freshness ?? "scheduled",
    id: `${journey.feed}:${journey.trip_id}`,
    mode: apiModeToTransitMode(journey.mode, journey.route_name),
    origin: journey.origin,
    plannedEnd: journey.planned_end,
    plannedStart: journey.planned_start,
    routeLabel: journey.route_label,
    routeName: journey.route_name,
    serviceDate: displayServiceDate(journey.service_date),
    serviceDateIso: journey.service_date,
    sourceUpdatedAt: journey.source.last_successful_fetch_at
      ? `Static GTFS fetched ${new Date(journey.source.last_successful_fetch_at).toLocaleString("en-MY")}`
      : "Static GTFS schedule",
    stopCount: journey.stop_count,
    ...(vehicle
      ? {
          vehicle: {
            label: vehicle.label,
            reportedAt: `Position ${formatFreshnessAge(vehicle.updatedAt)} ago`,
            toward: journey.destination,
          },
        }
      : {}),
  }
}

function formatFreshnessAge(updatedAt: string): string {
  const ageSeconds = Math.max(0, Math.floor((Date.now() - new Date(updatedAt).getTime()) / 1_000))
  if (ageSeconds < 60) {
    return `${ageSeconds}s`
  }
  if (ageSeconds < 3_600) {
    return `${Math.floor(ageSeconds / 60)}m`
  }
  return `${Math.floor(ageSeconds / 3_600)}h`
}

function apiModeToTransitMode(mode: string, routeName: string): TransitMode {
  switch (mode) {
    case "bus":
      return "bus"
    case "monorail":
      return "monorail"
    case "rail":
      return "rail"
    case "metro":
      if (/\bMONORAIL\b/i.test(routeName)) {
        return "monorail"
      }
      return /\b(?:LRT|BRT)\b/i.test(routeName) ? "lrt" : "mrt"
    case "tram":
      return "lrt"
    default:
      return "rail"
  }
}

function displayServiceDate(serviceDate: string): string {
  return displayDateFormatter.format(new Date(`${serviceDate}T12:00:00+08:00`))
}

function todayDisplayDate(): string {
  return displayDateFormatter.format(new Date())
}
