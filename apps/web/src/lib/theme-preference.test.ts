import { describe, expect, it } from "vitest"

import { parseThemePreference, resolveDarkMode, themePreferenceLabel } from "@/lib/theme-preference"

describe("colour scheme preference", () => {
  it("keeps each explicit user-selected scheme", () => {
    expect(parseThemePreference("light")).toBe("light")
    expect(parseThemePreference("dark")).toBe("dark")
    expect(parseThemePreference("system")).toBe("system")
  })

  it("falls back to system when local storage does not contain a supported scheme", () => {
    expect(parseThemePreference(null)).toBe("system")
    expect(parseThemePreference("violet")).toBe("system")
  })

  it("uses the current operating-system appearance only for the system option", () => {
    expect(resolveDarkMode("system", true)).toBe(true)
    expect(resolveDarkMode("system", false)).toBe(false)
    expect(resolveDarkMode("light", true)).toBe(false)
    expect(resolveDarkMode("dark", false)).toBe(true)
    expect(themePreferenceLabel("system")).toBe("System")
  })
})
