import {
  BusIcon,
  type Icon,
  QuestionIcon,
  SubwayIcon,
  TrainRegionalIcon,
  TrainSimpleIcon,
  TramIcon,
} from "@phosphor-icons/react"

import type { VehicleMapMode } from "@/domain/transit"

const vehicleModeIcons = {
  bus: BusIcon,
  lrt: TramIcon,
  monorail: TrainSimpleIcon,
  mrt: SubwayIcon,
  rail: TrainRegionalIcon,
  unknown: QuestionIcon,
} as const satisfies Readonly<Record<VehicleMapMode, Icon>>

const vehicleModeLabels = {
  bus: "Bus",
  lrt: "LRT",
  monorail: "Monorail",
  mrt: "MRT",
  rail: "Rail",
  unknown: "Unclassified",
} as const satisfies Readonly<Record<VehicleMapMode, string>>

export function vehicleIconForMode(mode: VehicleMapMode): Icon {
  return vehicleModeIcons[mode]
}

export function vehicleModeLabelFor(mode: VehicleMapMode): string {
  return vehicleModeLabels[mode]
}
