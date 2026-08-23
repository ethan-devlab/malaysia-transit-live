import { describe, expect, it } from "vitest"

import { parseTripDetail } from "@/lib/transit-api"
import { routeDataFor } from "@/lib/trip-route-data"

const stops = [
  {
    sequence: 0,
    stop_id: "S1",
    name: "One",
    latitude: 3.1,
    longitude: 101.6,
    arrival_time: "08:00:00",
    departure_time: "08:00:00",
  },
  {
    sequence: 1,
    stop_id: "S2",
    name: "Two",
    latitude: 3.2,
    longitude: 101.7,
    arrival_time: "08:10:00",
    departure_time: "08:10:00",
  },
]

function tripPayload(geometry: unknown, routeColor = "DC241F") {
  return {
    trip_id: "T1",
    route_id: "R1",
    headsign: "Central",
    service_date: "2026-08-07",
    is_scheduled: true,
    route_color: routeColor,
    route_text_color: "FFFFFF",
    geometry,
    stops,
    source: {
      feed: "rapid-rail-kl",
      freshness: "scheduled_only",
      last_successful_fetch_at: null,
      static_version_id: "version-1",
    },
  }
}

describe("trip route geometry", () => {
  it("uses official server coordinates for the solid route feature", () => {
    const trip = parseTripDetail(
      tripPayload({
        type: "LineString",
        coordinates: [
          [101.6, 3.1],
          [101.62, 3.16],
          [101.7, 3.2],
        ],
        quality: "official_shape",
        shape_id: "shape-a",
        source: "gtfs",
        source_version: "version-1",
        attribution: null,
      }),
    )

    const routeData = routeDataFor(trip)

    expect(routeData.features[0]).toMatchObject({
      geometry: {
        coordinates: [
          [101.6, 3.1],
          [101.62, 3.16],
          [101.7, 3.2],
        ],
        type: "LineString",
      },
      properties: { featureKind: "route", quality: "official_shape" },
    })
    expect(routeData.features.filter((feature) => feature.geometry.type === "Point")).toHaveLength(
      2,
    )
    expect(
      routeData.features.filter(
        (feature) =>
          feature.properties.featureKind === "stop" && feature.properties.stopKind === "terminus",
      ),
    ).toHaveLength(2)
  })

  it("preserves approximate quality for dashed styling", () => {
    const trip = parseTripDetail(
      tripPayload({
        type: "LineString",
        coordinates: [
          [101.6, 3.1],
          [101.7, 3.2],
        ],
        quality: "stop_sequence",
        shape_id: null,
        source: "scheduled_stops",
        source_version: "version-1",
        attribution: null,
      }),
    )

    expect(routeDataFor(trip).features[0]?.properties.quality).toBe("stop_sequence")
  })

  it("keeps scheduled stops when geometry is unavailable", () => {
    const trip = parseTripDetail(
      tripPayload({
        type: "LineString",
        coordinates: null,
        quality: "unavailable",
        shape_id: null,
        source: "none",
        source_version: "version-1",
        attribution: null,
      }),
    )

    const routeData = routeDataFor(trip)

    expect(routeData.features).toHaveLength(2)
    expect(routeData.features.every((feature) => feature.geometry.type === "Point")).toBe(true)
  })

  it("marks only the requested static scheduled stop as selected without inventing an interchange", () => {
    const trip = parseTripDetail(
      tripPayload({
        type: "LineString",
        coordinates: [
          [101.6, 3.1],
          [101.7, 3.2],
        ],
        quality: "official_shape",
        shape_id: "shape-a",
        source: "gtfs",
        source_version: "version-1",
        attribution: null,
      }),
    )

    const stops = routeDataFor(trip, { selectedStopId: "S2" }).features.filter(
      (feature) => feature.properties.featureKind === "stop",
    )

    expect(stops).toEqual(
      expect.arrayContaining([
        expect.objectContaining({
          properties: expect.objectContaining({
            isSelected: true,
            stopId: "S2",
            stopKind: "terminus",
          }),
        }),
        expect.objectContaining({
          properties: expect.objectContaining({
            isSelected: false,
            stopId: "S1",
          }),
        }),
      ]),
    )
    expect(stops.some((feature) => "isVerifiedInterchange" in feature.properties)).toBe(false)
  })

  it("accepts attributed infrastructure geometry and rejects malformed contracts", () => {
    expect(() =>
      parseTripDetail(
        tripPayload({
          type: "LineString",
          coordinates: [
            [101.6, 3.1],
            [101.7, 3.2],
          ],
          quality: "matched_infrastructure",
          shape_id: null,
          source: "derived_infrastructure",
          source_version: "graph-1",
          attribution: "OpenStreetMap contributors",
        }),
      ),
    ).not.toThrow()
    expect(() =>
      parseTripDetail(
        tripPayload({
          type: "LineString",
          coordinates: [
            [3.1, 101.6],
            [3.2, 101.7],
          ],
          quality: "official_shape",
          shape_id: "shape-a",
          source: "gtfs",
          source_version: "version-1",
          attribution: null,
        }),
      ),
    ).toThrow()
    expect(() =>
      parseTripDetail(
        tripPayload(
          {
            type: "LineString",
            coordinates: null,
            quality: "unavailable",
            shape_id: null,
            source: "none",
            source_version: "version-1",
            attribution: null,
          },
          "purple",
        ),
      ),
    ).toThrow()
  })
})
