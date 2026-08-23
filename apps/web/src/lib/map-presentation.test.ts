import { describe, expect, it } from "vitest"

import {
  civicBasemapPatch,
  civicMapStyleUrl,
  mapMotionDuration,
  routeColourContrastFor,
  routeColourFor,
  routePresentationFor,
  vehicleBearingRotation,
} from "@/lib/map-presentation"

describe("Civic map presentation policy", () => {
  it("uses the low-saturation project recipe without hiding orientation cues", () => {
    expect(
      civicBasemapPatch({ id: "poi-label", sourceLayer: "poi", type: "symbol" }, "light"),
    ).toEqual({ kind: "visibility", visibility: "none" })
    expect(
      civicBasemapPatch({ id: "building", sourceLayer: "building", type: "fill" }, "dark"),
    ).toEqual({ kind: "fill-opacity", opacity: 0.13 })
    expect(
      civicBasemapPatch({ id: "railway", sourceLayer: "transportation", type: "line" }, "light"),
    ).toBeUndefined()
    expect(civicMapStyleUrl("dark", "restricted key")).toContain("streets-v2-dark")
  })

  it("keeps authoritative routes solid and schedule-derived alignment dashed", () => {
    expect(routePresentationFor("official_shape")).toMatchObject({
      isApproximate: false,
      shouldRenderLine: true,
    })
    expect(routePresentationFor("matched_infrastructure")).toMatchObject({
      isApproximate: false,
      shouldRenderLine: true,
    })
    expect(routePresentationFor("stop_sequence")).toMatchObject({
      isApproximate: true,
      shouldRenderLine: true,
    })
    expect(routePresentationFor("unavailable").shouldRenderLine).toBe(false)
  })

  it("accepts only hexadecimal GTFS route colours and keeps a Civic fallback", () => {
    expect(routeColourFor("#DC241F", "#075EA8")).toBe("#DC241F")
    expect(routeColourFor("purple", "#075EA8")).toBe("#075EA8")
  })

  it("forces neutral casing support when a valid route colour misses either Civic theme target", () => {
    expect(routeColourContrastFor("#777777").requiresCasingSupport).toBe(false)
    expect(routeColourContrastFor("#ffffff").requiresCasingSupport).toBe(true)
    expect(routeColourContrastFor("#000000").requiresCasingSupport).toBe(true)
  })

  it("rotates a vehicle only for a valid GTFS bearing", () => {
    expect(vehicleBearingRotation(90)).toBe(90)
    expect(vehicleBearingRotation(360)).toBe(0)
    expect(vehicleBearingRotation(-1)).toBeUndefined()
    expect(vehicleBearingRotation(null)).toBeUndefined()
    expect(vehicleBearingRotation(Number.NaN)).toBeUndefined()
  })

  it("removes map movement when reduced motion is requested", () => {
    expect(mapMotionDuration(false)).toBe(200)
    expect(mapMotionDuration(true)).toBe(0)
  })
})
