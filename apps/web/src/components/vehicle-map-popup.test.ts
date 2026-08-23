import { describe, expect, it } from "vitest"

import { vehiclePopupAnchorFor } from "@/components/vehicle-map-popup"

describe("vehicle popup placement", () => {
  it("places a vehicle in the map's upper half below its marker so the summary remains visible", () => {
    expect(vehiclePopupAnchorFor(45, 542)).toBe("top")
  })

  it("places a vehicle in the map's lower half above its marker", () => {
    expect(vehiclePopupAnchorFor(460, 542)).toBe("bottom")
  })
})
