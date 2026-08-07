import { describe, expect, it } from "vitest"

import { shouldFallbackForMapError } from "@/lib/map-runtime"

describe("shouldFallbackForMapError", () => {
  it("does not replace a map that already loaded after a non-fatal error", () => {
    expect(shouldFallbackForMapError(true)).toBe(false)
  })

  it("falls back when the style fails before the map loads", () => {
    expect(shouldFallbackForMapError(false)).toBe(true)
  })
})
