import { CalendarBlank, Crosshair, MagnifyingGlass, Moon, Sun, Train } from "@phosphor-icons/react"
import { lazy, Suspense, useEffect, useMemo, useRef, useState } from "react"

import { DataAvailabilityNotice } from "@/components/data-availability-notice"
import { JourneyCard } from "@/components/journey-card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Skeleton } from "@/components/ui/skeleton"
import { journeyMatchesSearch, modeLabels, type TransitMode } from "@/domain/transit"
import { useTransitBoard } from "@/hooks/use-transit-board"

type ModeFilter = "all" | TransitMode
type ThemePreference = "dark" | "light" | "system"

const favouriteStorageKey = "malaysia-transit-live:favourites"
const themeStorageKey = "malaysia-transit-live:theme"

const NetworkMapPanel = lazy(async () => {
  const module = await import("@/components/network-map-panel")
  return { default: module.NetworkMapPanel }
})

const modeFilters: readonly { readonly id: ModeFilter; readonly label: string }[] = [
  { id: "all", label: "All services" },
  { id: "mrt", label: "MRT" },
  { id: "lrt", label: "LRT" },
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
    const storedValue = window.localStorage.getItem(themeStorageKey)
    if (storedValue === "dark" || storedValue === "light") {
      return storedValue
    }
  } catch {
    return "system"
  }

  return "system"
}

function resolveDarkMode(preference: ThemePreference, systemIsDark: boolean): boolean {
  return preference === "system" ? systemIsDark : preference === "dark"
}

export default function App() {
  const searchInput = useRef<HTMLInputElement>(null)
  const [searchQuery, setSearchQuery] = useState("")
  const [modeFilter, setModeFilter] = useState<ModeFilter>("all")
  const [showNetworkOnMobile, setShowNetworkOnMobile] = useState(false)
  const [selectedJourneyId, setSelectedJourneyId] = useState("")
  const [favouriteIds, setFavouriteIds] = useState<readonly string[]>(readFavourites)
  const [themePreference, setThemePreference] = useState<ThemePreference>(readThemePreference)
  const [systemIsDark, setSystemIsDark] = useState(
    () => window.matchMedia("(prefers-color-scheme: dark)").matches,
  )
  const board = useTransitBoard()

  const isDark = resolveDarkMode(themePreference, systemIsDark)
  const filteredJourneys = useMemo(
    () =>
      board.journeys.filter(
        (journey) =>
          (modeFilter === "all" || journey.mode === modeFilter) &&
          journeyMatchesSearch(journey, searchQuery),
      ),
    [board.journeys, modeFilter, searchQuery],
  )
  const selectedJourney = board.journeys.find((journey) => journey.id === selectedJourneyId)

  useEffect(() => {
    if (!selectedJourneyId || !board.journeys.some((journey) => journey.id === selectedJourneyId)) {
      setSelectedJourneyId(board.journeys.at(0)?.id ?? "")
    }
  }, [board.journeys, selectedJourneyId])

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

  function toggleTheme() {
    setThemePreference(isDark ? "light" : "dark")
  }

  return (
    <div className="min-h-screen bg-background text-foreground">
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
          <Button
            aria-label={isDark ? "Use light colour scheme" : "Use dark colour scheme"}
            onClick={toggleTheme}
            type="button"
            variant="ghost"
          >
            {isDark ? <Sun aria-hidden="true" /> : <Moon aria-hidden="true" />}
            <span className="hidden sm:inline">{isDark ? "Light" : "Dark"}</span>
          </Button>
        </div>
      </header>
      <main id="main-content" className="mx-auto max-w-7xl px-4 py-6 sm:px-6 sm:py-8 lg:px-8">
        <DataAvailabilityNotice state={board.state} />

        <section className="mt-8 grid gap-6 border-b border-border pb-8 lg:grid-cols-[minmax(0,1fr)_auto] lg:items-end">
          <div>
            <p className="font-mono text-xs font-semibold tracking-wide text-primary uppercase">
              KL / Klang Valley first · Malaysia-wide foundation
            </p>
            <h2 className="mt-3 max-w-3xl text-3xl font-semibold tracking-tight sm:text-4xl">
              Clear service information, without pretending uncertainty is live.
            </h2>
            <p className="mt-4 max-w-2xl text-base leading-7 text-muted-foreground">
              Search routes and stations, compare planned journeys, and read the source freshness
              before you travel.
            </p>
          </div>
          <dl className="grid grid-cols-2 gap-x-6 gap-y-2 border-l-2 border-primary pl-4 font-mono text-xs text-muted-foreground">
            <div>
              <dt>AREA</dt>
              <dd className="mt-1 font-sans text-sm font-medium text-foreground">KL priority</dd>
            </div>
            <div>
              <dt>SERVICE DATE</dt>
              <dd className="mt-1 font-sans text-sm font-medium text-foreground">
                {board.serviceDate}
              </dd>
            </div>
          </dl>
        </section>

        <section aria-labelledby="search-heading" className="mt-8">
          <div className="flex items-baseline justify-between gap-4">
            <div>
              <p className="font-mono text-xs font-semibold tracking-wide text-muted-foreground uppercase">
                Find a service
              </p>
              <h2 id="search-heading" className="mt-1 text-2xl font-semibold">
                Search the network
              </h2>
            </div>
            <p className="hidden font-mono text-xs text-muted-foreground sm:block">
              Press / to search
            </p>
          </div>
          <div className="relative mt-4 max-w-3xl">
            <MagnifyingGlass
              aria-hidden="true"
              className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-muted-foreground"
              size={21}
            />
            <label className="sr-only" htmlFor="network-search">
              Search route, station, or operator
            </label>
            <Input
              className="rounded-none border-x-0 border-t-0 border-b-2 bg-transparent pl-12 shadow-none focus-visible:ring-0"
              id="network-search"
              onChange={(event) => setSearchQuery(event.target.value)}
              placeholder="Route, station, or operator"
              ref={searchInput}
              type="search"
              value={searchQuery}
            />
          </div>
          <fieldset className="mt-4 flex flex-wrap gap-2">
            <legend className="sr-only">Filter services by mode</legend>
            {modeFilters.map((filter) => (
              <Button
                aria-pressed={modeFilter === filter.id}
                key={filter.id}
                onClick={() => setModeFilter(filter.id)}
                type="button"
                variant={modeFilter === filter.id ? "default" : "outline"}
              >
                {filter.id === "all" ? filter.label : modeLabels[filter.id]}
              </Button>
            ))}
          </fieldset>
        </section>

        <div className="mt-10 grid gap-10 xl:grid-cols-[minmax(0,1fr)_minmax(20rem,0.72fr)]">
          <section aria-labelledby="service-board-heading">
            <div className="flex flex-wrap items-end justify-between gap-3 border-b border-border pb-4">
              <div>
                <p className="font-mono text-xs font-semibold tracking-wide text-muted-foreground uppercase">
                  Service board
                </p>
                <h2 id="service-board-heading" className="mt-1 text-2xl font-semibold">
                  Planned and verified state
                </h2>
              </div>
              <p aria-live="polite" className="text-sm text-muted-foreground">
                {filteredJourneys.length} matching service{filteredJourneys.length === 1 ? "" : "s"}
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
              <div className="mt-5 grid gap-4 lg:grid-cols-2">
                {filteredJourneys.map((journey) => (
                  <JourneyCard
                    isFavourite={favouriteIds.includes(journey.id)}
                    isSelected={journey.id === selectedJourneyId}
                    journey={journey}
                    key={journey.id}
                    onSelect={setSelectedJourneyId}
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
          </section>

          <aside className="space-y-6 xl:border-l xl:border-border xl:pl-8">
            <Button
              aria-controls="network-map-heading"
              aria-expanded={showNetworkOnMobile}
              className="w-full xl:hidden"
              onClick={() => setShowNetworkOnMobile((isVisible) => !isVisible)}
              type="button"
              variant="outline"
            >
              {showNetworkOnMobile ? "Hide network view" : "Show network view"}
            </Button>
            <div className={showNetworkOnMobile ? undefined : "hidden xl:block"}>
              <Suspense
                fallback={
                  <section aria-busy="true" aria-label="Loading network view" className="space-y-3">
                    <div>
                      <p className="font-mono text-xs font-semibold tracking-wide text-muted-foreground uppercase">
                        KL / Klang Valley first
                      </p>
                      <h2 className="mt-1 text-xl font-semibold">Network view</h2>
                    </div>
                    <Skeleton className="h-72 rounded-sm sm:h-96" />
                  </section>
                }
              >
                <NetworkMapPanel isDark={isDark} vehicles={board.vehicles} />
              </Suspense>
            </div>
            {selectedJourney &&
            filteredJourneys.some((journey) => journey.id === selectedJourney.id) ? (
              <section
                aria-labelledby="selected-service-heading"
                className="border-y border-border py-5"
              >
                <p className="font-mono text-xs font-semibold tracking-wide text-muted-foreground uppercase">
                  Selected service
                </p>
                <h2 id="selected-service-heading" className="mt-1 text-xl font-semibold">
                  {selectedJourney.routeLabel} · {selectedJourney.routeName}
                </h2>
                <dl className="mt-4 space-y-3 text-sm">
                  <div className="flex items-start gap-3">
                    <Crosshair aria-hidden="true" className="mt-0.5 text-primary" />
                    <div>
                      <dt className="font-mono text-xs tracking-wide text-muted-foreground uppercase">
                        Direction
                      </dt>
                      <dd className="mt-1">
                        {selectedJourney.origin} to {selectedJourney.destination}
                      </dd>
                    </div>
                  </div>
                  <div className="flex items-start gap-3">
                    <CalendarBlank aria-hidden="true" className="mt-0.5 text-primary" />
                    <div>
                      <dt className="font-mono text-xs tracking-wide text-muted-foreground uppercase">
                        Planned journey
                      </dt>
                      <dd className="mt-1">
                        <time dateTime={selectedJourney.serviceDateIso}>
                          {selectedJourney.serviceDate}
                        </time>
                        ,{" "}
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
                      </dd>
                    </div>
                  </div>
                </dl>
              </section>
            ) : null}
          </aside>
        </div>
      </main>
      <footer className="mt-10 border-t border-border bg-muted/35">
        <div className="mx-auto flex max-w-7xl flex-col gap-2 px-4 py-6 text-sm text-muted-foreground sm:px-6 lg:flex-row lg:items-center lg:justify-between lg:px-8">
          <p>Malaysia Transit Live · public-information service</p>
          <p className="font-mono text-xs">Local favourites stay in this browser.</p>
        </div>
      </footer>
    </div>
  )
}
