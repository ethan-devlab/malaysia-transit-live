import { MapTrifold, Warning } from "@phosphor-icons/react"
import { useQuery } from "@tanstack/react-query"
import maplibregl from "maplibre-gl"
import { useEffect, useMemo, useRef, useState } from "react"

import { Button } from "@/components/ui/button"
import type { NetworkFocus, TransitJourney } from "@/domain/transit"
import type { ValidatedVehicle } from "@/hooks/use-transit-board"
import { shouldFallbackForMapError } from "@/lib/map-runtime"
import { fetchTripDetail, type TripDetail } from "@/lib/transit-api"

import "maplibre-gl/dist/maplibre-gl.css"

interface NetworkMapPanelProps {
  readonly focus: NetworkFocus | undefined
  readonly isDark: boolean
  readonly onSelectVehicle: (vehicleId: string) => void
  readonly selectedJourney: TransitJourney | undefined
  readonly vehicles: readonly ValidatedVehicle[]
}

interface TripTarget {
  readonly feed: string
  readonly id: string
  readonly serviceDate: string
  readonly tripId: string
}

interface MapRouteData {
  readonly features: readonly MapRouteFeature[]
  readonly type: "FeatureCollection"
}

interface MapRouteFeature {
  readonly geometry:
    | { readonly coordinates: [number, number]; readonly type: "Point" }
    | { readonly coordinates: [number, number][]; readonly type: "LineString" }
  readonly properties: Record<string, never>
  readonly type: "Feature"
}

interface NextScheduledStop {
  readonly name: string
  readonly time: string
}

interface VehicleFeatureCollection {
  readonly features: readonly {
    readonly geometry: { readonly coordinates: [number, number]; readonly type: "Point" }
    readonly properties: { readonly freshness: "live" | "stale"; readonly vehicleId: string }
    readonly type: "Feature"
  }[]
  readonly type: "FeatureCollection"
}

const mapTilerKey = import.meta.env["VITE_MAPTILER_KEY"]
const routeSourceId = "selected-trip-route"
const routeLineLayerId = "selected-trip-line"
const routeStopLayerId = "selected-trip-stops"
const vehicleSourceId = "dashboard-vehicles"
const vehicleClusterLayerId = "dashboard-vehicle-clusters"
const vehicleClusterCountLayerId = "dashboard-vehicle-cluster-count"
const vehiclePointLayerId = "dashboard-vehicle-points"
const defaultVehicleLimit = 8
const vehicleClusterThreshold = 40
const emptyStyleImage = { data: new Uint8Array([0, 0, 0, 0]), height: 1, width: 1 }

export function NetworkMapPanel({
  focus,
  isDark,
  onSelectVehicle,
  selectedJourney,
  vehicles,
}: NetworkMapPanelProps) {
  const mapElement = useRef<HTMLDivElement>(null)
  const mapInstance = useRef<maplibregl.Map | null>(null)
  const markerInstances = useRef<maplibregl.Marker[]>([])
  const focusedTripId = useRef("")
  const focusedVehicleId = useRef("")
  const [mapFailed, setMapFailed] = useState(false)
  const [mapLoaded, setMapLoaded] = useState(false)
  const canRenderMap = Boolean(mapTilerKey) && !mapFailed
  const selectedVehicleId = focus?.kind === "vehicle" ? focus.id : ""
  const selectedVehicle = vehicles.find((vehicle) => vehicle.id === selectedVehicleId)
  const focusedJourney = focus?.kind === "vehicle" ? undefined : selectedJourney
  const tripTarget = useMemo(
    () => tripTargetFor(focusedJourney, selectedVehicle, focus?.revision ?? 0),
    [focus?.revision, focusedJourney, selectedVehicle],
  )
  const tripQuery = useQuery({
    enabled: tripTarget !== undefined && import.meta.env.PROD,
    queryFn: ({ signal }) =>
      fetchTripDetail(
        tripTarget?.feed ?? "",
        tripTarget?.tripId ?? "",
        tripTarget?.serviceDate ?? "",
        signal,
      ),
    queryKey: [
      "selected-trip-stops",
      tripTarget?.feed,
      tripTarget?.tripId,
      tripTarget?.serviceDate,
    ],
  })
  const routeData = useMemo(() => routeDataFor(tripQuery.data?.stops ?? []), [tripQuery.data])
  const nextStop = useMemo(() => nextScheduledStop(tripQuery.data), [tripQuery.data])

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
    let hasLoaded = false
    const onLoad = () => {
      hasLoaded = true
      setMapLoaded(true)
    }

    mapInstance.current = map
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right")
    map.on("styleimagemissing", (event) => {
      if (event.id === " " && !map.hasImage(event.id)) {
        map.addImage(event.id, emptyStyleImage)
      }
    })
    map.once("load", onLoad)
    map.on("error", () => {
      if (shouldFallbackForMapError(hasLoaded)) setMapFailed(true)
    })

    return () => {
      markerInstances.current.forEach((marker) => {
        marker.remove()
      })
      markerInstances.current = []
      map.remove()
      mapInstance.current = null
      setMapLoaded(false)
    }
  }, [isDark, mapFailed])

  useEffect(() => {
    const map = mapInstance.current
    if (!mapLoaded || !map) {
      return
    }
    markerInstances.current.forEach((marker) => {
      marker.remove()
    })
    markerInstances.current = []
    removeVehicleLayers(map)
    if (vehicles.length > vehicleClusterThreshold) {
      const vehicleData: VehicleFeatureCollection = {
        features: vehicles.map((vehicle) => ({
          geometry: { coordinates: [vehicle.longitude, vehicle.latitude], type: "Point" },
          properties: { freshness: vehicle.freshness, vehicleId: vehicle.id },
          type: "Feature",
        })),
        type: "FeatureCollection",
      }
      return addVehicleClusterLayers(map, vehicleData, onSelectVehicle)
    }
    markerInstances.current = vehicles.map((vehicle) => {
      const marker = document.createElement("button")
      marker.type = "button"
      marker.className = markerClassName(vehicle, selectedVehicleId)
      marker.setAttribute("aria-label", vehicleAriaLabel(vehicle))
      marker.addEventListener("click", () => onSelectVehicle(vehicle.id))
      return new maplibregl.Marker({ element: marker })
        .setLngLat([vehicle.longitude, vehicle.latitude])
        .addTo(map)
    })
  }, [mapLoaded, onSelectVehicle, selectedVehicleId, vehicles])

  useEffect(() => {
    const map = mapInstance.current
    if (!mapLoaded || !map) {
      return
    }
    if (routeData.features.length === 0) {
      removeRouteLayers(map)
      return
    }
    addOrUpdateRouteLayers(map, routeData)
    if (tripTarget && focusedTripId.current !== tripTarget.id) {
      focusedTripId.current = tripTarget.id
      focusRoute(map, routeData)
    }
  }, [mapLoaded, routeData, tripTarget])

  useEffect(() => {
    const map = mapInstance.current
    if (!mapLoaded || !map || !selectedVehicle) {
      return
    }
    const vehicleFocusId = `${selectedVehicle.id}:${focus?.revision ?? 0}`
    if (focusedVehicleId.current === vehicleFocusId) {
      return
    }
    focusedVehicleId.current = vehicleFocusId
    map.flyTo({
      center: [selectedVehicle.longitude, selectedVehicle.latitude],
      duration: motionDuration(),
      essential: true,
      zoom: Math.max(map.getZoom(), 13),
    })
  }, [focus?.revision, mapLoaded, selectedVehicle])

  return (
    <section aria-labelledby="network-map-heading" className="min-w-0 space-y-3">
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
          <div
            className="h-[28rem] w-full overflow-hidden rounded-sm border border-border md:h-[34rem] xl:h-[calc(100dvh-10rem)] xl:min-h-[42rem] xl:max-h-[52rem]"
            ref={mapElement}
          />
          <MapStatus
            hasTripTarget={tripTarget !== undefined}
            routeId={tripQuery.data?.route_id}
            selectedJourney={focusedJourney}
            selectedVehicle={selectedVehicle}
            tripQueryState={tripQuery.status}
          />
          <p className="text-sm text-muted-foreground">
            Map data © MapTiler © OpenStreetMap contributors. The route line joins scheduled stop
            coordinates; it is not a road-level path or an ETA.
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
          nextStop={nextStop}
          nextStopUnavailableReason={
            selectedVehicle && !selectedVehicle.tripId
              ? "The upstream location did not identify a scheduled trip."
              : undefined
          }
          onSelect={onSelectVehicle}
          selectedVehicle={selectedVehicle}
          selectedVehicleId={selectedVehicleId}
          vehicles={vehicles}
        />
      ) : null}
    </section>
  )
}

function MapStatus({
  hasTripTarget,
  routeId,
  selectedJourney,
  selectedVehicle,
  tripQueryState,
}: {
  readonly hasTripTarget: boolean
  readonly routeId: string | undefined
  readonly selectedJourney: TransitJourney | undefined
  readonly selectedVehicle: ValidatedVehicle | undefined
  readonly tripQueryState: "error" | "pending" | "success"
}) {
  if (selectedVehicle && !selectedVehicle.tripId) {
    return (
      <p className="text-sm text-muted-foreground">
        Showing the current position for {selectedVehicle.label}. The upstream feed did not identify
        its scheduled trip.
      </p>
    )
  }
  if (hasTripTarget && tripQueryState === "pending") {
    return (
      <p className="text-sm text-muted-foreground">Loading the selected scheduled stop sequence.</p>
    )
  }
  if (tripQueryState === "error") {
    return (
      <p className="text-sm text-[color:var(--status-error-foreground)]">
        The selected route could not be loaded.
      </p>
    )
  }
  if (selectedVehicle) {
    return (
      <p className="text-sm text-muted-foreground">
        Showing the scheduled stop sequence for {selectedVehicle.label}
        {routeId ? ` on route ${routeId}` : ""}.
      </p>
    )
  }
  if (selectedJourney) {
    return (
      <p className="text-sm text-muted-foreground">
        Showing the scheduled stop sequence for {selectedJourney.routeLabel}.
      </p>
    )
  }
  return (
    <p className="text-sm text-muted-foreground">
      Select a service or validated vehicle to focus it on the map.
    </p>
  )
}

interface VehicleControlsProps {
  readonly nextStop: NextScheduledStop | undefined
  readonly nextStopUnavailableReason: string | undefined
  readonly onSelect: (vehicleId: string) => void
  readonly selectedVehicle: ValidatedVehicle | undefined
  readonly selectedVehicleId: string
  readonly vehicles: readonly ValidatedVehicle[]
}

function VehicleControls({
  nextStop,
  nextStopUnavailableReason,
  onSelect,
  selectedVehicle,
  selectedVehicleId,
  vehicles,
}: VehicleControlsProps) {
  const [showAll, setShowAll] = useState(false)
  const visibleVehicles = showAll ? vehicles : vehicles.slice(0, defaultVehicleLimit)
  const feedCount = new Set(vehicles.map((vehicle) => vehicle.feed)).size

  return (
    <section
      aria-label="Validated vehicle locations"
      className="border border-border bg-muted/20 p-3 text-sm"
    >
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="font-medium text-[color:var(--status-live-foreground)]">
            Validated vehicle locations
          </p>
          <p className="mt-1 text-muted-foreground">
            {vehicles.length} shown positions from {feedCount} official feed
            {feedCount === 1 ? "" : "s"}.
          </p>
        </div>
        {vehicles.length > defaultVehicleLimit ? (
          <Button
            onClick={() => setShowAll((isVisible) => !isVisible)}
            type="button"
            variant="ghost"
          >
            {showAll ? "Show fewer" : `Show all ${vehicles.length}`}
          </Button>
        ) : null}
      </div>
      <ul className={showAll ? "mt-3 max-h-80 space-y-2 overflow-y-auto pr-1" : "mt-3 space-y-2"}>
        {visibleVehicles.map((vehicle) => (
          <li key={vehicle.id}>
            <Button
              aria-pressed={selectedVehicleId === vehicle.id}
              className="h-auto min-h-11 w-full justify-start text-left whitespace-normal"
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
          <dl className="mt-3 grid gap-3 border-l border-border pl-3 text-sm">
            <div>
              <dt className="font-mono text-xs tracking-wide text-muted-foreground uppercase">
                Next scheduled stop
              </dt>
              <dd className="mt-1 font-medium">
                {nextStop
                  ? `${nextStop.name} · ${nextStop.time}`
                  : (nextStopUnavailableReason ?? "No later scheduled stop in this trip")}
              </dd>
            </div>
            <div>
              <dt className="font-mono text-xs tracking-wide text-muted-foreground uppercase">
                Vehicle position
              </dt>
              <dd className="mt-1 font-mono text-xs">
                {selectedVehicle.latitude.toFixed(5)}, {selectedVehicle.longitude.toFixed(5)}
              </dd>
            </div>
          </dl>
          <p className="mt-3 text-xs leading-5 text-muted-foreground">
            The next stop is from the published timetable, not a live arrival estimate.
          </p>
        </section>
      ) : null}
    </section>
  )
}

function tripTargetFor(
  selectedJourney: TransitJourney | undefined,
  selectedVehicle: ValidatedVehicle | undefined,
  focusRevision: number,
): TripTarget | undefined {
  if (selectedVehicle?.tripId) {
    return {
      feed: selectedVehicle.feed,
      id: `${selectedVehicle.feed}:${selectedVehicle.tripId}:${focusRevision}`,
      serviceDate: selectedJourney?.serviceDateIso ?? localServiceDate(),
      tripId: selectedVehicle.tripId,
    }
  }
  if (!selectedJourney) {
    return undefined
  }
  return {
    feed: selectedJourney.feedId,
    id: `${selectedJourney.id}:${focusRevision}`,
    serviceDate: selectedJourney.serviceDateIso,
    tripId: selectedJourney.id.slice(selectedJourney.feedId.length + 1),
  }
}

function routeDataFor(
  stops: readonly { readonly latitude: number | null; readonly longitude: number | null }[],
): MapRouteData {
  const points: [number, number][] = []
  stops.forEach((stop) => {
    if (stop.latitude !== null && stop.longitude !== null) {
      points.push([stop.longitude, stop.latitude])
    }
  })
  const features: MapRouteFeature[] = points.map((coordinates) => ({
    geometry: { coordinates, type: "Point" },
    properties: {},
    type: "Feature",
  }))
  if (points.length > 1) {
    features.unshift({
      geometry: { coordinates: points, type: "LineString" },
      properties: {},
      type: "Feature",
    })
  }
  return {
    features,
    type: "FeatureCollection",
  }
}

function nextScheduledStop(tripDetail: TripDetail | undefined): NextScheduledStop | undefined {
  if (!tripDetail) {
    return undefined
  }
  const currentSeconds = currentServiceSeconds(tripDetail.service_date)
  const stop = tripDetail.stops.find((candidate) => {
    const scheduledSeconds = gtfsTimeToSeconds(candidate.departure_time || candidate.arrival_time)
    return scheduledSeconds !== undefined && scheduledSeconds >= currentSeconds
  })
  if (!stop) {
    return undefined
  }
  return {
    name: stop.name,
    time: stop.departure_time || stop.arrival_time,
  }
}

function currentServiceSeconds(serviceDate: string): number {
  const values = Object.fromEntries(
    new Intl.DateTimeFormat("en-CA", {
      day: "2-digit",
      hour: "2-digit",
      hourCycle: "h23",
      minute: "2-digit",
      month: "2-digit",
      second: "2-digit",
      timeZone: "Asia/Kuala_Lumpur",
      year: "numeric",
    })
      .formatToParts(new Date())
      .map((part) => [part.type, part.value]),
  )
  const [year, month, day] = serviceDate.split("-").map(Number)
  return Math.floor(
    (Date.UTC(
      Number(values["year"]),
      Number(values["month"]) - 1,
      Number(values["day"]),
      Number(values["hour"]),
      Number(values["minute"]),
      Number(values["second"]),
    ) -
      Date.UTC(year ?? 0, (month ?? 1) - 1, day ?? 1)) /
      1_000,
  )
}

function gtfsTimeToSeconds(time: string): number | undefined {
  const [hours, minutes, seconds] = time.split(":").map(Number)
  if (
    hours === undefined ||
    minutes === undefined ||
    seconds === undefined ||
    Number.isNaN(hours) ||
    Number.isNaN(minutes) ||
    Number.isNaN(seconds) ||
    minutes > 59 ||
    seconds > 59
  ) {
    return undefined
  }
  return hours * 3_600 + minutes * 60 + seconds
}

function addOrUpdateRouteLayers(map: maplibregl.Map, routeData: MapRouteData) {
  const source = map.getSource(routeSourceId)
  if (source) {
    const geoJsonSource = source as maplibregl.GeoJSONSource
    geoJsonSource.setData(routeData)
    return
  }
  const routeColour = cssToken("--action-primary")
  const stopColour = cssToken("--status-live")
  const stopStrokeColour = cssToken("--surface-primary")
  if (!routeColour || !stopColour || !stopStrokeColour) {
    return
  }
  map.addSource(routeSourceId, { data: routeData, type: "geojson" })
  map.addLayer({
    filter: ["==", "$type", "LineString"],
    id: routeLineLayerId,
    layout: { "line-cap": "round", "line-join": "round" },
    paint: { "line-color": routeColour, "line-width": 4 },
    source: routeSourceId,
    type: "line",
  })
  map.addLayer({
    filter: ["==", "$type", "Point"],
    id: routeStopLayerId,
    paint: {
      "circle-color": stopColour,
      "circle-radius": 4,
      "circle-stroke-color": stopStrokeColour,
      "circle-stroke-width": 1,
    },
    source: routeSourceId,
    type: "circle",
  })
}

function removeRouteLayers(map: maplibregl.Map) {
  if (map.getLayer(routeStopLayerId)) {
    map.removeLayer(routeStopLayerId)
  }
  if (map.getLayer(routeLineLayerId)) {
    map.removeLayer(routeLineLayerId)
  }
  if (map.getSource(routeSourceId)) {
    map.removeSource(routeSourceId)
  }
}

function addVehicleClusterLayers(
  map: maplibregl.Map,
  data: VehicleFeatureCollection,
  onSelectVehicle: (vehicleId: string) => void,
): () => void {
  const liveColour = cssToken("--status-live")
  const warningColour = cssToken("--status-warning")
  const surfaceColour = cssToken("--surface-primary")
  const textColour = cssToken("--text-primary")
  if (!liveColour || !warningColour || !surfaceColour || !textColour) {
    return () => undefined
  }
  map.addSource(vehicleSourceId, {
    cluster: true,
    clusterMaxZoom: 14,
    clusterRadius: 48,
    clusterProperties: {
      live_count: ["+", ["case", ["==", ["get", "freshness"], "live"], 1, 0]],
    },
    data,
    type: "geojson",
  })
  map.addLayer({
    id: vehicleClusterLayerId,
    paint: {
      "circle-color": [
        "case",
        ["==", ["get", "live_count"], ["get", "point_count"]],
        liveColour,
        warningColour,
      ],
      "circle-radius": ["step", ["get", "point_count"], 18, 50, 22, 100, 28],
      "circle-stroke-color": surfaceColour,
      "circle-stroke-width": 2,
    },
    source: vehicleSourceId,
    type: "circle",
  })
  map.addLayer({
    id: vehicleClusterCountLayerId,
    layout: { "text-field": ["get", "point_count_abbreviated"], "text-size": 12 },
    paint: { "text-color": textColour },
    source: vehicleSourceId,
    type: "symbol",
  })
  map.addLayer({
    filter: ["!", ["has", "point_count"]],
    id: vehiclePointLayerId,
    paint: {
      "circle-color": ["case", ["==", ["get", "freshness"], "live"], liveColour, warningColour],
      "circle-radius": 7,
      "circle-stroke-color": surfaceColour,
      "circle-stroke-width": 2,
    },
    source: vehicleSourceId,
    type: "circle",
  })
  const onClusterClick = (event: maplibregl.MapMouseEvent) => {
    map.easeTo({
      center: event.lngLat,
      duration: motionDuration(),
      zoom: Math.min(map.getZoom() + 2, 16),
    })
  }
  const onPointClick = (event: maplibregl.MapMouseEvent) => {
    const feature = map.queryRenderedFeatures(event.point, { layers: [vehiclePointLayerId] })[0]
    const vehicleId = feature?.properties?.["vehicleId"]
    if (typeof vehicleId === "string") onSelectVehicle(vehicleId)
  }
  map.on("click", vehicleClusterLayerId, onClusterClick)
  map.on("click", vehiclePointLayerId, onPointClick)
  return () => {
    map.off("click", vehicleClusterLayerId, onClusterClick)
    map.off("click", vehiclePointLayerId, onPointClick)
    removeVehicleLayers(map)
  }
}

function removeVehicleLayers(map: maplibregl.Map) {
  if (map.getLayer(vehiclePointLayerId)) map.removeLayer(vehiclePointLayerId)
  if (map.getLayer(vehicleClusterCountLayerId)) map.removeLayer(vehicleClusterCountLayerId)
  if (map.getLayer(vehicleClusterLayerId)) map.removeLayer(vehicleClusterLayerId)
  if (map.getSource(vehicleSourceId)) map.removeSource(vehicleSourceId)
}

function focusRoute(map: maplibregl.Map, routeData: MapRouteData) {
  const points = routeData.features.flatMap((feature) =>
    feature.geometry.type === "Point" ? [feature.geometry.coordinates] : [],
  )
  if (points.length === 0) {
    return
  }
  const [firstPoint] = points
  if (!firstPoint) {
    return
  }
  const bounds = new maplibregl.LngLatBounds(firstPoint, firstPoint)
  points.slice(1).forEach((point) => {
    bounds.extend(point)
  })
  map.resize()
  if (points.length === 1) {
    map.flyTo({ center: firstPoint, duration: motionDuration(), essential: true, zoom: 13 })
    return
  }
  map.fitBounds(bounds, { duration: motionDuration(), maxZoom: 14, padding: 48 })
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

function cssToken(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim()
}

function localServiceDate(): string {
  const parts = new Intl.DateTimeFormat("en-CA", {
    day: "2-digit",
    month: "2-digit",
    timeZone: "Asia/Kuala_Lumpur",
    year: "numeric",
  }).formatToParts(new Date())
  const values = Object.fromEntries(parts.map((part) => [part.type, part.value]))
  return `${values["year"]}-${values["month"]}-${values["day"]}`
}

function motionDuration(): number {
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches ? 0 : 300
}

function supportsWebGl(): boolean {
  const canvas = document.createElement("canvas")
  return Boolean(canvas.getContext("webgl2") ?? canvas.getContext("webgl"))
}
