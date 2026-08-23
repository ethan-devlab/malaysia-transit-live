import { NavigationArrowIcon } from "@phosphor-icons/react"
import maplibregl from "maplibre-gl"
import { createRoot } from "react-dom/client"

import { vehicleIconForMode } from "@/components/vehicle-mode-icon"
import type { ValidatedVehicle } from "@/hooks/use-transit-board"
import { vehicleBearingRotation } from "@/lib/map-presentation"

interface VehicleMapMarkerOptions {
  readonly ariaLabel: string
  readonly onSelect: (vehicleId: string) => void
  readonly selected: boolean
  readonly vehicle: ValidatedVehicle
}

export interface VehicleMapMarker {
  readonly remove: () => void
}

export function addVehicleMapMarker(
  map: maplibregl.Map,
  { ariaLabel, onSelect, selected, vehicle }: VehicleMapMarkerOptions,
): VehicleMapMarker {
  const element = document.createElement("button")
  const root = createRoot(element)

  element.setAttribute("aria-label", ariaLabel)
  element.type = "button"
  root.render(<VehicleMapMarkerContents selected={selected} vehicle={vehicle} />)
  element.addEventListener("click", () => onSelect(vehicle.id))
  const marker = new maplibregl.Marker({ element })
    .setLngLat([vehicle.longitude, vehicle.latitude])
    .addTo(map)

  return {
    remove: () => {
      root.unmount()
      marker.remove()
    },
  }
}

function VehicleMapMarkerContents({
  selected,
  vehicle,
}: {
  readonly selected: boolean
  readonly vehicle: ValidatedVehicle
}) {
  const Icon = vehicleIconForMode(vehicle.mode)
  const rotation = vehicleBearingRotation(vehicle.bearing)
  const shellClassName = markerClassName(vehicle, selected)
  const rotationStyle = rotation === undefined ? undefined : { transform: `rotate(${rotation}deg)` }

  return (
    <span className={shellClassName}>
      <Icon aria-hidden="true" size={20} weight="fill" />
      {rotation === undefined ? null : (
        <NavigationArrowIcon
          aria-hidden="true"
          className="absolute -top-1.5 left-1/2 -translate-x-1/2 text-foreground"
          size={12}
          style={rotationStyle}
          weight="fill"
        />
      )}
    </span>
  )
}

function markerClassName(vehicle: ValidatedVehicle, selected: boolean): string {
  const base =
    "pointer-events-none grid size-11 cursor-pointer place-items-center border-2 bg-[color:var(--surface-primary)] text-foreground transition-[transform,opacity] duration-200 focus-visible:outline-3 focus-visible:outline-offset-2 focus-visible:outline-[color:var(--focus-ring)] motion-reduce:transition-none"
  const selection = selected ? " ring-2 ring-[color:var(--action-primary)] ring-offset-2" : ""
  if (vehicle.freshness === "stale") {
    return `${base} rounded-sm border-dashed border-[color:var(--status-warning)]${selection}`
  }
  return `${base} rounded-full border-[color:var(--status-live)]${selection}`
}
