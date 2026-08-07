import type { TripDetail } from "@/lib/transit-api"

export type RouteGeometryQuality = TripDetail["geometry"]["quality"]

export interface MapRouteFeature {
  readonly geometry:
    | { readonly coordinates: [number, number]; readonly type: "Point" }
    | { readonly coordinates: [number, number][]; readonly type: "LineString" }
  readonly properties: {
    readonly featureKind: "route" | "stop"
    readonly quality: RouteGeometryQuality
  }
  readonly type: "Feature"
}

export interface MapRouteData {
  readonly features: readonly MapRouteFeature[]
  readonly type: "FeatureCollection"
}

export function routeDataFor(tripDetail: TripDetail | undefined): MapRouteData {
  if (!tripDetail) {
    return { features: [], type: "FeatureCollection" }
  }
  const quality = tripDetail.geometry.quality
  const features: MapRouteFeature[] = tripDetail.stops.flatMap((stop) =>
    stop.latitude === null || stop.longitude === null
      ? []
      : [
          {
            geometry: { coordinates: [stop.longitude, stop.latitude], type: "Point" },
            properties: { featureKind: "stop", quality },
            type: "Feature" as const,
          },
        ],
  )
  if (tripDetail.geometry.coordinates) {
    features.unshift({
      geometry: { coordinates: tripDetail.geometry.coordinates, type: "LineString" },
      properties: { featureKind: "route", quality },
      type: "Feature",
    })
  }
  return { features, type: "FeatureCollection" }
}
