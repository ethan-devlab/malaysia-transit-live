export type TransitMode = "bus" | "lrt" | "monorail" | "mrt" | "rail"

export type FreshnessState = "live" | "preview" | "scheduled" | "stale" | "unavailable"

export interface VehiclePosition {
  readonly label: string
  readonly toward: string
  readonly reportedAt: string
}

export interface TransitJourney {
  readonly id: string
  readonly agency: string
  readonly feedId: string
  readonly mode: TransitMode
  readonly routeLabel: string
  readonly routeName: string
  readonly origin: string
  readonly destination: string
  readonly serviceDate: string
  readonly serviceDateIso: string
  readonly plannedStart: string
  readonly plannedEnd: string
  readonly stopCount: number
  readonly freshness: FreshnessState
  readonly sourceUpdatedAt: string
  readonly vehicle?: VehiclePosition
}

export const modeLabels: Readonly<Record<TransitMode, string>> = {
  bus: "Bus",
  lrt: "LRT",
  monorail: "Monorail",
  mrt: "MRT",
  rail: "Rail",
}

export const freshnessLabels: Readonly<Record<FreshnessState, string>> = {
  live: "Verified live",
  preview: "Preview — not upstream",
  scheduled: "Scheduled only",
  stale: "Live feed stale",
  unavailable: "Source unavailable",
}

export function journeyMatchesSearch(journey: TransitJourney, query: string): boolean {
  const normalizedQuery = query.trim().toLocaleLowerCase("en-MY")

  if (normalizedQuery.length === 0) {
    return true
  }

  const searchableText = [
    journey.routeLabel,
    journey.routeName,
    journey.origin,
    journey.destination,
    journey.agency,
  ]
    .join(" ")
    .toLocaleLowerCase("en-MY")

  return searchableText.includes(normalizedQuery)
}
