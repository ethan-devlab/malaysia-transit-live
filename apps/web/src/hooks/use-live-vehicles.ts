import { useQuery, useQueryClient } from "@tanstack/react-query"
import { useEffect } from "react"

import {
  fetchVehicleLocations,
  parseVehicleSnapshot,
  type VehicleLocation,
} from "@/lib/transit-api"

const queryKey = ["validated-vehicles"] as const

export function useLiveVehicles(enabled: boolean): readonly VehicleLocation[] {
  const queryClient = useQueryClient()
  const vehicleQuery = useQuery({
    enabled,
    queryFn: ({ signal }) => fetchVehicleLocations(signal),
    queryKey,
    refetchInterval: 60_000,
  })

  useEffect(() => {
    if (!enabled) {
      return undefined
    }
    const eventSource = new EventSource("/stream/v1/vehicles")
    const onSnapshot = (event: MessageEvent<string>) => {
      try {
        queryClient.setQueryData<readonly VehicleLocation[]>(
          queryKey,
          parseVehicleSnapshot(event.data),
        )
      } catch {
        // Keep the last validated REST snapshot if a malformed event is received.
      }
    }

    eventSource.addEventListener("vehicle-snapshot", onSnapshot)
    return () => {
      eventSource.removeEventListener("vehicle-snapshot", onSnapshot)
      eventSource.close()
    }
  }, [enabled, queryClient])

  return vehicleQuery.data ?? []
}
