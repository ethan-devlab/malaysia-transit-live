"""Deterministically match ordered scheduled stops to an offline rail graph."""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass
from heapq import heappop, heappush
from itertools import count, pairwise
from typing import Final, Literal

Coordinate = tuple[float, float]
MatchStatus = Literal["accepted", "rejected", "ambiguous"]

DERIVATION_VERSION: Final = "ktmb-osm-rail-v2"
MAX_CANDIDATES_PER_STOP: Final = 3
MAX_STOP_DISTANCE_METRES: Final = 750.0
MAX_ENDPOINT_DISTANCE_METRES: Final = 750.0
MAX_DETOUR_RATIO: Final = 2.5
MIN_CONFIDENCE: Final = 0.75
IDENTITY_MISMATCH_PENALTY_METRES: Final = 500.0
AMBIGUITY_MARGIN_METRES: Final = 100.0
STOP_DISTANCE_COST_MULTIPLIER: Final = 4.0
SPATIAL_CELL_DEGREES: Final = 0.01
SPATIAL_SEARCH_RADIUS_CELLS: Final = 2


@dataclass(frozen=True, slots=True)
class GraphNode:
    """Name one graph vertex using its stable source ID and GeoJSON coordinate."""

    external_id: str
    coordinate: Coordinate


@dataclass(frozen=True, slots=True)
class GraphEdge:
    """Describe a permitted bidirectional rail segment and its source references."""

    external_id: str
    start_node_external_id: str
    end_node_external_id: str
    length_metres: float
    route_refs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class GraphPath:
    """Capture one weighted graph path with its physical length kept separately."""

    node_ids: tuple[str, ...]
    edge_ids: tuple[str, ...]
    equivalent_path_count: int
    length_metres: float
    weighted_cost: float


type PathCacheKey = tuple[str, str, tuple[str, ...]]
type PathCache = dict[PathCacheKey, GraphPath | None]


@dataclass(frozen=True, slots=True)
class RailGraph:
    """Expose a normalized graph with deterministic adjacency ordering."""

    nodes: dict[str, GraphNode]
    edges: dict[str, GraphEdge]
    adjacency: dict[str, tuple[GraphEdge, ...]]
    spatial_index: dict[tuple[int, int], tuple[str, ...]]

    @classmethod
    def from_edges(
        cls,
        nodes: dict[str, GraphNode],
        edges: tuple[GraphEdge, ...],
    ) -> RailGraph:
        """Build symmetric adjacency while rejecting dangling source edges."""
        adjacency: dict[str, list[GraphEdge]] = defaultdict(list)
        node_cells: dict[tuple[int, int], list[str]] = defaultdict(list)
        edge_by_id: dict[str, GraphEdge] = {}
        for node_id, node in nodes.items():
            node_cells[_spatial_cell(node.coordinate)].append(node_id)
        for edge in edges:
            if edge.start_node_external_id not in nodes or edge.end_node_external_id not in nodes:
                raise ValueError("A rail edge references an unknown graph node.")
            edge_by_id[edge.external_id] = edge
            adjacency[edge.start_node_external_id].append(edge)
            adjacency[edge.end_node_external_id].append(edge)
        return cls(
            adjacency={
                node_id: tuple(sorted(node_edges, key=lambda edge: edge.external_id))
                for node_id, node_edges in adjacency.items()
            },
            edges=edge_by_id,
            nodes=nodes,
            spatial_index={
                cell: tuple(sorted(node_ids))
                for cell, node_ids in node_cells.items()
            },
        )


@dataclass(frozen=True, slots=True)
class MatchResult:
    """Return an accepted path or a labelled safe-rejection outcome."""

    status: MatchStatus
    coordinates: tuple[Coordinate, ...]
    metrics: dict[str, float | int]
    reason: str


@dataclass(frozen=True, slots=True)
class _Candidate:
    node_id: str
    distance_metres: float


@dataclass(frozen=True, slots=True)
class _MatchState:
    ambiguous_branch_count: int
    current_node_id: str
    node_ids: tuple[str, ...]
    stop_distances: tuple[float, ...]
    track_length_metres: float
    weighted_cost: float


def matcher_configuration() -> dict[str, float | int | str]:
    """Provide the exact threshold set that becomes part of each persisted cache key."""
    return {
        "ambiguity_margin_metres": AMBIGUITY_MARGIN_METRES,
        "derivation_version": DERIVATION_VERSION,
        "identity_mismatch_penalty_metres": IDENTITY_MISMATCH_PENALTY_METRES,
        "max_candidates_per_stop": MAX_CANDIDATES_PER_STOP,
        "max_detour_ratio": MAX_DETOUR_RATIO,
        "max_endpoint_distance_metres": MAX_ENDPOINT_DISTANCE_METRES,
        "max_stop_distance_metres": MAX_STOP_DISTANCE_METRES,
        "minimum_confidence": MIN_CONFIDENCE,
        "spatial_cell_degrees": SPATIAL_CELL_DEGREES,
        "spatial_search_radius_cells": SPATIAL_SEARCH_RADIUS_CELLS,
        "stop_distance_cost_multiplier": STOP_DISTANCE_COST_MULTIPLIER,
    }


def match_ordered_stops(
    graph: RailGraph,
    stops: tuple[Coordinate, ...],
    route_identity: tuple[str, ...],
    path_cache: PathCache | None = None,
) -> MatchResult:
    """Choose a continuous ordered-stop rail path or preserve the safe fallback."""
    distinct_stops = _distinct_coordinates(stops)
    if len(distinct_stops) < 2:
        return _rejected("At least two distinct scheduled stops are required.")
    candidates_by_stop = tuple(_candidate_nodes(graph, stop) for stop in distinct_stops)
    if any(not candidates for candidates in candidates_by_stop):
        return _rejected(
            "One or more scheduled stops are farther than "
            f"{MAX_STOP_DISTANCE_METRES:.0f} m from a permitted rail graph node."
        )
    states = _matching_states(
        graph,
        candidates_by_stop,
        _identity_tokens(route_identity),
        path_cache if path_cache is not None else {},
    )
    if not states:
        return _rejected("Scheduled stops do not form a continuous permitted rail path.")
    ordered_states = tuple(sorted(states, key=lambda state: (state.weighted_cost, state.node_ids)))
    direct_length = sum(haversine_metres(start, end) for start, end in pairwise(distinct_stops))
    if direct_length == 0:
        return _rejected("Scheduled stops do not define a measurable route direction.")
    return _evaluated_match(graph, ordered_states, direct_length)


def haversine_metres(start: Coordinate, end: Coordinate) -> float:
    """Measure geographic distance in metres for graph weights and confidence gates."""
    start_longitude, start_latitude = start
    end_longitude, end_latitude = end
    latitude_delta = math.radians(end_latitude - start_latitude)
    longitude_delta = math.radians(end_longitude - start_longitude)
    start_latitude_radians = math.radians(start_latitude)
    end_latitude_radians = math.radians(end_latitude)
    a = (
        math.sin(latitude_delta / 2) ** 2
        + math.cos(start_latitude_radians)
        * math.cos(end_latitude_radians)
        * math.sin(longitude_delta / 2) ** 2
    )
    return 6_371_008.8 * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _matching_states(
    graph: RailGraph,
    candidates_by_stop: tuple[tuple[_Candidate, ...], ...],
    route_tokens: tuple[str, ...],
    path_cache: PathCache,
) -> tuple[_MatchState, ...]:
    states = tuple(
        _MatchState(
            ambiguous_branch_count=0,
            current_node_id=candidate.node_id,
            node_ids=(candidate.node_id,),
            stop_distances=(candidate.distance_metres,),
            track_length_metres=0.0,
            weighted_cost=candidate.distance_metres * STOP_DISTANCE_COST_MULTIPLIER,
        )
        for candidate in candidates_by_stop[0]
    )
    for candidates in candidates_by_stop[1:]:
        states = _best_states(
            [
                next_state
                for state in states
                for candidate in candidates
                if (
                    next_state := _next_state(
                        graph,
                        state,
                        candidate,
                        route_tokens,
                        path_cache,
                    )
                )
                is not None
            ]
        )
        if not states:
            break
    return states


def _next_state(
    graph: RailGraph,
    state: _MatchState,
    candidate: _Candidate,
    route_tokens: tuple[str, ...],
    path_cache: PathCache,
) -> _MatchState | None:
    path = _path_between(
        graph,
        state.current_node_id,
        candidate.node_id,
        route_tokens,
        path_cache,
    )
    if path is None:
        return None
    return _MatchState(
        ambiguous_branch_count=state.ambiguous_branch_count + path.equivalent_path_count - 1,
        current_node_id=candidate.node_id,
        node_ids=state.node_ids + path.node_ids[1:],
        stop_distances=(*state.stop_distances, candidate.distance_metres),
        track_length_metres=state.track_length_metres + path.length_metres,
        weighted_cost=(
            state.weighted_cost
            + path.weighted_cost
            + candidate.distance_metres * STOP_DISTANCE_COST_MULTIPLIER
        ),
    )


def _evaluated_match(
    graph: RailGraph,
    ordered_states: tuple[_MatchState, ...],
    direct_length: float,
) -> MatchResult:
    best_state = ordered_states[0]
    metrics = _metrics(best_state, direct_length, ordered_states)
    if metrics["ambiguous_branch_count"]:
        return MatchResult(
            coordinates=(),
            metrics=metrics,
            reason="Comparable graph branches satisfy the ordered-stop constraints.",
            status="ambiguous",
        )
    rejection_reason = _quality_rejection(metrics)
    if rejection_reason:
        return _rejected(rejection_reason, metrics)
    coordinates = tuple(graph.nodes[node_id].coordinate for node_id in best_state.node_ids)
    if len(_distinct_coordinates(coordinates)) < 2:
        return _rejected("The selected rail path has fewer than two distinct coordinates.", metrics)
    return MatchResult(coordinates=coordinates, metrics=metrics, reason="", status="accepted")


def _quality_rejection(metrics: dict[str, float | int]) -> str | None:
    if metrics["endpoint_distance_metres"] > MAX_ENDPOINT_DISTANCE_METRES:
        return "A terminal stop is farther than the endpoint tolerance."
    if metrics["maximum_stop_distance_metres"] > MAX_STOP_DISTANCE_METRES:
        return "A scheduled stop exceeds the graph proximity tolerance."
    if metrics["detour_ratio"] > MAX_DETOUR_RATIO:
        return "The continuous rail path exceeds the maximum detour ratio."
    if metrics["confidence"] < MIN_CONFIDENCE:
        return "The constrained path did not meet the confidence threshold."
    return None


def _candidate_nodes(graph: RailGraph, stop: Coordinate) -> tuple[_Candidate, ...]:
    longitude_cell, latitude_cell = _spatial_cell(stop)
    candidates = sorted(
        (
            _Candidate(node_id=node_id, distance_metres=haversine_metres(stop, node.coordinate))
            for latitude_offset in range(
                -SPATIAL_SEARCH_RADIUS_CELLS,
                SPATIAL_SEARCH_RADIUS_CELLS + 1,
            )
            for longitude_offset in range(
                -SPATIAL_SEARCH_RADIUS_CELLS,
                SPATIAL_SEARCH_RADIUS_CELLS + 1,
            )
            for node_id in graph.spatial_index.get(
                (longitude_cell + longitude_offset, latitude_cell + latitude_offset),
                (),
            )
            if (node := graph.nodes[node_id])
        ),
        key=lambda candidate: (candidate.distance_metres, candidate.node_id),
    )
    return tuple(
        candidate
        for candidate in candidates
        if candidate.distance_metres <= MAX_STOP_DISTANCE_METRES
    )[:MAX_CANDIDATES_PER_STOP]


def _path_between(
    graph: RailGraph,
    start_node_id: str,
    end_node_id: str,
    route_tokens: tuple[str, ...],
    cache: PathCache,
) -> GraphPath | None:
    cache_key = (start_node_id, end_node_id, route_tokens)
    if cache_key not in cache:
        cache[cache_key] = _shortest_path(graph, start_node_id, end_node_id, route_tokens)
    return cache[cache_key]


def _shortest_path(
    graph: RailGraph,
    start_node_id: str,
    end_node_id: str,
    route_tokens: tuple[str, ...],
) -> GraphPath | None:
    if start_node_id == end_node_id:
        return GraphPath(
            edge_ids=(),
            equivalent_path_count=1,
            length_metres=0.0,
            node_ids=(start_node_id,),
            weighted_cost=0.0,
        )
    distances = {start_node_id: 0.0}
    path_counts = {start_node_id: 1}
    predecessors: dict[str, tuple[str, str]] = {}
    queue_counter = count()
    queue: list[tuple[float, int, str]] = [(0.0, next(queue_counter), start_node_id)]
    while queue:
        current_cost, _, current_node_id = heappop(queue)
        if current_cost != distances.get(current_node_id):
            continue
        if current_node_id == end_node_id:
            break
        for edge in graph.adjacency.get(current_node_id, ()):
            next_node_id = _opposite_node(edge, current_node_id)
            next_cost = current_cost + _edge_cost(edge, route_tokens)
            existing_cost = distances.get(next_node_id)
            predecessor = (current_node_id, edge.external_id)
            if (
                existing_cost is None
                or next_cost < existing_cost
                or (next_cost == existing_cost and predecessor < predecessors[next_node_id])
            ):
                distances[next_node_id] = next_cost
                path_counts[next_node_id] = path_counts[current_node_id]
                predecessors[next_node_id] = predecessor
                heappush(queue, (next_cost, next(queue_counter), next_node_id))
            elif next_cost == existing_cost:
                path_counts[next_node_id] = (
                    path_counts.get(next_node_id, 0) + path_counts[current_node_id]
                )
    if end_node_id not in distances:
        return None
    node_ids = [end_node_id]
    edge_ids: list[str] = []
    current_node_id = end_node_id
    while current_node_id != start_node_id:
        previous_node_id, edge_id = predecessors[current_node_id]
        node_ids.append(previous_node_id)
        edge_ids.append(edge_id)
        current_node_id = previous_node_id
    ordered_edge_ids = tuple(reversed(edge_ids))
    return GraphPath(
        edge_ids=ordered_edge_ids,
        equivalent_path_count=path_counts[end_node_id],
        length_metres=sum(graph.edges[edge_id].length_metres for edge_id in ordered_edge_ids),
        node_ids=tuple(reversed(node_ids)),
        weighted_cost=distances[end_node_id],
    )


def _best_states(states: list[_MatchState]) -> tuple[_MatchState, ...]:
    by_node: dict[str, list[_MatchState]] = defaultdict(list)
    for state in sorted(states, key=lambda item: (item.weighted_cost, item.node_ids)):
        existing = by_node[state.current_node_id]
        if state.node_ids not in {item.node_ids for item in existing} and len(existing) < 2:
            existing.append(state)
    return tuple(state for node_id in sorted(by_node) for state in by_node[node_id])


def _metrics(
    best_state: _MatchState,
    direct_length: float,
    ordered_states: tuple[_MatchState, ...],
) -> dict[str, float | int]:
    endpoint_distance = max(best_state.stop_distances[0], best_state.stop_distances[-1])
    maximum_stop_distance = max(best_state.stop_distances)
    detour_ratio = best_state.track_length_metres / direct_length
    ambiguity_count = best_state.ambiguous_branch_count + sum(
        state.weighted_cost - best_state.weighted_cost <= AMBIGUITY_MARGIN_METRES
        for state in ordered_states[1:]
    )
    proximity_penalty = (
        min(
            1.0,
            (endpoint_distance / MAX_ENDPOINT_DISTANCE_METRES)
            + (maximum_stop_distance / MAX_STOP_DISTANCE_METRES),
        )
        / 2
    )
    detour_penalty = max(0.0, detour_ratio - 1) / max(1.0, MAX_DETOUR_RATIO - 1)
    confidence = max(0.0, 1 - 0.55 * proximity_penalty - 0.45 * detour_penalty)
    return {
        "ambiguous_branch_count": ambiguity_count,
        "confidence": round(confidence, 6),
        "detour_ratio": round(detour_ratio, 6),
        "endpoint_distance_metres": round(endpoint_distance, 3),
        "maximum_stop_distance_metres": round(maximum_stop_distance, 3),
        "railway_edge_coverage": 1.0,
        "track_length_metres": round(best_state.track_length_metres, 3),
    }


def _edge_cost(edge: GraphEdge, route_tokens: tuple[str, ...]) -> float:
    if route_tokens and edge.route_refs and not _edge_matches_identity(edge, route_tokens):
        return edge.length_metres + IDENTITY_MISMATCH_PENALTY_METRES
    return edge.length_metres


def _edge_matches_identity(edge: GraphEdge, route_tokens: tuple[str, ...]) -> bool:
    edge_tokens = _identity_tokens(edge.route_refs)
    return any(
        route_token in edge_token or edge_token in route_token
        for route_token in route_tokens
        for edge_token in edge_tokens
    )


def _identity_tokens(values: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(
        sorted(
            {
                token.casefold()
                for value in values
                for token in value.replace("/", " ").replace("-", " ").split()
                if token
            }
        )
    )


def _opposite_node(edge: GraphEdge, node_id: str) -> str:
    if node_id == edge.start_node_external_id:
        return edge.end_node_external_id
    return edge.start_node_external_id


def _distinct_coordinates(coordinates: tuple[Coordinate, ...]) -> tuple[Coordinate, ...]:
    distinct: list[Coordinate] = []
    for coordinate in coordinates:
        if not distinct or distinct[-1] != coordinate:
            distinct.append(coordinate)
    return tuple(distinct)


def _spatial_cell(coordinate: Coordinate) -> tuple[int, int]:
    longitude, latitude = coordinate
    return (
        math.floor(longitude / SPATIAL_CELL_DEGREES),
        math.floor(latitude / SPATIAL_CELL_DEGREES),
    )


def _rejected(
    reason: str,
    metrics: dict[str, float | int] | None = None,
) -> MatchResult:
    return MatchResult(coordinates=(), metrics=metrics or {}, reason=reason, status="rejected")
