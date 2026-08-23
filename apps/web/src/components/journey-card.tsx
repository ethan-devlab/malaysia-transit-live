import {
  ArrowRight,
  Bus,
  CalendarBlank,
  Clock,
  Star,
  Subway,
  Train,
  Tram,
} from "@phosphor-icons/react"

import { DataStatusBadge } from "@/components/data-status-badge"
import { Button } from "@/components/ui/button"
import { Card, CardContent, CardFooter, CardHeader, CardTitle } from "@/components/ui/card"
import { modeLabels, type TransitJourney } from "@/domain/transit"

interface JourneyCardProps {
  readonly journey: TransitJourney
  readonly isFavourite: boolean
  readonly isSelected: boolean
  readonly onSelect: (journeyId: string) => void
  readonly onToggleFavourite: (journeyId: string) => void
}

function ModeIcon({ mode }: Pick<TransitJourney, "mode">) {
  switch (mode) {
    case "bus":
      return <Bus aria-hidden="true" size={24} weight="duotone" />
    case "mrt":
      return <Subway aria-hidden="true" size={24} weight="duotone" />
    case "lrt":
      return <Tram aria-hidden="true" size={24} weight="duotone" />
    case "monorail":
      return <Tram aria-hidden="true" size={24} weight="duotone" />
    case "rail":
      return <Train aria-hidden="true" size={24} weight="duotone" />
  }
}

export function JourneyCard({
  journey,
  isFavourite,
  isSelected,
  onSelect,
  onToggleFavourite,
}: JourneyCardProps) {
  const titleId = `${journey.id}-title`
  const vehicleStateClass =
    journey.freshness === "stale"
      ? "border-[color:var(--status-warning-border)] text-[color:var(--status-warning-foreground)]"
      : "border-[color:var(--status-live-border)] text-[color:var(--status-live-foreground)]"

  return (
    <Card
      aria-labelledby={titleId}
      className={isSelected ? "border-primary bg-primary/5" : undefined}
      role="group"
    >
      <CardHeader className="gap-3">
        <div className="flex items-start gap-3">
          <div className="mt-0.5 text-primary">
            <ModeIcon mode={journey.mode} />
          </div>
          <div className="min-w-0">
            <p className="font-mono text-xs font-semibold tracking-wide text-muted-foreground uppercase">
              {modeLabels[journey.mode]} · {journey.routeLabel}
            </p>
            <CardTitle id={titleId} className="mt-1 text-lg font-semibold">
              {journey.routeName}
            </CardTitle>
          </div>
        </div>
        <DataStatusBadge state={journey.freshness} />
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-2 text-sm">
          <div>
            <p className="font-mono text-xs tracking-wide text-muted-foreground uppercase">
              Origin
            </p>
            <p className="mt-1 font-medium">{journey.origin}</p>
          </div>
          <ArrowRight aria-hidden="true" className="text-muted-foreground" />
          <div className="text-right">
            <p className="font-mono text-xs tracking-wide text-muted-foreground uppercase">
              Destination
            </p>
            <p className="mt-1 font-medium">{journey.destination}</p>
          </div>
        </div>
        <dl className="grid grid-cols-2 gap-x-4 gap-y-3 border-y border-border py-3 text-sm">
          <div>
            <dt className="flex items-center gap-2 font-mono text-xs tracking-wide text-muted-foreground uppercase">
              <CalendarBlank aria-hidden="true" className="text-muted-foreground" />
              Service date
            </dt>
            <dd className="mt-1 pl-6">
              <time dateTime={journey.serviceDateIso}>{journey.serviceDate}</time>
            </dd>
          </div>
          <div>
            <dt className="flex items-center gap-2 font-mono text-xs tracking-wide text-muted-foreground uppercase">
              <Clock aria-hidden="true" className="text-muted-foreground" />
              Planned
            </dt>
            <dd className="mt-1 pl-6">
              <time dateTime={`${journey.serviceDateIso}T${journey.plannedStart}:00+08:00`}>
                {journey.plannedStart}
              </time>
              –
              <time dateTime={`${journey.serviceDateIso}T${journey.plannedEnd}:00+08:00`}>
                {journey.plannedEnd}
              </time>
            </dd>
          </div>
          <div>
            <dt className="font-mono text-xs tracking-wide text-muted-foreground uppercase">
              Stops
            </dt>
            <dd className="mt-1">{journey.stopCount}</dd>
          </div>
          <div>
            <dt className="font-mono text-xs tracking-wide text-muted-foreground uppercase">
              Source
            </dt>
            <dd className="mt-1 truncate" title={journey.feedId}>
              {journey.feedId}
            </dd>
          </div>
        </dl>
        <p className="text-sm text-muted-foreground">
          <span className="font-medium text-foreground">{journey.agency}.</span>{" "}
          {journey.sourceUpdatedAt}
        </p>
        {journey.vehicle ? (
          <p className={`border-l-2 pl-3 text-sm ${vehicleStateClass}`}>
            {journey.vehicle.label}: toward {journey.vehicle.toward}. {journey.vehicle.reportedAt}.
          </p>
        ) : null}
      </CardContent>
      <CardFooter className="justify-between gap-3">
        <Button
          aria-label={
            isFavourite
              ? `Remove ${journey.routeLabel} from local favourites`
              : `Save ${journey.routeLabel} as a local favourite`
          }
          className="shrink-0"
          onClick={() => onToggleFavourite(journey.id)}
          type="button"
          variant="ghost"
        >
          <Star aria-hidden="true" weight={isFavourite ? "fill" : "regular"} />
          <span className="hidden sm:inline">{isFavourite ? "Saved" : "Save"}</span>
        </Button>
        <Button onClick={() => onSelect(journey.id)} type="button" variant="outline">
          {isSelected ? "Selected" : "View route"}
          <ArrowRight aria-hidden="true" />
        </Button>
      </CardFooter>
    </Card>
  )
}
