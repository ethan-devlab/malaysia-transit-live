export type ThemePreference = "dark" | "light" | "system"

export const themePreferences: readonly ThemePreference[] = ["system", "light", "dark"]

export function parseThemePreference(value: string | null | undefined): ThemePreference {
  return value === "dark" || value === "light" || value === "system" ? value : "system"
}

export function resolveDarkMode(preference: ThemePreference, systemIsDark: boolean): boolean {
  return preference === "system" ? systemIsDark : preference === "dark"
}

export function themePreferenceLabel(preference: ThemePreference): string {
  return preference === "system" ? "System" : preference === "light" ? "Light" : "Dark"
}
