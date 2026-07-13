import { MapTrifold, Warning } from "@phosphor-icons/react"
import maplibregl from "maplibre-gl"
import { useEffect, useRef, useState } from "react"

import { Button } from "@/components/ui/button"
import type { ValidatedVehicle } from "@/hooks/use-transit-board"

import "maplibre-gl/dist/maplibre-gl.css"

interface NetworkMapPanelProps {
  readonly isDark: boolean
  readonly vehicles: readonly ValidatedVehicle[]
}

const mapTilerKey = import.meta.env["VITE_MAPTILER_KEY"]

export function NetworkMapPanel({ isDark, vehicles }: NetworkMapPanelProps) {
  const mapElement = useRef<HTMLElement>(null)
  const [mapFailed, setMapFailed] = useState(false)
  const [selectedVehicleId, setSelectedVehicleId] = useState("")
  const canRenderMap = Boolean(mapTilerKey) && !mapFailed
  const selectedVehicle = vehicles.find((vehicle) => vehicle.id === selectedVehicleId)

  useEffect(() => {
    if (selectedVehicleId && !selectedVehicle) {
      setSelectedVehicleId("")
    }
  }, [selectedVehicle, selectedVehicleId])

  useEffect(() => {
    if (!mapElement.current || !mapTilerKey || mapFailed) {
      return undefined
    }
    if (!supportsWebGl()) {
      setMapFailed(true)
      return undefined
    }

    const styleName = isDark ? "streets-v2-dark" : "streets-v2"
    const map = new maplibregl.Map({
      center: [101.6869, 3.139],
      container: mapElement.current,
      maxZoom: 16,
      minZoom: 7,
      style: `https://api.maptiler.com/maps/${styleName}/style.json?key=${encodeURIComponent(mapTilerKey)}`,
      zoom: 10,
    })

    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right")
    map.once("load", () => {
      for (const vehicle of vehicles) {
        const marker = document.createElement("button")
        marker.type = "button"
        marker.className = markerClassName(vehicle, selectedVehicleId)
        marker.setAttribute("aria-label", vehicleAriaLabel(vehicle))
        marker.addEventListener("click", () => setSelectedVehicleId(vehicle.id))
        new maplibregl.Marker({ element: marker })
          .setLngLat([vehicle.longitude, vehicle.latitude])
          .addTo(map)
      }
    })
    map.once("error", () => setMapFailed(true))

    return () => map.remove()
  }, [isDark, mapFailed, selectedVehicleId, vehicles])

  return (
    <section aria-labelledby="network-map-heading" className="space-y-3">
      <div className="flex items-baseline justify-between gap-4">
        <div>
          <p className="font-mono text-xs font-semibold tracking-wide text-muted-foreground uppercase">
            KL / Klang Valley first
          </p>
          <h2 id="network-map-heading" className="mt-1 text-xl font-semibold">
            Network view
          </h2>
        </div>
        <MapTrifold aria-hidden="true" className="text-primary" size={26} weight="duotone" />
      </div>
      {canRenderMap ? (
        <>
          <section
            aria-label="Network map. Every vehicle has an equivalent control below."
            className="h-72 overflow-hidden rounded-sm border border-border sm:h-96"
            ref={mapElement}
          />
          <p className="text-sm text-muted-foreground">
            Map data © MapTiler © OpenStreetMap contributors. Route and vehicle details remain
            available in the service board.
          </p>
        </>
      ) : (
        <div className="flex min-h-72 flex-col justify-center border border-dashed border-border bg-muted/45 p-5 sm:min-h-96">
          <Warning
            aria-hidden="true"
            className="mb-4 text-[color:var(--status-warning-foreground)]"
            size={28}
            weight="duotone"
          />
          <p className="text-lg font-semibold">
            {mapFailed ? "Map unavailable" : "Map configuration required"}
          </p>
          <p className="mt-2 max-w-lg text-sm leading-6 text-muted-foreground">
            {mapFailed
              ? "The map could not be started on this device. The complete service board remains available without it."
              : "Set the restricted MapTiler browser key before deployment. The complete service board remains available without a map."}
          </p>
        </div>
      )}
      {vehicles.length > 0 ? (
        <VehicleControls
          onSelect={setSelectedVehicleId}
          selectedVehicle={selectedVehicle}
          selectedVehicleId={selectedVehicleId}
          vehicles={vehicles}
        />
      ) : null}
    </section>
  )
}

interface VehicleControlsProps {
  readonly onSelect: (vehicleId: string) => void
  readonly selectedVehicle: ValidatedVehicle | undefined
  readonly selectedVehicleId: string
  readonly vehicles: readonly ValidatedVehicle[]
}

function VehicleControls({
  onSelect,
  selectedVehicle,
  selectedVehicleId,
  vehicles,
}: VehicleControlsProps) {
  return (
    <section
      aria-label="Validated vehicle locations"
      className="border-l-2 border-[color:var(--status-live-border)] pl-3 text-sm"
    >
      <p className="font-medium text-[color:var(--status-live-foreground)]">
        Validated vehicle locations
      </p>
      <ul className="mt-2 space-y-2">
        {vehicles.map((vehicle) => (
          <li key={vehicle.id}>
            <Button
              aria-pressed={selectedVehicleId === vehicle.id}
              className="h-auto min-h-11 w-full justify-start text-left"
              onClick={() => onSelect(vehicle.id)}
              type="button"
              variant={selectedVehicleId === vehicle.id ? "default" : "outline"}
            >
              {vehicle.label} · {vehicle.feed} ·{" "}
              {vehicle.freshness === "live" ? "Verified live" : "Live feed stale"}
            </Button>
          </li>
        ))}
      </ul>
      {selectedVehicle ? (
        <section aria-live="polite" className="mt-3 border-t border-border pt-3">
          <p className="font-mono text-xs tracking-wide text-muted-foreground uppercase">
            Selected vehicle
          </p>
          <p className="mt-1 font-medium">{selectedVehicle.label}</p>
          <p className="mt-1 text-muted-foreground">{vehicleAriaLabel(selectedVehicle)}</p>
        </section>
      ) : null}
    </section>
  )
}

function markerClassName(vehicle: ValidatedVehicle, selectedVehicleId: string): string {
  const base =
    "grid size-11 cursor-pointer place-items-center bg-transparent before:block before:size-4 before:rounded-full before:border-2 before:border-white focus-visible:outline-3 focus-visible:outline-offset-2"
  if (vehicle.id === selectedVehicleId) {
    return `${base} before:bg-primary before:ring-2 before:ring-primary/40`
  }
  return vehicle.freshness === "live"
    ? `${base} before:bg-[color:var(--status-live)]`
    : `${base} before:bg-[color:var(--status-warning)]`
}

function vehicleAriaLabel(vehicle: ValidatedVehicle): string {
  const state = vehicle.freshness === "live" ? "verified live" : "last verified position is stale"
  return `${vehicle.label} from ${vehicle.feed}; ${state}; updated ${formatAge(vehicle.updatedAt)} ago.`
}

function formatAge(updatedAt: string): string {
  const ageSeconds = Math.max(0, Math.floor((Date.now() - new Date(updatedAt).getTime()) / 1_000))
  if (ageSeconds < 60) {
    return `${ageSeconds} seconds`
  }
  if (ageSeconds < 3_600) {
    return `${Math.floor(ageSeconds / 60)} minutes`
  }
  return `${Math.floor(ageSeconds / 3_600)} hours`
}

function supportsWebGl(): boolean {
  const canvas = document.createElement("canvas")
  return Boolean(canvas.getContext("webgl2") ?? canvas.getContext("webgl"))
}
