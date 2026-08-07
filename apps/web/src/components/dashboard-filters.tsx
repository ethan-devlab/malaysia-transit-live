import type { Dashboard, DashboardMode } from "@/lib/dashboard-api"

export interface DashboardFilterState {
  readonly mode: DashboardMode
  readonly operator: string
  readonly region: string
}

interface DashboardFiltersProps {
  readonly data: Dashboard | undefined
  readonly value: DashboardFilterState
  readonly onChange: (next: DashboardFilterState) => void
}

const modeLabels: Readonly<Record<DashboardMode, string>> = {
  all: "All services",
  bus: "Bus",
  mrt: "MRT",
  lrt: "LRT",
  monorail: "Monorail",
  rail: "Rail",
  unknown: "Unclassified",
}
const dashboardModes: readonly DashboardMode[] = [
  "all",
  "bus",
  "mrt",
  "lrt",
  "monorail",
  "rail",
  "unknown",
]

function parseDashboardMode(value: string): DashboardMode {
  switch (value) {
    case "all":
    case "bus":
    case "mrt":
    case "lrt":
    case "monorail":
    case "rail":
    case "unknown":
      return value
    default:
      return "all"
  }
}

export function DashboardFilters({ data, onChange, value }: DashboardFiltersProps) {
  const operators = data?.options["operators"] ?? []
  const regions = data?.options["regions"] ?? []
  const selectedMode = value.mode === "all" ? undefined : value.mode
  const visibleOperators =
    value.mode === "all"
      ? operators
      : operators.filter((operator) =>
          data?.sources.some(
            (source) =>
              source.operator_key === operator.key &&
              source.modes.includes(value.mode === "all" ? "unknown" : value.mode),
          ),
        )
  const visibleRegions = value.operator
    ? regions.filter((region) =>
        data?.sources.some(
          (source) =>
            source.region_key === region.key &&
            source.operator_key === value.operator &&
            (selectedMode === undefined || source.modes.includes(selectedMode)),
        ),
      )
    : regions.filter((region) =>
        selectedMode === undefined
          ? true
          : data?.sources.some(
              (source) => source.region_key === region.key && source.modes.includes(selectedMode),
            ),
      )
  const update = (next: Partial<DashboardFilterState>) => onChange({ ...value, ...next })

  return (
    <fieldset className="grid gap-3 border-b border-border pb-5 sm:grid-cols-3">
      <legend className="sr-only">Dashboard filters</legend>
      <label className="grid gap-1 text-sm">
        <span className="font-mono text-xs font-semibold tracking-wide text-muted-foreground uppercase">
          Mode
        </span>
        <select
          aria-label="Filter by mode"
          className="h-11 rounded-sm border border-border bg-background px-3 text-sm"
          onChange={(event) =>
            update({ mode: parseDashboardMode(event.target.value), operator: "", region: "" })
          }
          value={value.mode}
        >
          {dashboardModes.map((mode) => (
            <option key={mode} value={mode}>
              {modeLabels[mode]}
            </option>
          ))}
        </select>
      </label>
      {data && (visibleOperators.length === 0 || visibleRegions.length === 0) ? (
        <p className="text-sm text-muted-foreground sm:col-span-3" role="status">
          No operator or city options match this mode. Clear filters to restore all services.
        </p>
      ) : null}
      <label className="grid gap-1 text-sm">
        <span className="font-mono text-xs font-semibold tracking-wide text-muted-foreground uppercase">
          Operator
        </span>
        <select
          aria-label="Filter by operator"
          className="h-11 rounded-sm border border-border bg-background px-3 text-sm"
          onChange={(event) => update({ operator: event.target.value, region: "" })}
          value={value.operator}
        >
          <option value="">All operators</option>
          {visibleOperators.map((operator) => (
            <option key={operator.key} value={operator.key}>
              {operator.label}
            </option>
          ))}
        </select>
      </label>
      <label className="grid gap-1 text-sm">
        <span className="font-mono text-xs font-semibold tracking-wide text-muted-foreground uppercase">
          City / region
        </span>
        <select
          aria-label="Filter by city or region"
          className="h-11 rounded-sm border border-border bg-background px-3 text-sm"
          onChange={(event) => update({ region: event.target.value })}
          value={value.region}
        >
          <option value="">All regions</option>
          {visibleRegions.map((region) => (
            <option key={region.key} value={region.key}>
              {region.label}
            </option>
          ))}
        </select>
      </label>
      {value.mode !== "all" || value.operator || value.region ? (
        <button
          className="min-h-11 justify-self-start text-sm font-medium text-primary underline-offset-4 hover:underline sm:col-span-3"
          onClick={() => onChange({ mode: "all", operator: "", region: "" })}
          type="button"
        >
          Clear filters
        </button>
      ) : null}
    </fieldset>
  )
}
