import maplibregl from "maplibre-gl"
import { createRoot } from "react-dom/client"

import { vehicleIconForMode } from "@/components/vehicle-mode-icon"
import { vehiclePopupSummaryFor } from "@/components/vehicle-popup-summary"
import type { ValidatedVehicle } from "@/hooks/use-transit-board"

export interface VehicleMapPopup {
  readonly remove: () => void
}

export function addVehicleMapPopup(
  map: maplibregl.Map,
  vehicle: ValidatedVehicle,
  onClose: () => void,
): VehicleMapPopup {
  const content = document.createElement("div")
  const root = createRoot(content)
  let removed = false

  const close = () => {
    if (removed) {
      return
    }
    removed = true
    root.unmount()
    onClose()
  }
  const vehiclePosition = map.project([vehicle.longitude, vehicle.latitude])
  const popup = new maplibregl.Popup({
    anchor: vehiclePopupAnchorFor(vehiclePosition.y, map.getContainer().clientHeight),
    className: "civic-vehicle-popup",
    closeButton: true,
    closeOnClick: false,
    closeOnMove: false,
    focusAfterOpen: false,
    maxWidth: "20rem",
    offset: 18,
  })

  popup.on("close", close)
  root.render(<VehicleMapPopupContents vehicle={vehicle} />)
  popup.setLngLat([vehicle.longitude, vehicle.latitude]).setDOMContent(content).addTo(map)

  return {
    remove: () => {
      if (removed) {
        return
      }
      popup.remove()
      close()
    },
  }
}

export function vehiclePopupAnchorFor(vehicleY: number, mapHeight: number): "top" | "bottom" {
  return vehicleY < mapHeight / 2 ? "top" : "bottom"
}

function VehicleMapPopupContents({ vehicle }: { readonly vehicle: ValidatedVehicle }) {
  const Icon = vehicleIconForMode(vehicle.mode)
  const summary = vehiclePopupSummaryFor(vehicle)
  const freshnessClassName =
    vehicle.freshness === "live"
      ? "text-[color:var(--status-live-foreground)]"
      : "text-[color:var(--status-warning-foreground)]"

  return (
    <section
      aria-label={`Vehicle summary for ${summary.vehicleLabel}`}
      className="min-w-0 p-3 pr-11"
    >
      <p className="flex items-center gap-2 text-xs font-semibold tracking-wide text-muted-foreground uppercase">
        <Icon aria-hidden="true" size={16} weight="fill" />
        {summary.modeLabel}
      </p>
      <h3 className="mt-1 break-words text-base font-semibold [overflow-wrap:anywhere]">
        {summary.vehicleLabel}
      </h3>
      <p className="mt-1 break-words font-mono text-xs text-muted-foreground [overflow-wrap:anywhere]">
        {summary.feed}
      </p>
      <p className={`mt-3 text-sm font-medium ${freshnessClassName}`}>{summary.freshnessLabel}</p>
      <dl className="mt-3 space-y-2 text-sm">
        <div>
          <dt className="text-xs text-muted-foreground">Route / trip</dt>
          <dd className="mt-0.5 break-words font-mono [overflow-wrap:anywhere]">
            {summary.routeTrip}
          </dd>
        </div>
        <div>
          <dt className="text-xs text-muted-foreground">Position update</dt>
          <dd className="mt-0.5 font-mono text-xs">{summary.positionUpdatedAt}</dd>
        </div>
      </dl>
    </section>
  )
}
