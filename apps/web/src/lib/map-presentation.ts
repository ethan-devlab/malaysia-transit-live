import type { RouteGeometryQuality } from "@/lib/trip-route-data"

export type CivicMapTheme = "dark" | "light"

export interface CivicBasemapLayer {
  readonly id: string
  readonly sourceLayer: string | undefined
  readonly type: string
}

export type CivicBasemapPatch =
  | { readonly kind: "fill-opacity"; readonly opacity: number }
  | { readonly kind: "line-opacity"; readonly opacity: number }
  | { readonly kind: "visibility"; readonly visibility: "none" }

export interface RoutePresentation {
  readonly casingOpacity: number
  readonly isApproximate: boolean
  readonly shouldRenderLine: boolean
}

export interface RouteColourContrast {
  readonly darkRatio: number
  readonly lightRatio: number
  readonly requiresCasingSupport: boolean
}

const cssHexColour = /^#[0-9a-f]{6}$/iu
const civicDarkBasemap = "#101820"
const civicLightBasemap = "#f7f9fc"
const minimumRouteContrast = 3

export function civicMapStyleUrl(theme: CivicMapTheme, mapTilerKey: string): string {
  const styleName = theme === "dark" ? "streets-v2-dark" : "streets-v2"
  return `https://api.maptiler.com/maps/${styleName}/style.json?key=${encodeURIComponent(mapTilerKey)}`
}

export function civicBasemapPatch(
  layer: CivicBasemapLayer,
  theme: CivicMapTheme,
): CivicBasemapPatch | undefined {
  const layerName = `${layer.id} ${layer.sourceLayer ?? ""}`.toLocaleLowerCase("en-US")

  if (layer.type === "symbol" && /(?:poi|housenumber|address)/u.test(layerName)) {
    return { kind: "visibility", visibility: "none" }
  }
  if (layer.type === "fill" && /building/u.test(layerName)) {
    return { kind: "fill-opacity", opacity: theme === "dark" ? 0.13 : 0.1 }
  }
  if (
    layer.type === "line" &&
    /(?:minor|residential|service|street|path)/u.test(layerName) &&
    !/rail/u.test(layerName)
  ) {
    return { kind: "line-opacity", opacity: theme === "dark" ? 0.28 : 0.32 }
  }
  return undefined
}

export function routePresentationFor(quality: RouteGeometryQuality): RoutePresentation {
  if (quality === "stop_sequence") {
    return { casingOpacity: 0.72, isApproximate: true, shouldRenderLine: true }
  }
  if (quality === "unavailable") {
    return { casingOpacity: 0, isApproximate: false, shouldRenderLine: false }
  }
  return { casingOpacity: 0.82, isApproximate: false, shouldRenderLine: true }
}

export function routeColourFor(gtfsRouteColour: string | undefined, fallback: string): string {
  return gtfsRouteColour && cssHexColour.test(gtfsRouteColour) ? gtfsRouteColour : fallback
}

export function routeColourContrastFor(routeColour: string): RouteColourContrast {
  const routeLuminance = relativeLuminance(routeColour)
  const lightRatio = contrastRatio(routeLuminance, relativeLuminance(civicLightBasemap))
  const darkRatio = contrastRatio(routeLuminance, relativeLuminance(civicDarkBasemap))
  return {
    darkRatio,
    lightRatio,
    requiresCasingSupport: lightRatio < minimumRouteContrast || darkRatio < minimumRouteContrast,
  }
}

export function vehicleBearingRotation(bearing: number | null): number | undefined {
  if (!Number.isFinite(bearing) || bearing === null || bearing < 0 || bearing > 360) {
    return undefined
  }
  return bearing % 360
}

export function mapMotionDuration(reducedMotion: boolean): number {
  return reducedMotion ? 0 : 200
}

function contrastRatio(left: number, right: number): number {
  const lighter = Math.max(left, right)
  const darker = Math.min(left, right)
  return (lighter + 0.05) / (darker + 0.05)
}

function relativeLuminance(colour: string): number {
  const channels = hexChannels(colour)
  if (!channels) {
    return 0
  }
  const red = linearChannel(channels[0])
  const green = linearChannel(channels[1])
  const blue = linearChannel(channels[2])
  return 0.2126 * red + 0.7152 * green + 0.0722 * blue
}

function hexChannels(colour: string): readonly [number, number, number] | undefined {
  if (!cssHexColour.test(colour)) {
    return undefined
  }
  const red = Number.parseInt(colour.slice(1, 3), 16)
  const green = Number.parseInt(colour.slice(3, 5), 16)
  const blue = Number.parseInt(colour.slice(5, 7), 16)
  return [red, green, blue]
}

function linearChannel(channel: number): number {
  const value = channel / 255
  return value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4
}
