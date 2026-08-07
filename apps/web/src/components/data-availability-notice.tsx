import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import type { BoardDataState, RealtimeCoverage } from "@/hooks/use-transit-board"

interface DataAvailabilityNoticeProps {
  readonly realtime: RealtimeCoverage
  readonly state: BoardDataState
}

const baseNoticeContent: Readonly<
  Record<
    Exclude<BoardDataState, "ready">,
    { readonly description: string; readonly title: string; readonly tone: string }
  >
> = {
  loading: {
    description: "The service is checking the active static dataset.",
    title: "Loading service data",
    tone: "border-border bg-muted text-foreground",
  },
  preview: {
    description:
      "The importer and realtime polling services are not connected in this local build. No card is an upstream ETA or vehicle reading.",
    title: "Integration preview",
    tone: "border-[color:var(--status-preview-border)] bg-[color:var(--status-preview-surface)] text-[color:var(--status-preview-foreground)]",
  },
  unavailable: {
    description:
      "No valid static snapshot is active. The previous good dataset is retained until a valid replacement is available.",
    title: "Service data unavailable",
    tone: "border-[color:var(--status-error-border)] bg-[color:var(--status-error-surface)] text-[color:var(--status-error-foreground)]",
  },
}

export function DataAvailabilityNotice({ realtime, state }: DataAvailabilityNoticeProps) {
  const content = state === "ready" ? readyNoticeContent(realtime) : baseNoticeContent[state]
  return (
    <Alert className={content.tone}>
      <AlertTitle className="font-semibold">{content.title}</AlertTitle>
      <AlertDescription>{content.description}</AlertDescription>
    </Alert>
  )
}

function readyNoticeContent(realtime: RealtimeCoverage) {
  if (realtime.validatedVehicleCount > 0) {
    return {
      description: `${realtime.validatedVehicleCount} reference-validated vehicle locations are currently shown. Journey times remain planned GTFS times, not ETAs.`,
      title: "Validated vehicle locations available",
      tone: "border-[color:var(--status-live-border)] bg-[color:var(--status-live-surface)] text-[color:var(--status-live-foreground)]",
    }
  }
  if (realtime.awaitingFirstFetchCount > 0) {
    return {
      description: `${realtime.awaitingFirstFetchCount} official realtime feed${realtime.awaitingFirstFetchCount === 1 ? " is" : "s are"} awaiting the first shared-rate-limit poll. Schedules remain available in the meantime.`,
      title: "Scheduled data ready; realtime is warming up",
      tone: "border-[color:var(--status-warning-border)] bg-[color:var(--status-warning-surface)] text-[color:var(--status-warning-foreground)]",
    }
  }
  return {
    description: `${realtime.scheduledOnlyFeedCount} active feed${realtime.scheduledOnlyFeedCount === 1 ? " is" : "s are"} scheduled-only because the official source publishes no realtime vehicle positions. Journey times are from the active GTFS static dataset.`,
    title: "Scheduled data ready",
    tone: "border-[color:var(--status-scheduled-border)] bg-[color:var(--status-scheduled-surface)] text-[color:var(--status-scheduled-foreground)]",
  }
}
