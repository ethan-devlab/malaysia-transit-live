import { Broadcast, Clock, Warning, XCircle } from "@phosphor-icons/react"

import { Badge } from "@/components/ui/badge"
import { type FreshnessState, freshnessLabels } from "@/domain/transit"

interface DataStatusBadgeProps {
  readonly state: FreshnessState
}

const stateClasses: Readonly<Record<FreshnessState, string>> = {
  live: "border-[color:var(--status-live-border)] bg-[color:var(--status-live-surface)] text-[color:var(--status-live-foreground)]",
  preview:
    "border-[color:var(--status-preview-border)] bg-[color:var(--status-preview-surface)] text-[color:var(--status-preview-foreground)]",
  scheduled:
    "border-[color:var(--status-scheduled-border)] bg-[color:var(--status-scheduled-surface)] text-[color:var(--status-scheduled-foreground)]",
  stale:
    "border-[color:var(--status-warning-border)] bg-[color:var(--status-warning-surface)] text-[color:var(--status-warning-foreground)]",
  unavailable:
    "border-[color:var(--status-error-border)] bg-[color:var(--status-error-surface)] text-[color:var(--status-error-foreground)]",
}

function StatusIcon({ state }: DataStatusBadgeProps) {
  switch (state) {
    case "live":
      return <Broadcast aria-hidden="true" weight="bold" />
    case "preview":
      return <Clock aria-hidden="true" weight="bold" />
    case "scheduled":
      return <Clock aria-hidden="true" weight="bold" />
    case "stale":
      return <Warning aria-hidden="true" weight="bold" />
    case "unavailable":
      return <XCircle aria-hidden="true" weight="bold" />
  }
}

export function DataStatusBadge({ state }: DataStatusBadgeProps) {
  return (
    <Badge className={stateClasses[state]} variant="outline">
      <StatusIcon state={state} />
      {freshnessLabels[state]}
    </Badge>
  )
}
