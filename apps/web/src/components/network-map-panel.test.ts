import { describe, expect, it } from "vitest"

import { isMapStyleReady, shouldFallbackForMapError } from "@/lib/map-runtime"

describe("map runtime", () => {
  it("does not replace a map that already loaded after a non-fatal error", () => {
    expect(shouldFallbackForMapError(true)).toBe(false)
  })

  it("falls back when the style fails before the map loads", () => {
    expect(shouldFallbackForMapError(false)).toBe(true)
  })

  it("does not use a previous map's style readiness during a theme replacement", () => {
    const previousMap = {}
    const replacementMap = {}

    expect(isMapStyleReady(previousMap, previousMap)).toBe(true)
    expect(isMapStyleReady(replacementMap, previousMap)).toBe(false)
    expect(isMapStyleReady(replacementMap, replacementMap)).toBe(true)
  })
})
