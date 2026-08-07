import { fireEvent, render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"

import { type DashboardFilterState, DashboardFilters } from "@/components/dashboard-filters"
import type { Dashboard } from "@/lib/dashboard-api"

const data = {
  generated_at: "2026-07-16T10:00:00Z",
  filters: { mode: "all", operator: null, region: null },
  options: {
    modes: [{ key: "bus", label: "Bus", count: 1 }],
    operators: [{ key: "rapid-kl", label: "Rapid KL", count: 1 }],
    regions: [{ key: "kuala-lumpur", label: "Kuala Lumpur", count: 1 }],
  },
  summary: {
    feed_count: 1,
    vehicle_count: 1,
    live_vehicle_count: 1,
    stale_vehicle_count: 0,
    unknown_vehicle_count: 0,
    scheduled_only_feed_count: 0,
    unavailable_feed_count: 0,
    awaiting_first_fetch_feed_count: 0,
  },
  sources: [
    {
      feed: "rapid-bus-kl",
      display_name: "Rapid Bus Kuala Lumpur",
      operator_key: "rapid-kl",
      operator_name: "Rapid KL",
      region_key: "kuala-lumpur",
      region_name: "Kuala Lumpur",
      agency_names: ["Rapid"],
      modes: ["bus"],
      static_state: "active",
      realtime_state: "available",
      last_successful_static_fetch_at: null,
      last_successful_realtime_fetch_at: null,
      vehicle_count: 1,
      live_vehicle_count: 1,
      stale_vehicle_count: 0,
      unknown_vehicle_count: 0,
    },
  ],
  vehicles: { items: [], total_count: 0, returned_count: 0, next_cursor: null, truncated: false },
} satisfies Dashboard

describe("DashboardFilters", () => {
  it("clears child filters when the parent mode changes", () => {
    let current: DashboardFilterState = {
      mode: "bus",
      operator: "rapid-kl",
      region: "kuala-lumpur",
    }
    render(
      <DashboardFilters
        data={data}
        onChange={(next) => {
          current = next
        }}
        value={current}
      />,
    )

    fireEvent.change(screen.getByLabelText("Filter by mode"), { target: { value: "all" } })

    expect(current).toEqual({ mode: "all", operator: "", region: "" })
  })
})
