export function shouldFallbackForMapError(hasLoaded: boolean): boolean {
  return !hasLoaded
}

export function isMapStyleReady<T extends object>(
  map: T | null,
  styleReadyMap: T | null,
): map is T {
  return map !== null && map === styleReadyMap
}
