import { Bus, Clock, MapPin, Signpost } from "@phosphor-icons/react"
import { Children, type ReactNode } from "react"

import { Button } from "@/components/ui/button"
import type { NetworkSearch, ScheduledJourney, VehicleLocation } from "@/lib/transit-api"

interface NetworkSearchResultsProps {
  readonly data: NetworkSearch | undefined
  readonly hasError: boolean
  readonly isLoading: boolean
  readonly onSelectJourney: (journey: ScheduledJourney) => void
  readonly onSelectVehicle: (vehicle: VehicleLocation) => void
  readonly query: string
}

export function NetworkSearchResults({
  data,
  hasError,
  isLoading,
  onSelectJourney,
  onSelectVehicle,
  query,
}: NetworkSearchResultsProps) {
  if (query.trim().length < 2) {
    return null
  }

  if (isLoading) {
    return (
      <section aria-live="polite" className="mt-4 border-l-2 border-primary pl-4">
        <p className="font-mono text-xs font-semibold tracking-wide text-muted-foreground uppercase">
          Network search
        </p>
        <p className="mt-1 text-sm text-muted-foreground">Searching scheduled and live data…</p>
      </section>
    )
  }

  if (hasError) {
    return (
      <section
        aria-live="polite"
        className="mt-4 border-l-2 border-[color:var(--status-error-border)] pl-4"
      >
        <p className="font-medium text-[color:var(--status-error-foreground)]">
          Network search is temporarily unavailable.
        </p>
        <p className="mt-1 text-sm text-muted-foreground">
          The service board remains available while this search is retried.
        </p>
      </section>
    )
  }

  if (!data) {
    return null
  }

  const resultCount =
    data.journeys.length + data.routes.length + data.stops.length + data.vehicles.length
  return (
    <section
      aria-labelledby="network-search-results-heading"
      className="mt-5 border-y border-border py-5"
    >
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <div>
          <p className="font-mono text-xs font-semibold tracking-wide text-primary uppercase">
            Network search
          </p>
          <h3 id="network-search-results-heading" className="mt-1 text-lg font-semibold">
            {resultCount} matching record{resultCount === 1 ? "" : "s"}
          </h3>
        </div>
        <p className="font-mono text-xs text-muted-foreground">“{data.query}”</p>
      </div>

      {resultCount === 0 ? (
        <p className="mt-4 text-sm text-muted-foreground">
          No active scheduled service, stop, route, or retained vehicle position matches this term.
        </p>
      ) : (
        <div className="mt-4 grid gap-5 lg:grid-cols-2">
          <SearchGroup title="Scheduled trips" icon={<Clock aria-hidden="true" />}>
            {data.journeys.map((journey) => (
              <Button
                className="h-auto min-h-11 w-full justify-start px-3 py-3 text-left whitespace-normal"
                key={`${journey.feed}:${journey.trip_id}`}
                onClick={() => onSelectJourney(journey)}
                type="button"
                variant="outline"
              >
                <span className="grid min-w-0 gap-1">
                  <span className="break-words font-medium">
                    {journey.route_label} · {journey.origin} to {journey.destination}
                  </span>
                  <span className="font-mono text-xs text-muted-foreground">
                    {journey.planned_start}–{journey.planned_end} · {journey.feed}
                  </span>
                </span>
              </Button>
            ))}
          </SearchGroup>

          <SearchGroup title="Validated live vehicles" icon={<Bus aria-hidden="true" />}>
            {data.vehicles.map((vehicle) => (
              <Button
                className="h-auto min-h-11 w-full justify-start px-3 py-3 text-left whitespace-normal"
                key={`${vehicle.feed}:${vehicle.vehicle_id}`}
                onClick={() => onSelectVehicle(vehicle)}
                type="button"
                variant="outline"
              >
                <span className="grid min-w-0 gap-1">
                  <span className="font-medium">
                    Vehicle {vehicle.vehicle_id}
                    {vehicle.route_id ? ` · route ${vehicle.route_id}` : ""}
                  </span>
                  <span className="font-mono text-xs text-muted-foreground">
                    {vehicle.feed} ·{" "}
                    {vehicle.freshness === "live" ? "Verified live" : "Live feed stale"} ·{" "}
                    {formatAge(vehicle.fetched_at)} ago
                  </span>
                </span>
              </Button>
            ))}
          </SearchGroup>

          <SearchGroup title="Routes" icon={<Signpost aria-hidden="true" />}>
            {data.routes.map((route) => (
              <article
                className="border-l border-border pl-3"
                key={`${route.source.feed}:${route.route_id}`}
              >
                <p className="font-medium">
                  {route.label} · {route.name}
                </p>
                <p className="mt-1 font-mono text-xs text-muted-foreground">
                  {route.mode} · {route.source.feed}
                </p>
              </article>
            ))}
          </SearchGroup>

          <SearchGroup title="Stops and stations" icon={<MapPin aria-hidden="true" />}>
            {data.stops.map((stop) => (
              <article
                className="border-l border-border pl-3"
                key={`${stop.source.feed}:${stop.stop_id}`}
              >
                <p className="font-medium">{stop.name}</p>
                <p className="mt-1 font-mono text-xs text-muted-foreground">
                  {stop.stop_id} · {stop.source.feed}
                </p>
              </article>
            ))}
          </SearchGroup>
        </div>
      )}
    </section>
  )
}

function SearchGroup({
  children,
  icon,
  title,
}: {
  readonly children: ReactNode
  readonly icon: ReactNode
  readonly title: string
}) {
  if (Children.count(children) === 0) {
    return null
  }

  return (
    <section className="min-w-0">
      <h4 className="flex items-center gap-2 font-mono text-xs font-semibold tracking-wide text-muted-foreground uppercase">
        {icon}
        {title}
      </h4>
      <div className="mt-3 grid max-h-80 gap-2 overflow-y-auto pr-1">{children}</div>
    </section>
  )
}

function formatAge(timestamp: string): string {
  const ageSeconds = Math.max(0, Math.floor((Date.now() - new Date(timestamp).getTime()) / 1_000))
  if (ageSeconds < 60) {
    return `${ageSeconds}s`
  }
  if (ageSeconds < 3_600) {
    return `${Math.floor(ageSeconds / 60)}m`
  }
  return `${Math.floor(ageSeconds / 3_600)}h`
}
