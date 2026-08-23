import { MapTrifold, Warning } from "@phosphor-icons/react"
import { useQuery } from "@tanstack/react-query"
import maplibregl from "maplibre-gl"
import maplibreWorkerUrl from "maplibre-gl/dist/maplibre-gl-csp-worker.js?url"
import { type ReactNode, useCallback, useEffect, useMemo, useRef, useState } from "react"

import { Button } from "@/components/ui/button"
import { addVehicleMapMarker, type VehicleMapMarker } from "@/components/vehicle-map-marker"
import { addVehicleMapPopup, type VehicleMapPopup } from "@/components/vehicle-map-popup"
import type { NetworkFocus, TransitJourney, VehicleMapMode } from "@/domain/transit"
import type { ValidatedVehicle } from "@/hooks/use-transit-board"
import {
  type CivicMapTheme,
  civicBasemapPatch,
  civicMapStyleUrl,
  mapMotionDuration,
  routeColourContrastFor,
  routeColourFor,
  routePresentationFor,
} from "@/lib/map-presentation"
import { isMapStyleReady, shouldFallbackForMapError } from "@/lib/map-runtime"
import { fetchTripDetail, type TripDetail } from "@/lib/transit-api"
import { type MapRouteData, routeDataFor } from "@/lib/trip-route-data"
import { installVehicleMapSprites } from "@/lib/vehicle-map-sprites"

import "maplibre-gl/dist/maplibre-gl.css"

maplibregl.setWorkerUrl(maplibreWorkerUrl)

interface NetworkMapPanelProps {
  readonly afterMapCanvas?: ReactNode
  readonly eyebrow: string
  readonly focus: NetworkFocus | undefined
  readonly heading: string
  readonly isDark: boolean
  readonly landmarkLabel: string
  readonly onSelectVehicle: (vehicleId: string) => void
  readonly selectedJourney: TransitJourney | undefined
  readonly showVehicleControls: boolean
  readonly vehicles: readonly ValidatedVehicle[]
}

interface TripTarget {
  readonly feed: string
  readonly id: string
  readonly serviceDate: string
  readonly tripId: string
}

interface NextScheduledStop {
  readonly id: string
  readonly name: string
  readonly time: string
}

interface VehicleFeatureCollection {
  readonly features: readonly {
    readonly geometry: { readonly coordinates: [number, number]; readonly type: "Point" }
    readonly properties: {
      readonly freshness: "live" | "stale"
      readonly mode: VehicleMapMode
      readonly vehicleId: string
    }
    readonly type: "Feature"
  }[]
  readonly type: "FeatureCollection"
}

const mapTilerKey = import.meta.env["VITE_MAPTILER_KEY"]
const routeSourceId = "selected-trip-route"
const routeOfficialCasingLayerId = "selected-trip-official-casing"
const routeOfficialLayerId = "selected-trip-official-line"
const routeApproximateCasingLayerId = "selected-trip-approximate-casing"
const routeApproximateLayerId = "selected-trip-approximate-line"
const routeLabelLayerId = "selected-trip-route-label"
const routeStopLayerId = "selected-trip-ordinary-stops"
const routeSelectedStopLayerId = "selected-trip-next-scheduled-stop"
const routeStopLabelLayerId = "selected-trip-stop-labels"
const routeTerminusLayerId = "selected-trip-termini"
const vehicleSourceId = "dashboard-vehicles"
const vehicleClusterLayerId = "dashboard-vehicle-clusters"
const vehicleClusterCountLayerId = "dashboard-vehicle-cluster-count"
const vehiclePointLayerId = "dashboard-vehicle-points"
const defaultVehicleLimit = 8
const vehicleClusterThreshold = 40
const emptyStyleImage = { data: new Uint8Array([0, 0, 0, 0]), height: 1, width: 1 }

// allow: SIZE_OK — one MapLibre canvas lifecycle needs shared setup and teardown.
export function NetworkMapPanel({
  afterMapCanvas,
  eyebrow,
  focus,
  heading,
  isDark,
  landmarkLabel,
  onSelectVehicle,
  selectedJourney,
  showVehicleControls,
  vehicles,
}: NetworkMapPanelProps) {
  const mapElement = useRef<HTMLDivElement>(null)
  const mapInstance = useRef<maplibregl.Map | null>(null)
  const styleReadyMap = useRef<maplibregl.Map | null>(null)
  const markerInstances = useRef<VehicleMapMarker[]>([])
  const activeVehiclePopup = useRef<VehicleMapPopup | null>(null)
  const activeVehiclePopupKey = useRef("")
  const focusedTripId = useRef("")
  const focusedVehicleId = useRef("")
  const [mapFailed, setMapFailed] = useState(false)
  const [mapGeneration, setMapGeneration] = useState(0)
  const [mapLoaded, setMapLoaded] = useState(false)
  const [styleGeneration, setStyleGeneration] = useState(0)
  const removeActiveVehiclePopup = useCallback(() => {
    activeVehiclePopup.current?.remove()
    activeVehiclePopup.current = null
    activeVehiclePopupKey.current = ""
  }, [])
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
  const nextStop = useMemo(() => nextScheduledStop(tripQuery.data), [tripQuery.data])
  const routeData = useMemo(
    () =>
      routeDataFor(
        tripQuery.data,
        selectedVehicle && nextStop ? { selectedStopId: nextStop.id } : {},
      ),
    [nextStop, selectedVehicle, tripQuery.data],
  )
  const routeColour = tripQuery.data?.route_color ? `#${tripQuery.data.route_color}` : undefined

  useEffect(() => {
    if (!mapElement.current || !mapTilerKey || mapFailed) {
      return undefined
    }
    if (!supportsWebGl()) {
      setMapFailed(true)
      return undefined
    }

    const theme: CivicMapTheme = isDark ? "dark" : "light"
    const map = new maplibregl.Map({
      center: [101.6869, 3.139],
      container: mapElement.current,
      maxZoom: 16,
      minZoom: 7,
      style: civicMapStyleUrl(theme, mapTilerKey),
      zoom: 10,
    })
    map.getCanvas().setAttribute("aria-label", `${landmarkLabel} canvas`)
    let hasLoaded = false
    const onStyleLoad = () => {
      hasLoaded = true
      mapInstance.current = map
      styleReadyMap.current = map
      applyCivicBasemapTuning(map, theme)
      setMapLoaded(true)
      setStyleGeneration((current) => current + 1)
    }
    const onStyleImageMissing = (event: { readonly id: string }) => {
      if (event.id === " " && !map.hasImage(event.id)) {
        map.addImage(event.id, emptyStyleImage)
      }
    }
    const onMapError = () => {
      if (shouldFallbackForMapError(hasLoaded)) {
        setMapFailed(true)
      }
    }

    mapInstance.current = map
    styleReadyMap.current = null
    setMapGeneration((current) => current + 1)
    focusedTripId.current = ""
    focusedVehicleId.current = ""
    setMapLoaded(false)
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right")
    map.on("styleimagemissing", onStyleImageMissing)
    map.on("style.load", onStyleLoad)
    map.on("error", onMapError)

    return () => {
      map.off("styleimagemissing", onStyleImageMissing)
      map.off("style.load", onStyleLoad)
      map.off("error", onMapError)
      removeActiveVehiclePopup()
      markerInstances.current.forEach((marker) => {
        marker.remove()
      })
      markerInstances.current = []
      if (styleReadyMap.current === map) {
        styleReadyMap.current = null
      }
      if (mapInstance.current === map) {
        mapInstance.current = null
      }
      map.remove()
      setMapLoaded(false)
    }
  }, [isDark, landmarkLabel, mapFailed, removeActiveVehiclePopup])

  useEffect(() => {
    const map = mapInstance.current
    if (!mapLoaded || styleGeneration === 0 || !isMapStyleReady(map, styleReadyMap.current)) {
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
          properties: { freshness: vehicle.freshness, mode: vehicle.mode, vehicleId: vehicle.id },
          type: "Feature",
        })),
        type: "FeatureCollection",
      }
      const removeClusterLayers = addVehicleClusterLayers(map, vehicleData, onSelectVehicle)
      return () => {
        if (mapInstance.current === map) removeClusterLayers()
      }
    }
    markerInstances.current = vehicles.map((vehicle) =>
      addVehicleMapMarker(map, {
        ariaLabel: vehicleAriaLabel(vehicle),
        onSelect: onSelectVehicle,
        selected: vehicle.id === selectedVehicleId,
        vehicle,
      }),
    )
  }, [mapLoaded, onSelectVehicle, selectedVehicleId, styleGeneration, vehicles])

  useEffect(() => {
    const map = mapInstance.current
    if (!mapLoaded || styleGeneration === 0 || !isMapStyleReady(map, styleReadyMap.current)) {
      return
    }
    if (routeData.features.length === 0) {
      removeRouteLayers(map)
      return
    }
    addOrUpdateRouteLayers(map, routeData, routeColour)
    if (tripTarget && focusedTripId.current !== tripTarget.id) {
      focusedTripId.current = tripTarget.id
      focusRoute(map, routeData)
    }
  }, [mapLoaded, routeColour, routeData, styleGeneration, tripTarget])

  useEffect(() => {
    const map = mapInstance.current
    if (
      !mapLoaded ||
      mapGeneration === 0 ||
      !isMapStyleReady(map, styleReadyMap.current) ||
      !selectedVehicle
    ) {
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
  }, [focus?.revision, mapGeneration, mapLoaded, selectedVehicle])

  useEffect(() => {
    const map = mapInstance.current
    removeActiveVehiclePopup()
    if (
      !mapLoaded ||
      mapGeneration === 0 ||
      styleGeneration === 0 ||
      !isMapStyleReady(map, styleReadyMap.current) ||
      !selectedVehicle
    ) {
      return undefined
    }

    const popupKey = `${selectedVehicle.id}:${focus?.revision ?? 0}`
    activeVehiclePopupKey.current = popupKey
    activeVehiclePopup.current = addVehicleMapPopup(map, selectedVehicle, () => {
      if (activeVehiclePopupKey.current === popupKey) {
        activeVehiclePopup.current = null
        activeVehiclePopupKey.current = ""
      }
    })
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        removeActiveVehiclePopup()
      }
    }
    window.addEventListener("keydown", onKeyDown)

    return () => {
      window.removeEventListener("keydown", onKeyDown)
      if (activeVehiclePopupKey.current === popupKey) {
        removeActiveVehiclePopup()
      }
    }
  }, [
    focus?.revision,
    mapGeneration,
    mapLoaded,
    removeActiveVehiclePopup,
    selectedVehicle,
    styleGeneration,
  ])

  return (
    <section aria-label={landmarkLabel} className="min-w-0 space-y-3">
      <div className="flex items-baseline justify-between gap-4">
        <div>
          <p className="font-mono text-xs font-semibold tracking-wide text-muted-foreground uppercase">
            {eyebrow}
          </p>
          <h2 className="mt-1 text-xl font-semibold">{heading}</h2>
        </div>
        <MapTrifold aria-hidden="true" className="text-primary" size={26} weight="duotone" />
      </div>
      {canRenderMap ? (
        <>
          <div
            className="h-[28rem] w-full overflow-hidden rounded-sm border border-border md:h-[34rem] xl:h-[34rem] xl:min-h-[34rem] xl:max-h-[38rem]"
            ref={mapElement}
          />
          {afterMapCanvas}
          <MapStatus
            geometry={tripQuery.data?.geometry}
            hasTripTarget={tripTarget !== undefined}
            routeId={tripQuery.data?.route_id}
            selectedJourney={focusedJourney}
            selectedVehicle={selectedVehicle}
            tripQueryState={tripQuery.status}
          />
          <p className="text-sm text-muted-foreground">
            Map data © MapTiler © OpenStreetMap contributors. Route source and quality are stated
            above; timetable details are not live arrival predictions.
          </p>
        </>
      ) : (
        <>
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
          {afterMapCanvas}
        </>
      )}
      {showVehicleControls && vehicles.length > 0 ? (
        <VehicleControls
          landmarkLabel={landmarkLabel}
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
  geometry,
  hasTripTarget,
  routeId,
  selectedJourney,
  selectedVehicle,
  tripQueryState,
}: {
  readonly geometry: TripDetail["geometry"] | undefined
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
  if (geometry?.quality === "official_shape") {
    return (
      <p className="text-sm text-muted-foreground">
        <span className="font-medium text-foreground">Official GTFS alignment.</span> Shape{" "}
        {geometry.shape_id} from static version {geometry.source_version}.
      </p>
    )
  }
  if (geometry?.quality === "matched_infrastructure") {
    return (
      <p className="text-sm text-muted-foreground">
        <span className="font-medium text-foreground">Infrastructure-matched alignment.</span>{" "}
        {geometry.attribution}
      </p>
    )
  }
  if (geometry?.quality === "stop_sequence") {
    return (
      <p className="text-sm text-[color:var(--status-warning-foreground)]">
        <span className="font-medium">Approximate alignment.</span> The dashed line joins scheduled
        stops and does not claim to follow rail or road infrastructure.
      </p>
    )
  }
  if (geometry?.quality === "unavailable") {
    return (
      <p className="text-sm text-[color:var(--status-warning-foreground)]">
        <span className="font-medium">Route alignment unavailable.</span> Scheduled stops remain
        visible when coordinates are available.
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
  readonly landmarkLabel: string
  readonly nextStop: NextScheduledStop | undefined
  readonly nextStopUnavailableReason: string | undefined
  readonly onSelect: (vehicleId: string) => void
  readonly selectedVehicle: ValidatedVehicle | undefined
  readonly selectedVehicleId: string
  readonly vehicles: readonly ValidatedVehicle[]
}

function VehicleControls({
  landmarkLabel,
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
      aria-label={`${landmarkLabel} vehicle locations`}
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
    id: stop.stop_id,
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

function addOrUpdateRouteLayers(
  map: maplibregl.Map,
  routeData: MapRouteData,
  gtfsRouteColour: string | undefined,
) {
  const actionColour = cssToken("--action-primary")
  const stopColour = cssToken("--status-live")
  const stopStrokeColour = cssToken("--surface-primary")
  const routeCasingColour = cssToken("--text-primary")
  if (!actionColour || !routeCasingColour || !stopColour || !stopStrokeColour) {
    return
  }
  const routeQuality = routeData.features.find((feature) => feature.geometry.type === "LineString")
    ?.properties.quality
  const routePresentation = routePresentationFor(routeQuality ?? "unavailable")
  const routeColour = routeColourFor(gtfsRouteColour, actionColour)
  const routeCasingOpacity = routeColourContrastFor(routeColour).requiresCasingSupport
    ? 1
    : routePresentation.casingOpacity

  removeRouteLayers(map)
  map.addSource(routeSourceId, { data: routeData, type: "geojson" })
  if (routePresentation.shouldRenderLine && routePresentation.isApproximate) {
    map.addLayer({
      filter: ["==", ["get", "featureKind"], "route"],
      id: routeApproximateCasingLayerId,
      layout: { "line-cap": "round", "line-join": "round" },
      paint: {
        "line-color": routeCasingColour,
        "line-dasharray": [2, 2],
        "line-opacity": routeCasingOpacity,
        "line-width": ["interpolate", ["linear"], ["zoom"], 7, 5, 11, 8, 15, 12],
      },
      source: routeSourceId,
      type: "line",
    })
    map.addLayer({
      filter: ["==", ["get", "featureKind"], "route"],
      id: routeApproximateLayerId,
      layout: { "line-cap": "round", "line-join": "round" },
      paint: {
        "line-color": routeColour,
        "line-dasharray": [2, 2],
        "line-width": ["interpolate", ["linear"], ["zoom"], 7, 2.5, 11, 4, 15, 6],
      },
      source: routeSourceId,
      type: "line",
    })
  } else if (routePresentation.shouldRenderLine) {
    map.addLayer({
      filter: ["==", ["get", "featureKind"], "route"],
      id: routeOfficialCasingLayerId,
      layout: { "line-cap": "round", "line-join": "round" },
      paint: {
        "line-color": routeCasingColour,
        "line-opacity": routeCasingOpacity,
        "line-width": ["interpolate", ["linear"], ["zoom"], 7, 5, 11, 8, 15, 12],
      },
      source: routeSourceId,
      type: "line",
    })
    map.addLayer({
      filter: ["==", ["get", "featureKind"], "route"],
      id: routeOfficialLayerId,
      layout: { "line-cap": "round", "line-join": "round" },
      paint: {
        "line-color": routeColour,
        "line-width": ["interpolate", ["linear"], ["zoom"], 7, 2.5, 11, 4, 15, 6],
      },
      source: routeSourceId,
      type: "line",
    })
  }
  map.addLayer({
    filter: [
      "all",
      ["==", ["get", "featureKind"], "stop"],
      ["==", ["get", "stopKind"], "ordinary"],
    ],
    id: routeStopLayerId,
    paint: {
      "circle-color": stopColour,
      "circle-radius": ["interpolate", ["linear"], ["zoom"], 9, 3, 14, 5],
      "circle-stroke-color": stopStrokeColour,
      "circle-stroke-width": 1.25,
    },
    source: routeSourceId,
    type: "circle",
  })
  map.addLayer({
    filter: [
      "all",
      ["==", ["get", "featureKind"], "stop"],
      ["==", ["get", "stopKind"], "terminus"],
    ],
    id: routeTerminusLayerId,
    paint: {
      "circle-color": stopStrokeColour,
      "circle-radius": ["interpolate", ["linear"], ["zoom"], 9, 5, 14, 7],
      "circle-stroke-color": stopColour,
      "circle-stroke-width": 2.25,
    },
    source: routeSourceId,
    type: "circle",
  })
  map.addLayer({
    filter: ["all", ["==", ["get", "featureKind"], "stop"], ["==", ["get", "isSelected"], true]],
    id: routeSelectedStopLayerId,
    paint: {
      "circle-color": stopStrokeColour,
      "circle-radius": ["interpolate", ["linear"], ["zoom"], 9, 7, 14, 10],
      "circle-stroke-color": actionColour,
      "circle-stroke-width": 3,
    },
    source: routeSourceId,
    type: "circle",
  })
  if (routeQuality === "official_shape") {
    map.addLayer({
      filter: ["==", ["get", "featureKind"], "route"],
      id: routeLabelLayerId,
      layout: {
        "symbol-placement": "line",
        "symbol-spacing": 500,
        "text-allow-overlap": false,
        "text-field": ["get", "routeLabel"],
        "text-keep-upright": true,
        "text-max-angle": 30,
        "text-padding": 4,
        "text-size": ["interpolate", ["linear"], ["zoom"], 11, 11, 14, 13],
      },
      minzoom: 11,
      paint: {
        "text-color": routeCasingColour,
        "text-halo-color": stopStrokeColour,
        "text-halo-width": 1.25,
      },
      source: routeSourceId,
      type: "symbol",
    })
  }
  map.addLayer({
    filter: ["==", ["get", "featureKind"], "stop"],
    id: routeStopLabelLayerId,
    layout: {
      "text-allow-overlap": false,
      "text-field": ["get", "stopName"],
      "text-offset": [0, 1.1],
      "text-padding": 4,
      "text-size": ["interpolate", ["linear"], ["zoom"], 14, 11, 16, 12],
      "text-variable-anchor": ["top", "bottom", "left", "right"],
    },
    minzoom: 14,
    paint: {
      "text-color": routeCasingColour,
      "text-halo-color": stopStrokeColour,
      "text-halo-width": 1,
    },
    source: routeSourceId,
    type: "symbol",
  })
}

function removeRouteLayers(map: maplibregl.Map) {
  if (map.getLayer(routeStopLabelLayerId)) {
    map.removeLayer(routeStopLabelLayerId)
  }
  if (map.getLayer(routeLabelLayerId)) {
    map.removeLayer(routeLabelLayerId)
  }
  if (map.getLayer(routeTerminusLayerId)) {
    map.removeLayer(routeTerminusLayerId)
  }
  if (map.getLayer(routeSelectedStopLayerId)) {
    map.removeLayer(routeSelectedStopLayerId)
  }
  if (map.getLayer(routeStopLayerId)) {
    map.removeLayer(routeStopLayerId)
  }
  if (map.getLayer(routeApproximateLayerId)) {
    map.removeLayer(routeApproximateLayerId)
  }
  if (map.getLayer(routeApproximateCasingLayerId)) {
    map.removeLayer(routeApproximateCasingLayerId)
  }
  if (map.getLayer(routeOfficialLayerId)) {
    map.removeLayer(routeOfficialLayerId)
  }
  if (map.getLayer(routeOfficialCasingLayerId)) {
    map.removeLayer(routeOfficialCasingLayerId)
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
  installVehicleMapSprites(map, {
    live: liveColour,
    stale: warningColour,
    surface: surfaceColour,
    text: textColour,
  })
  map.addSource(vehicleSourceId, {
    cluster: true,
    clusterMaxZoom: 12,
    clusterRadius: 48,
    clusterProperties: {
      live_count: ["+", ["case", ["==", ["get", "freshness"], "live"], 1, 0]],
    },
    data,
    type: "geojson",
  })
  map.addLayer({
    filter: ["has", "point_count"],
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
    filter: ["has", "point_count"],
    id: vehicleClusterCountLayerId,
    layout: { "text-field": ["get", "point_count_abbreviated"], "text-size": 12 },
    paint: { "text-color": textColour },
    source: vehicleSourceId,
    type: "symbol",
  })
  map.addLayer({
    filter: ["!", ["has", "point_count"]],
    id: vehiclePointLayerId,
    layout: {
      "icon-allow-overlap": true,
      "icon-image": ["concat", "vehicle-symbol-", ["get", "mode"], "-", ["get", "freshness"]],
      "icon-size": ["interpolate", ["linear"], ["zoom"], 9, 0.72, 14, 1],
    },
    source: vehicleSourceId,
    type: "symbol",
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
    feature.geometry.type === "Point"
      ? [feature.geometry.coordinates]
      : feature.geometry.coordinates,
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

function vehicleAriaLabel(vehicle: ValidatedVehicle): string {
  const state = vehicle.freshness === "live" ? "verified live" : "last verified position is stale"
  const mode =
    vehicle.mode === "unknown" ? "unclassified mode" : `${vehicle.mode.toUpperCase()} mode`
  return `${vehicle.label} from ${vehicle.feed}; ${mode}; ${state}; updated ${formatAge(vehicle.updatedAt)} ago.`
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

function applyCivicBasemapTuning(map: maplibregl.Map, theme: CivicMapTheme): void {
  for (const layer of map.getStyle().layers) {
    const sourceLayer =
      "source-layer" in layer && typeof layer["source-layer"] === "string"
        ? layer["source-layer"]
        : undefined
    const patch = civicBasemapPatch({ id: layer.id, sourceLayer, type: layer.type }, theme)
    if (patch?.kind === "visibility") {
      map.setLayoutProperty(layer.id, "visibility", patch.visibility)
    }
    if (patch?.kind === "fill-opacity") {
      map.setPaintProperty(layer.id, "fill-opacity", patch.opacity)
    }
    if (patch?.kind === "line-opacity") {
      map.setPaintProperty(layer.id, "line-opacity", patch.opacity)
    }
  }
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
  return mapMotionDuration(window.matchMedia("(prefers-reduced-motion: reduce)").matches)
}

function supportsWebGl(): boolean {
  const canvas = document.createElement("canvas")
  return Boolean(canvas.getContext("webgl2") ?? canvas.getContext("webgl"))
}
