import type { TripDetail } from "@/lib/transit-api"

export type RouteGeometryQuality = TripDetail["geometry"]["quality"]

interface MapRouteLineFeature {
  readonly geometry: { readonly coordinates: [number, number][]; readonly type: "LineString" }
  readonly properties: {
    readonly featureKind: "route"
    readonly quality: RouteGeometryQuality
    readonly routeLabel: string
  }
  readonly type: "Feature"
}

interface MapRouteStopFeature {
  readonly geometry: { readonly coordinates: [number, number]; readonly type: "Point" }
  readonly properties: {
    readonly featureKind: "stop"
    readonly isSelected: boolean
    readonly quality: RouteGeometryQuality
    readonly stopId: string
    readonly stopKind: "ordinary" | "terminus"
    readonly stopName: string
  }
  readonly type: "Feature"
}

export type MapRouteFeature = MapRouteLineFeature | MapRouteStopFeature

export interface MapRouteData {
  readonly features: readonly MapRouteFeature[]
  readonly type: "FeatureCollection"
}

interface RouteDataOptions {
  readonly selectedStopId?: string
}

export function routeDataFor(
  tripDetail: TripDetail | undefined,
  { selectedStopId }: RouteDataOptions = {},
): MapRouteData {
  if (!tripDetail) {
    return { features: [], type: "FeatureCollection" }
  }
  const quality = tripDetail.geometry.quality
  const firstSequence = tripDetail.stops.at(0)?.sequence
  const lastSequence = tripDetail.stops.at(-1)?.sequence
  const features: MapRouteFeature[] = tripDetail.stops.flatMap((stop) =>
    stop.latitude === null || stop.longitude === null
      ? []
      : [
          {
            geometry: { coordinates: [stop.longitude, stop.latitude], type: "Point" },
            properties: {
              featureKind: "stop",
              isSelected: stop.stop_id === selectedStopId,
              quality,
              stopId: stop.stop_id,
              stopKind:
                stop.sequence === firstSequence || stop.sequence === lastSequence
                  ? "terminus"
                  : "ordinary",
              stopName: stop.name,
            },
            type: "Feature" as const,
          },
        ],
  )
  if (tripDetail.geometry.coordinates) {
    features.unshift({
      geometry: { coordinates: tripDetail.geometry.coordinates, type: "LineString" },
      properties: {
        featureKind: "route",
        quality,
        routeLabel: tripDetail.route_id || tripDetail.headsign,
      },
      type: "Feature",
    })
  }
  return { features, type: "FeatureCollection" }
}
