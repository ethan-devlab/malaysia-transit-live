import {
  BusIcon,
  QuestionIcon,
  SubwayIcon,
  TrainRegionalIcon,
  TrainSimpleIcon,
  TramIcon,
} from "@phosphor-icons/react"
import { describe, expect, it } from "vitest"

import { vehicleIconForMode, vehicleModeLabelFor } from "@/components/vehicle-mode-icon"
import { vehiclePopupSummaryFor } from "@/components/vehicle-popup-summary"
import type { VehicleMapMode } from "@/domain/transit"
import type { ValidatedVehicle } from "@/hooks/use-transit-board"
import { vehicleSpriteId, vehicleSpriteShapeForMode } from "@/lib/vehicle-map-sprites"

const modes: readonly VehicleMapMode[] = ["bus", "mrt", "lrt", "monorail", "rail", "unknown"]

const vehicle = {
  bearing: 90,
  feed: "rapid-kl",
  freshness: "live",
  id: "rapid-kl:V42",
  label: "Vehicle V42",
  latitude: 3.139,
  longitude: 101.6869,
  mode: "mrt",
  routeId: "MRT-KG",
  tripId: "very-long-scheduled-trip-id",
  updatedAt: "2026-08-10T08:20:00Z",
} satisfies ValidatedVehicle

describe("vehicle map presentation", () => {
  it("gives every normalized mode an explicit DOM icon and canvas sprite identity", () => {
    expect(vehicleIconForMode("bus")).toBe(BusIcon)
    expect(vehicleIconForMode("mrt")).toBe(SubwayIcon)
    expect(vehicleIconForMode("lrt")).toBe(TramIcon)
    expect(vehicleIconForMode("monorail")).toBe(TrainSimpleIcon)
    expect(vehicleIconForMode("rail")).toBe(TrainRegionalIcon)
    expect(vehicleIconForMode("unknown")).toBe(QuestionIcon)
    expect(new Set(modes.map(vehicleIconForMode)).size).toBe(modes.length)
    expect(new Set(modes.map(vehicleSpriteShapeForMode)).size).toBe(modes.length)
    expect(new Set(modes.map((mode) => vehicleSpriteId(mode, "live"))).size).toBe(modes.length)
  })

  it("builds a position-only popup summary without the full selected-vehicle detail", () => {
    expect(vehicleModeLabelFor("mrt")).toBe("MRT")
    expect(vehiclePopupSummaryFor(vehicle)).toEqual({
      feed: "rapid-kl",
      freshnessLabel: "Verified live",
      modeLabel: "MRT",
      positionUpdatedAt: expect.stringMatching(/^10 Aug 2026/u),
      routeTrip: "MRT-KG / very-long-scheduled-trip-id",
      vehicleLabel: "Vehicle V42",
    })
  })
})
