import { vehicleModeLabelFor } from "@/components/vehicle-mode-icon"
import type { ValidatedVehicle } from "@/hooks/use-transit-board"

export interface VehiclePopupSummary {
  readonly feed: string
  readonly freshnessLabel: "Verified live" | "Live feed stale"
  readonly modeLabel: string
  readonly positionUpdatedAt: string
  readonly routeTrip: string
  readonly vehicleLabel: string
}

export function vehiclePopupSummaryFor(vehicle: ValidatedVehicle): VehiclePopupSummary {
  const routeLabel = vehicle.routeId || "Unclassified route"
  const tripLabel = vehicle.tripId || "Trip not reported"

  return {
    feed: vehicle.feed,
    freshnessLabel: vehicle.freshness === "live" ? "Verified live" : "Live feed stale",
    modeLabel: vehicleModeLabelFor(vehicle.mode),
    positionUpdatedAt: formatPositionTimestamp(vehicle.updatedAt),
    routeTrip: `${routeLabel} / ${tripLabel}`,
    vehicleLabel: vehicle.label,
  }
}

function formatPositionTimestamp(updatedAt: string): string {
  const parsed = new Date(updatedAt)
  if (Number.isNaN(parsed.getTime())) {
    return "Time unavailable"
  }
  return new Intl.DateTimeFormat("en-MY", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "Asia/Kuala_Lumpur",
  }).format(parsed)
}
