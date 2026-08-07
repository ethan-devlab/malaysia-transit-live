import { useQuery, useQueryClient } from "@tanstack/react-query"
import { useEffect } from "react"

import { previewDashboard } from "@/data/previewDashboard"
import {
  type Dashboard,
  type DashboardQuery,
  fetchDashboard,
  parseDashboardSnapshot,
} from "@/lib/dashboard-api"

const dashboardKey = ["dashboard"] as const

export function useDashboard(query: DashboardQuery) {
  const queryClient = useQueryClient()
  const dashboardQuery = useQuery({
    enabled: true,
    queryFn: ({ signal }) =>
      import.meta.env.PROD
        ? fetchDashboard(query, signal)
        : Promise.resolve(previewDashboard(query)),
    queryKey: [...dashboardKey, query.mode, query.operator, query.region],
    refetchInterval: 60_000,
    staleTime: 30_000,
  })

  useEffect(() => {
    if (!import.meta.env.PROD) {
      return undefined
    }
    const params = new URLSearchParams()
    if (query.mode !== "all") params.set("mode", query.mode)
    if (query.operator) params.set("operator", query.operator)
    if (query.region) params.set("region", query.region)
    const source = new EventSource(`/stream/v1/dashboard?${params.toString()}`)
    const onSnapshot = (event: MessageEvent<string>) => {
      try {
        const snapshot = parseDashboardSnapshot(event.data)
        queryClient.setQueryData<Dashboard>(
          [...dashboardKey, query.mode, query.operator, query.region],
          snapshot,
        )
      } catch {}
    }
    source.addEventListener("dashboard-snapshot", onSnapshot)
    return () => {
      source.removeEventListener("dashboard-snapshot", onSnapshot)
      source.close()
    }
  }, [query.mode, query.operator, query.region, queryClient])

  return dashboardQuery
}
