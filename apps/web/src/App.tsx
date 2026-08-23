import { CalendarBlank, Crosshair, MagnifyingGlass, Train } from "@phosphor-icons/react"
import { useQuery } from "@tanstack/react-query"
import { useEffect, useMemo, useRef, useState } from "react"
import { DashboardWorkspace } from "@/components/dashboard-workspace"
import { DataAvailabilityNotice } from "@/components/data-availability-notice"
import { JourneyCard } from "@/components/journey-card"
import { NetworkMapPanel } from "@/components/network-map-panel"
import { NetworkSearchResults } from "@/components/network-search-results"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Skeleton } from "@/components/ui/skeleton"
import {
  journeyMatchesSearch,
  modeLabels,
  type NetworkFocus,
  type TransitMode,
} from "@/domain/transit"
import { toTransitJourney, toValidatedVehicle, useTransitBoard } from "@/hooks/use-transit-board"
import {
  parseThemePreference,
  resolveDarkMode,
  type ThemePreference,
  themePreferenceLabel,
  themePreferences,
} from "@/lib/theme-preference"
import { fetchNetworkSearch } from "@/lib/transit-api"

type ModeFilter = "all" | TransitMode

const favouriteStorageKey = "malaysia-transit-live:favourites"
const themeStorageKey = "malaysia-transit-live:theme"
const defaultServiceShortlistSize = 4

const modeFilters: readonly { readonly id: ModeFilter; readonly label: string }[] = [
  { id: "all", label: "All services" },
  { id: "mrt", label: "MRT" },
  { id: "lrt", label: "LRT" },
  { id: "monorail", label: "Monorail" },
  { id: "bus", label: "Bus" },
  { id: "rail", label: "Rail" },
]

function readFavourites(): readonly string[] {
  try {
    const storedValue = window.localStorage.getItem(favouriteStorageKey)
    if (!storedValue) {
      return []
    }

    const parsedValue: unknown = JSON.parse(storedValue)
    if (!Array.isArray(parsedValue)) {
      return []
    }

    return parsedValue.filter((value): value is string => typeof value === "string")
  } catch {
    return []
  }
}

function readThemePreference(): ThemePreference {
  try {
    return parseThemePreference(window.localStorage.getItem(themeStorageKey))
  } catch {
    return "system"
  }
}

function hasDashboardUrlState(): boolean {
  const parameters = new URLSearchParams(window.location.search)
  return ["view", "mode", "operator", "region"].some((name) => parameters.has(name))
}

export default function App() {
  const searchInput = useRef<HTMLInputElement>(null)
  const [searchQuery, setSearchQuery] = useState("")
  const [modeFilter, setModeFilter] = useState<ModeFilter>("all")
  const [selectedJourneyId, setSelectedJourneyId] = useState("")
  const [showAllServices, setShowAllServices] = useState(false)
  const [networkFocus, setNetworkFocus] = useState<NetworkFocus>()
  const [networkMonitorOpen, setNetworkMonitorOpen] = useState(hasDashboardUrlState)
  const [favouriteIds, setFavouriteIds] = useState<readonly string[]>(readFavourites)
  const [themePreference, setThemePreference] = useState<ThemePreference>(readThemePreference)
  const [systemIsDark, setSystemIsDark] = useState(
    () => window.matchMedia("(prefers-color-scheme: dark)").matches,
  )
  const board = useTransitBoard()

  const isDark = resolveDarkMode(themePreference, systemIsDark)
  const normalizedSearchQuery = searchQuery.trim()
  const shouldSearchNetwork = normalizedSearchQuery.length >= 2 && board.state === "ready"
  const networkSearch = useQuery({
    enabled: shouldSearchNetwork,
    queryFn: ({ signal }) => fetchNetworkSearch(normalizedSearchQuery, signal),
    queryKey: ["network-search", normalizedSearchQuery],
    staleTime: 15_000,
  })
  const searchedVehicles = useMemo(
    () => (networkSearch.data?.vehicles ?? []).map(toValidatedVehicle),
    [networkSearch.data],
  )
  const mapVehicles = useMemo(() => {
    const vehiclesById = new Map(board.vehicles.map((vehicle) => [vehicle.id, vehicle]))
    searchedVehicles.forEach((vehicle) => {
      vehiclesById.set(vehicle.id, vehicle)
    })
    return [...vehiclesById.values()]
  }, [board.vehicles, searchedVehicles])
  const vehicleByTrip = useMemo(
    () =>
      new Map(
        mapVehicles
          .filter((vehicle) => vehicle.tripId.length > 0)
          .map((vehicle) => [`${vehicle.feed}:${vehicle.tripId}`, vehicle]),
      ),
    [mapVehicles],
  )
  const searchedJourneys = useMemo(
    () =>
      (networkSearch.data?.journeys ?? []).map((journey) =>
        toTransitJourney(journey, vehicleByTrip),
      ),
    [networkSearch.data, vehicleByTrip],
  )
  const visibleJourneys = shouldSearchNetwork ? searchedJourneys : board.journeys
  const filteredJourneys = useMemo(
    () =>
      visibleJourneys.filter(
        (journey) =>
          (modeFilter === "all" || journey.mode === modeFilter) &&
          (shouldSearchNetwork || journeyMatchesSearch(journey, searchQuery)),
      ),
    [modeFilter, searchQuery, shouldSearchNetwork, visibleJourneys],
  )
  const knownJourneys = useMemo(() => {
    const journeysById = new Map(board.journeys.map((journey) => [journey.id, journey]))
    searchedJourneys.forEach((journey) => {
      journeysById.set(journey.id, journey)
    })
    return [...journeysById.values()]
  }, [board.journeys, searchedJourneys])
  const selectedJourney = knownJourneys.find((journey) => journey.id === selectedJourneyId)
  const serviceBoardJourneys = useMemo(() => {
    if (showAllServices || filteredJourneys.length <= defaultServiceShortlistSize) {
      return filteredJourneys
    }

    const shortlist = filteredJourneys.slice(0, defaultServiceShortlistSize)
    if (
      !selectedJourney ||
      !filteredJourneys.some((journey) => journey.id === selectedJourney.id) ||
      shortlist.some((journey) => journey.id === selectedJourney.id)
    ) {
      return shortlist
    }

    return [...shortlist.slice(0, -1), selectedJourney]
  }, [filteredJourneys, selectedJourney, showAllServices])
  const hasHiddenServices = serviceBoardJourneys.length < filteredJourneys.length
  const selectedMapVehicles = useMemo(() => {
    if (networkFocus?.kind === "vehicle") {
      return mapVehicles.filter((vehicle) => vehicle.id === networkFocus.id)
    }
    if (!selectedJourney) {
      return []
    }
    return mapVehicles.filter(
      (vehicle) => `${vehicle.feed}:${vehicle.tripId}` === selectedJourney.id,
    )
  }, [mapVehicles, networkFocus, selectedJourney])

  useEffect(() => {
    if (!selectedJourneyId || !knownJourneys.some((journey) => journey.id === selectedJourneyId)) {
      setSelectedJourneyId(knownJourneys.at(0)?.id ?? "")
    }
  }, [knownJourneys, selectedJourneyId])

  useEffect(() => {
    const mediaQuery = window.matchMedia("(prefers-color-scheme: dark)")
    const onSystemThemeChange = (event: MediaQueryListEvent) => {
      setSystemIsDark(event.matches)
    }

    mediaQuery.addEventListener("change", onSystemThemeChange)
    return () => mediaQuery.removeEventListener("change", onSystemThemeChange)
  }, [])

  useEffect(() => {
    const root = document.documentElement
    root.classList.toggle("dark", isDark)
    root.classList.toggle("light", !isDark)
    root.style.colorScheme = isDark ? "dark" : "light"
  }, [isDark])

  useEffect(() => {
    if (themePreference === "system") {
      window.localStorage.removeItem(themeStorageKey)
      return
    }

    window.localStorage.setItem(themeStorageKey, themePreference)
  }, [themePreference])

  useEffect(() => {
    const focusSearch = (event: KeyboardEvent) => {
      const target = event.target
      const isTypingField =
        target instanceof HTMLInputElement ||
        target instanceof HTMLTextAreaElement ||
        target instanceof HTMLSelectElement ||
        (target instanceof HTMLElement && target.isContentEditable)

      if (
        event.defaultPrevented ||
        event.key !== "/" ||
        event.altKey ||
        event.ctrlKey ||
        event.metaKey ||
        isTypingField
      ) {
        return
      }

      event.preventDefault()
      searchInput.current?.focus()
    }

    document.addEventListener("keydown", focusSearch)
    return () => document.removeEventListener("keydown", focusSearch)
  }, [])

  function toggleFavourite(journeyId: string) {
    setFavouriteIds((currentIds) => {
      const nextIds = currentIds.includes(journeyId)
        ? currentIds.filter((id) => id !== journeyId)
        : [...currentIds, journeyId]

      window.localStorage.setItem(favouriteStorageKey, JSON.stringify(nextIds))
      return nextIds
    })
  }

  function selectJourney(journeyId: string) {
    setSelectedJourneyId(journeyId)
    setNetworkFocus((currentFocus) => ({
      id: journeyId,
      kind: "journey",
      revision: (currentFocus?.revision ?? 0) + 1,
    }))
    focusSelectedService()
  }

  function selectVehicle(vehicleId: string) {
    const vehicle = mapVehicles.find((candidate) => candidate.id === vehicleId)
    if (vehicle?.tripId) {
      const journeyId = `${vehicle.feed}:${vehicle.tripId}`
      if (knownJourneys.some((journey) => journey.id === journeyId)) {
        setSelectedJourneyId(journeyId)
      }
    }
    setNetworkFocus((currentFocus) => ({
      id: vehicleId,
      kind: "vehicle",
      revision: (currentFocus?.revision ?? 0) + 1,
    }))
    focusSelectedService()
  }

  function focusSelectedService() {
    window.requestAnimationFrame(() => {
      document.getElementById("selected-service-context")?.scrollIntoView({
        behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth",
        block: "start",
      })
    })
  }

  return (
    <div className="flex min-h-screen flex-col bg-background text-foreground">
      <a
        className="sr-only left-4 top-4 z-50 bg-primary px-3 py-2 text-primary-foreground focus:not-sr-only focus:absolute"
        href="#main-content"
      >
        Skip to service board
      </a>
      <header className="border-b border-border bg-background">
        <div className="mx-auto flex min-h-18 max-w-7xl items-center justify-between gap-4 px-4 sm:px-6 lg:px-8">
          <div className="flex min-w-0 items-center gap-3">
            <div className="grid size-10 shrink-0 place-items-center bg-primary text-primary-foreground">
              <Train aria-hidden="true" size={24} weight="duotone" />
            </div>
            <div className="min-w-0">
              <p className="font-mono text-xs font-semibold tracking-wide text-muted-foreground uppercase">
                Public transport signal
              </p>
              <h1 className="truncate text-lg font-semibold">Malaysia Transit Live</h1>
            </div>
          </div>
          <label className="flex shrink-0 items-center gap-2 text-sm">
            <span className="hidden font-medium sm:inline">Theme</span>
            <select
              aria-label="Colour scheme"
              className="h-11 rounded-sm border border-border bg-background px-3 text-sm focus-visible:outline-3 focus-visible:outline-offset-2 focus-visible:outline-primary"
              onChange={(event) => setThemePreference(parseThemePreference(event.target.value))}
              value={themePreference}
            >
              {themePreferences.map((preference) => (
                <option key={preference} value={preference}>
                  {themePreferenceLabel(preference)}
                </option>
              ))}
            </select>
          </label>
        </div>
      </header>
      <main
        id="main-content"
        className="mx-auto w-full max-w-[90rem] flex-1 px-4 py-6 sm:px-6 sm:py-8 lg:px-8"
      >
        <DataAvailabilityNotice realtime={board.realtime} state={board.state} />
        <section aria-labelledby="trip-finder-heading" className="mt-6 border-b border-border pb-6">
          <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_auto] xl:items-end">
            <div>
              <p className="font-mono text-xs font-semibold tracking-wide text-primary uppercase">
                Journey finder
              </p>
              <h2 id="trip-finder-heading" className="mt-2 text-2xl font-semibold tracking-tight">
                Find a service before you travel.
              </h2>
              <p className="mt-2 max-w-2xl text-sm leading-6 text-muted-foreground">
                Search scheduled trips, stops, operators, and validated vehicle positions. Scheduled
                times and live locations remain clearly distinct.
              </p>
            </div>
            <dl className="grid grid-cols-2 gap-x-6 gap-y-3 font-mono text-xs text-muted-foreground">
              <div>
                <dt>Coverage</dt>
                <dd className="mt-1 font-sans text-sm font-medium text-foreground">Klang Valley</dd>
              </div>
              <div>
                <dt>Service date</dt>
                <dd className="mt-1 font-sans text-sm font-medium text-foreground">
                  {board.serviceDate}
                </dd>
              </div>
            </dl>
          </div>
          <div className="mt-5 grid gap-5 2xl:grid-cols-[minmax(0,1fr)_auto] 2xl:items-end">
            <div className="relative max-w-3xl">
              <div className="flex items-baseline justify-between gap-4">
                <label className="text-sm font-medium" htmlFor="network-search">
                  Route, station, trip, vehicle, or operator
                </label>
                <p className="font-mono text-xs text-muted-foreground">Press / to search</p>
              </div>
              <MagnifyingGlass
                aria-hidden="true"
                className="pointer-events-none absolute left-4 top-[3.4rem] -translate-y-1/2 text-muted-foreground"
                size={21}
              />
              <Input
                aria-describedby="network-search-help"
                className="mt-2 rounded-none border-x-0 border-t-0 border-b-2 bg-transparent pl-12 shadow-none focus-visible:ring-0"
                id="network-search"
                onChange={(event) => {
                  setSearchQuery(event.target.value)
                  setShowAllServices(false)
                }}
                placeholder="For example: KGL, Pasar Seni, or Rapid Rail"
                ref={searchInput}
                type="search"
                value={searchQuery}
              />
              <p id="network-search-help" className="mt-2 text-sm text-muted-foreground">
                Vehicle positions are not arrival predictions.
              </p>
            </div>
            <fieldset className="flex flex-wrap gap-2 xl:justify-end">
              <legend className="mb-2 text-sm font-medium">Filter by service mode</legend>
              {modeFilters.map((filter) => (
                <Button
                  aria-pressed={modeFilter === filter.id}
                  key={filter.id}
                  onClick={() => {
                    setModeFilter(filter.id)
                    setShowAllServices(false)
                  }}
                  type="button"
                  variant={modeFilter === filter.id ? "default" : "outline"}
                >
                  {filter.id === "all" ? filter.label : modeLabels[filter.id]}
                </Button>
              ))}
            </fieldset>
          </div>
          <NetworkSearchResults
            data={networkSearch.data}
            hasError={networkSearch.isError}
            isLoading={shouldSearchNetwork && networkSearch.isPending}
            onSelectJourney={(journey) => selectJourney(`${journey.feed}:${journey.trip_id}`)}
            onSelectVehicle={(vehicle) => selectVehicle(`${vehicle.feed}:${vehicle.vehicle_id}`)}
            query={searchQuery}
          />
        </section>

        <div className="mt-6 grid min-w-0 gap-6 xl:grid-cols-[minmax(0,0.9fr)_minmax(28rem,0.85fr)]">
          <section aria-labelledby="service-board-heading" className="min-w-0">
            <div className="flex flex-wrap items-end justify-between gap-3 border-b border-border pb-4">
              <div>
                <p className="font-mono text-xs font-semibold tracking-wide text-muted-foreground uppercase">
                  Service board
                </p>
                <h2 id="service-board-heading" className="mt-1 text-2xl font-semibold">
                  Choose a service
                </h2>
              </div>
              <p aria-live="polite" className="text-sm text-muted-foreground">
                Showing {serviceBoardJourneys.length} of {filteredJourneys.length} service
                {filteredJourneys.length === 1 ? "" : "s"}
              </p>
            </div>
            {board.state === "loading" ? (
              <div
                aria-busy="true"
                aria-label="Loading scheduled services"
                className="mt-5 grid gap-4 lg:grid-cols-2"
                role="status"
              >
                <Skeleton className="h-96 rounded-sm" />
                <Skeleton className="h-96 rounded-sm" />
              </div>
            ) : filteredJourneys.length > 0 ? (
              <div className="mt-5 grid gap-4 lg:grid-cols-2" id="service-board-list">
                {serviceBoardJourneys.map((journey) => (
                  <JourneyCard
                    isFavourite={favouriteIds.includes(journey.id)}
                    isSelected={journey.id === selectedJourneyId}
                    journey={journey}
                    key={journey.id}
                    onSelect={selectJourney}
                    onToggleFavourite={toggleFavourite}
                  />
                ))}
              </div>
            ) : (
              <div className="mt-5 border border-dashed border-border p-6" role="status">
                <p className="text-lg font-semibold">No matching service</p>
                <p className="mt-2 text-sm text-muted-foreground">
                  Try a route label, a station name, or remove a service-mode filter.
                </p>
              </div>
            )}
            {filteredJourneys.length > defaultServiceShortlistSize ? (
              <div className="mt-5 flex flex-wrap items-center justify-between gap-3 border-t border-border pt-4">
                <p className="text-sm text-muted-foreground">
                  {hasHiddenServices
                    ? "Choose a suggested service or load the complete matching list."
                    : "Showing the complete matching service list."}
                </p>
                <Button
                  aria-controls="service-board-list"
                  aria-expanded={showAllServices}
                  onClick={() => setShowAllServices((currentValue) => !currentValue)}
                  type="button"
                  variant="outline"
                >
                  {showAllServices
                    ? "Show fewer services"
                    : `Show all ${filteredJourneys.length} services`}
                </Button>
              </div>
            ) : null}
          </section>

          <aside
            aria-label="Selected service"
            className="min-w-0 space-y-5 xl:sticky xl:top-6 xl:self-start xl:border-l xl:border-border xl:pl-8"
            id="selected-service-context"
          >
            {selectedJourney &&
            filteredJourneys.some((journey) => journey.id === selectedJourney.id) ? (
              <>
                <section className="border-b border-border pb-5">
                  <p className="font-mono text-xs font-semibold tracking-wide text-muted-foreground uppercase">
                    Selected service
                  </p>
                  <h2 id="selected-service-heading" className="mt-1 text-xl font-semibold">
                    {selectedJourney.routeLabel} · {selectedJourney.routeName}
                  </h2>
                  <p className="mt-3 flex items-start gap-3 text-sm">
                    <Crosshair aria-hidden="true" className="mt-0.5 shrink-0 text-primary" />
                    <span>
                      {selectedJourney.origin} to {selectedJourney.destination}
                    </span>
                  </p>
                  <p className="mt-2 flex items-start gap-3 text-sm text-muted-foreground">
                    <CalendarBlank aria-hidden="true" className="mt-0.5 shrink-0 text-primary" />
                    <span>
                      <time dateTime={selectedJourney.serviceDateIso}>
                        {selectedJourney.serviceDate}
                      </time>{" "}
                      ·{" "}
                      <time
                        dateTime={`${selectedJourney.serviceDateIso}T${selectedJourney.plannedStart}:00+08:00`}
                      >
                        {selectedJourney.plannedStart}
                      </time>
                      –
                      <time
                        dateTime={`${selectedJourney.serviceDateIso}T${selectedJourney.plannedEnd}:00+08:00`}
                      >
                        {selectedJourney.plannedEnd}
                      </time>
                    </span>
                  </p>
                </section>
                <NetworkMapPanel
                  eyebrow="Selected service"
                  focus={networkFocus}
                  heading="Route map"
                  isDark={isDark}
                  landmarkLabel="Selected service map"
                  onSelectVehicle={selectVehicle}
                  selectedJourney={selectedJourney}
                  showVehicleControls
                  vehicles={selectedMapVehicles}
                />
              </>
            ) : (
              <section className="border border-dashed border-border bg-muted/20 p-5" role="status">
                <p className="font-medium">Select a scheduled service to view its route.</p>
                <p className="mt-2 text-sm text-muted-foreground">
                  The map will state whether the alignment is official, approximate, or unavailable.
                </p>
              </section>
            )}
          </aside>
        </div>

        <section
          aria-labelledby="network-monitor-heading"
          className="mt-12 border-t border-border pt-6"
        >
          <details
            className="group border-b border-border pb-6"
            onToggle={(event) => setNetworkMonitorOpen(event.currentTarget.open)}
            open={networkMonitorOpen}
          >
            <summary className="flex min-h-11 cursor-pointer list-none items-center justify-between gap-4 py-2 text-left focus-visible:outline-3 focus-visible:outline-offset-4 focus-visible:outline-[color:var(--focus-ring)]">
              <span>
                <span id="network-monitor-heading" className="block text-lg font-semibold">
                  All vehicle positions and source health
                </span>
                <span className="mt-1 block text-sm text-muted-foreground">
                  Optional network monitor for complete coverage, filters, and feed status.
                </span>
              </span>
              <span aria-hidden="true" className="font-mono text-xs text-primary uppercase">
                <span className="group-open:hidden">Open</span>
                <span className="hidden group-open:inline">Close</span>
              </span>
            </summary>
            {networkMonitorOpen ? (
              <div className="border-t border-border pt-6">
                <DashboardWorkspace isDark={isDark} />
              </div>
            ) : null}
          </details>
        </section>
      </main>
      <footer className="mt-10 border-t border-border bg-muted/35">
        <div className="mx-auto flex max-w-7xl flex-col gap-2 px-4 py-6 text-sm text-muted-foreground sm:px-6 lg:flex-row lg:items-center lg:justify-between lg:px-8">
          <p>Malaysia Transit Live · public-information service</p>
          <p className="font-mono text-xs">
            <a
              className="underline underline-offset-4 hover:text-foreground"
              href="https://developer.data.gov.my/realtime-api/gtfs-realtime"
              rel="noreferrer"
              target="_blank"
            >
              Malaysia Official Open API
            </a>{" "}
            · Local favourites stay in this browser.
          </p>
        </div>
      </footer>
    </div>
  )
}
