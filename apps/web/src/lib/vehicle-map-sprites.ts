import type maplibregl from "maplibre-gl"

import type { VehicleMapMode } from "@/domain/transit"

type VehicleFreshness = "live" | "stale"
export type VehicleSpriteShape =
  | "bus"
  | "mrt-subway"
  | "lrt-tram"
  | "monorail"
  | "regional-rail"
  | "unclassified"

interface VehicleSpriteColours {
  readonly live: string
  readonly stale: string
  readonly surface: string
  readonly text: string
}

const vehicleModes: readonly VehicleMapMode[] = ["bus", "lrt", "monorail", "mrt", "rail", "unknown"]
const freshnessStates: readonly VehicleFreshness[] = ["live", "stale"]
const vehicleSpriteShapes = {
  bus: "bus",
  lrt: "lrt-tram",
  monorail: "monorail",
  mrt: "mrt-subway",
  rail: "regional-rail",
  unknown: "unclassified",
} as const satisfies Readonly<Record<VehicleMapMode, VehicleSpriteShape>>

export function installVehicleMapSprites(map: maplibregl.Map, colours: VehicleSpriteColours): void {
  for (const mode of vehicleModes) {
    for (const freshness of freshnessStates) {
      const id = vehicleSpriteId(mode, freshness)
      if (map.hasImage(id)) {
        continue
      }
      const image = vehicleSpriteImage(mode, freshness, colours)
      if (image) {
        map.addImage(id, image, { pixelRatio: 2 })
      }
    }
  }
}

export function vehicleSpriteId(mode: VehicleMapMode, freshness: VehicleFreshness): string {
  return `vehicle-symbol-${mode}-${freshness}`
}

export function vehicleSpriteShapeForMode(mode: VehicleMapMode): VehicleSpriteShape {
  return vehicleSpriteShapes[mode]
}

function vehicleSpriteImage(
  mode: VehicleMapMode,
  freshness: VehicleFreshness,
  colours: VehicleSpriteColours,
): ImageData | undefined {
  const size = 32
  const canvas = document.createElement("canvas")
  canvas.height = size
  canvas.width = size
  const context = canvas.getContext("2d")
  if (!context) {
    return undefined
  }
  const stroke = freshness === "live" ? colours.live : colours.stale

  context.fillStyle = colours.surface
  context.lineCap = "round"
  context.lineJoin = "round"
  context.lineWidth = 2.5
  context.strokeStyle = stroke
  if (freshness === "stale") {
    context.setLineDash([3, 2])
  }
  context.translate(size / 2, size / 2)

  const shape = vehicleSpriteShapeForMode(mode)
  if (shape === "bus") {
    drawBus(context)
  } else if (shape === "mrt-subway") {
    drawMrtSubway(context)
  } else if (shape === "lrt-tram") {
    drawLrtTram(context)
  } else if (shape === "monorail") {
    drawMonorail(context)
  } else if (shape === "regional-rail") {
    drawRegionalRail(context)
  } else {
    drawUnclassified(context, colours.text)
  }

  return context.getImageData(0, 0, size, size)
}

function drawBus(context: CanvasRenderingContext2D): void {
  roundedRectangle(context, -8, -9, 16, 18, 3)
  context.fill()
  context.stroke()
  context.setLineDash([])
  context.beginPath()
  context.moveTo(-5, -3)
  context.lineTo(5, -3)
  context.moveTo(-5, 3)
  context.lineTo(5, 3)
  context.stroke()
  drawWheels(context)
}

function drawMrtSubway(context: CanvasRenderingContext2D): void {
  roundedRectangle(context, -9, -8, 18, 16, 4)
  context.fill()
  context.stroke()
  context.setLineDash([])
  context.beginPath()
  context.moveTo(-5, -3)
  context.lineTo(5, -3)
  context.moveTo(-5, 3)
  context.lineTo(5, 3)
  context.moveTo(0, 8)
  context.lineTo(0, 11)
  context.stroke()
}

function drawLrtTram(context: CanvasRenderingContext2D): void {
  roundedRectangle(context, -7, -10, 14, 20, 2)
  context.fill()
  context.stroke()
  context.setLineDash([])
  context.beginPath()
  context.moveTo(0, -14)
  context.lineTo(0, -10)
  context.moveTo(-4, -12)
  context.lineTo(4, -12)
  context.moveTo(-5, -4)
  context.lineTo(5, -4)
  context.moveTo(-5, 1)
  context.lineTo(5, 1)
  context.stroke()
  drawWheels(context)
}

function drawMonorail(context: CanvasRenderingContext2D): void {
  roundedRectangle(context, -10, -6, 20, 12, 6)
  context.fill()
  context.stroke()
  context.setLineDash([])
  context.beginPath()
  context.moveTo(-6, -1)
  context.lineTo(6, -1)
  context.moveTo(-9, 9)
  context.lineTo(9, 9)
  context.stroke()
}

function drawRegionalRail(context: CanvasRenderingContext2D): void {
  roundedRectangle(context, -8, -10, 16, 20, 4)
  context.fill()
  context.stroke()
  context.setLineDash([])
  context.beginPath()
  context.moveTo(-5, -4)
  context.lineTo(5, -4)
  context.moveTo(-5, 2)
  context.lineTo(5, 2)
  context.moveTo(0, -8)
  context.lineTo(0, 7)
  context.stroke()
  drawWheels(context)
}

function drawUnclassified(context: CanvasRenderingContext2D, textColour: string): void {
  context.beginPath()
  context.arc(0, 0, 9, 0, Math.PI * 2)
  context.fill()
  context.stroke()
  context.setLineDash([])
  context.fillStyle = textColour
  context.font = "600 14px IBM Plex Sans, sans-serif"
  context.textAlign = "center"
  context.textBaseline = "middle"
  context.fillText("?", 0, 1)
}

function drawWheels(context: CanvasRenderingContext2D): void {
  context.beginPath()
  context.arc(-5, 9, 1.6, 0, Math.PI * 2)
  context.arc(5, 9, 1.6, 0, Math.PI * 2)
  context.fill()
}

function roundedRectangle(
  context: CanvasRenderingContext2D,
  x: number,
  y: number,
  width: number,
  height: number,
  radius: number,
): void {
  context.beginPath()
  context.moveTo(x + radius, y)
  context.lineTo(x + width - radius, y)
  context.quadraticCurveTo(x + width, y, x + width, y + radius)
  context.lineTo(x + width, y + height - radius)
  context.quadraticCurveTo(x + width, y + height, x + width - radius, y + height)
  context.lineTo(x + radius, y + height)
  context.quadraticCurveTo(x, y + height, x, y + height - radius)
  context.lineTo(x, y + radius)
  context.quadraticCurveTo(x, y, x + radius, y)
  context.closePath()
}
