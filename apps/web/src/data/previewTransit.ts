import type { TransitJourney } from "@/domain/transit"

const malaysiaDateFormatter = new Intl.DateTimeFormat("en-MY", {
  day: "2-digit",
  month: "short",
  timeZone: "Asia/Kuala_Lumpur",
  year: "numeric",
})

const malaysiaDatePartFormatter = new Intl.DateTimeFormat("en-CA", {
  day: "2-digit",
  month: "2-digit",
  timeZone: "Asia/Kuala_Lumpur",
  year: "numeric",
})

const today = new Date()
export const previewServiceDate = malaysiaDateFormatter.format(today)
export const previewServiceDateIso = toMalaysiaIsoDate(today)

function toMalaysiaIsoDate(date: Date): string {
  const parts = malaysiaDatePartFormatter.formatToParts(date)
  const valueFor = (type: Intl.DateTimeFormatPartTypes) => {
    const value = parts.find((part) => part.type === type)?.value
    if (!value) {
      throw new Error(`Missing ${type} in a Malaysia date formatter result.`)
    }
    return value
  }

  return `${valueFor("year")}-${valueFor("month")}-${valueFor("day")}`
}

export const previewJourneys = [
  {
    id: "rapid-rail-kl-mrt-kajang",
    agency: "Rapid Rail Kuala Lumpur",
    feedId: "rapid-rail-kl",
    mode: "mrt",
    routeLabel: "MRT Kajang",
    routeName: "Kajang Line",
    origin: "Sungai Buloh",
    destination: "Kajang",
    serviceDate: previewServiceDate,
    serviceDateIso: previewServiceDateIso,
    plannedStart: "07:14",
    plannedEnd: "08:31",
    stopCount: 31,
    freshness: "preview",
    sourceUpdatedAt: "Preview fixture — static import pending",
  },
  {
    id: "rapid-rail-kl-lrt-kelana-jaya",
    agency: "Rapid Rail Kuala Lumpur",
    feedId: "rapid-rail-kl",
    mode: "lrt",
    routeLabel: "LRT Kelana Jaya",
    routeName: "Kelana Jaya Line",
    origin: "Gombak",
    destination: "Putra Heights",
    serviceDate: previewServiceDate,
    serviceDateIso: previewServiceDateIso,
    plannedStart: "07:20",
    plannedEnd: "08:27",
    stopCount: 37,
    freshness: "preview",
    sourceUpdatedAt: "Preview fixture — static import pending",
  },
  {
    id: "rapid-bus-kl-t851",
    agency: "Rapid Bus Kuala Lumpur",
    feedId: "rapid-bus-kl",
    mode: "bus",
    routeLabel: "T851",
    routeName: "Taman Tun Dr Ismail",
    origin: "TTDI MRT",
    destination: "Bandar Utama",
    serviceDate: previewServiceDate,
    serviceDateIso: previewServiceDateIso,
    plannedStart: "07:25",
    plannedEnd: "07:51",
    stopCount: 15,
    freshness: "preview",
    sourceUpdatedAt: "Preview state — not an upstream reading",
  },
  {
    id: "ktmb-komuter-seremban",
    agency: "KTM Berhad",
    feedId: "ktmb",
    mode: "rail",
    routeLabel: "KTM Komuter",
    routeName: "Seremban Line",
    origin: "Batu Caves",
    destination: "Pulau Sebang / Tampin",
    serviceDate: previewServiceDate,
    serviceDateIso: previewServiceDateIso,
    plannedStart: "07:32",
    plannedEnd: "09:11",
    stopCount: 27,
    freshness: "preview",
    sourceUpdatedAt: "Preview state — not an upstream reading",
  },
] satisfies readonly TransitJourney[]
