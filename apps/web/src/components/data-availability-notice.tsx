import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import type { BoardDataState } from "@/hooks/use-transit-board"

interface DataAvailabilityNoticeProps {
  readonly state: BoardDataState
}

const noticeContent: Readonly<
  Record<
    BoardDataState,
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
  ready: {
    description:
      "Journey times are from the active GTFS static dataset. Vehicle positions appear only after independent realtime validation.",
    title: "Scheduled data ready",
    tone: "border-[color:var(--status-scheduled-border)] bg-[color:var(--status-scheduled-surface)] text-[color:var(--status-scheduled-foreground)]",
  },
  unavailable: {
    description:
      "No valid static snapshot is active. The previous good dataset is retained until a valid replacement is available.",
    title: "Service data unavailable",
    tone: "border-[color:var(--status-error-border)] bg-[color:var(--status-error-surface)] text-[color:var(--status-error-foreground)]",
  },
}

export function DataAvailabilityNotice({ state }: DataAvailabilityNoticeProps) {
  const content = noticeContent[state]
  return (
    <Alert className={content.tone}>
      <AlertTitle className="font-semibold">{content.title}</AlertTitle>
      <AlertDescription>{content.description}</AlertDescription>
    </Alert>
  )
}
