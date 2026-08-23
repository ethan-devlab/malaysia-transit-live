from __future__ import annotations

from transit.services.rail_matching import (
    GraphEdge,
    GraphNode,
    PathCache,
    RailGraph,
    match_ordered_stops,
)


def test_given_connected_ordered_stops_when_matching_then_accepts_one_continuous_path() -> None:
    graph = _graph(
        {
            "a": (101.0, 3.0),
            "b": (101.004, 3.0),
            "c": (101.008, 3.0),
        },
        (("a", "b", ()), ("b", "c", ())),
    )

    result = match_ordered_stops(
        graph,
        ((101.0, 3.0), (101.004, 3.0), (101.008, 3.0)),
        (),
    )

    assert result.status == "accepted"
    assert result.coordinates == ((101.0, 3.0), (101.004, 3.0), (101.008, 3.0))
    assert result.metrics["ambiguous_branch_count"] == 0


def test_given_a_nearer_disconnected_track_when_matching_then_uses_the_connected_stop_order() -> (
    None
):
    graph = _graph(
        {
            "a": (101.0004, 3.0),
            "b": (101.004, 3.0),
            "c": (101.008, 3.0),
            "d": (101.0, 3.0),
            "e": (101.0002, 3.001),
        },
        (("a", "b", ()), ("b", "c", ()), ("d", "e", ())),
    )

    result = match_ordered_stops(graph, ((101.0001, 3.0), (101.008, 3.0)), ())

    assert result.status == "accepted"
    assert result.coordinates[0] == (101.0004, 3.0)
    assert result.coordinates[-1] == (101.008, 3.0)


def test_given_stops_across_spatial_cells_when_matching_then_keeps_a_nearby_continuous_path() -> (
    None
):
    graph = _graph(
        {
            "a": (101.0098, 3.0),
            "b": (101.0198, 3.0),
        },
        (("a", "b", ()),),
    )

    result = match_ordered_stops(graph, ((101.0101, 3.0), (101.0201, 3.0)), ())

    assert result.status == "accepted"
    assert result.coordinates == ((101.0098, 3.0), (101.0198, 3.0))


def test_given_disconnected_stops_when_matching_then_rejects_without_a_path() -> None:
    graph = _graph(
        {
            "a": (101.0, 3.0),
            "b": (101.004, 3.0),
            "c": (101.02, 3.0),
            "d": (101.024, 3.0),
        },
        (("a", "b", ()), ("c", "d", ())),
    )

    result = match_ordered_stops(graph, ((101.0, 3.0), (101.024, 3.0)), ())

    assert result.status == "rejected"
    assert result.coordinates == ()
    assert result.reason == "Scheduled stops do not form a continuous permitted rail path."


def test_given_equal_branches_when_matching_then_marks_the_alignment_ambiguous() -> None:
    graph = _graph(
        {
            "a": (101.0, 3.0),
            "north": (101.004, 3.004),
            "south": (101.004, 2.996),
            "c": (101.008, 3.0),
        },
        (
            ("a", "north", ()),
            ("north", "c", ()),
            ("a", "south", ()),
            ("south", "c", ()),
        ),
    )

    first = match_ordered_stops(graph, ((101.0, 3.0), (101.008, 3.0)), ())
    second = match_ordered_stops(graph, ((101.0, 3.0), (101.008, 3.0)), ())

    assert first.status == "ambiguous"
    assert first.coordinates == ()
    assert first.metrics["ambiguous_branch_count"] == 1
    assert second == first


def test_given_repeated_service_patterns_when_matching_then_reuses_run_scoped_paths() -> None:
    graph = _graph(
        {
            "a": (101.0, 3.0),
            "b": (101.004, 3.0),
            "c": (101.008, 3.0),
        },
        (("a", "b", ()), ("b", "c", ())),
    )
    path_cache: PathCache = {}

    first = match_ordered_stops(
        graph,
        ((101.0, 3.0), (101.004, 3.0), (101.008, 3.0)),
        (),
        path_cache,
    )
    cache_size_after_first = len(path_cache)
    second = match_ordered_stops(
        graph,
        ((101.0, 3.0), (101.004, 3.0), (101.008, 3.0)),
        (),
        path_cache,
    )

    assert cache_size_after_first > 0
    assert len(path_cache) == cache_size_after_first
    assert second == first


def test_given_known_route_identity_when_matching_then_prefers_matching_rail_edges() -> None:
    graph = _graph(
        {
            "a": (101.0, 3.0),
            "ktm": (101.004, 3.004),
            "other": (101.004, 2.996),
            "c": (101.008, 3.0),
        },
        (
            ("a", "ktm", ("KTM",)),
            ("ktm", "c", ("KTM",)),
            ("a", "other", ("Other operator",)),
            ("other", "c", ("Other operator",)),
        ),
    )

    result = match_ordered_stops(graph, ((101.0, 3.0), (101.008, 3.0)), ("KTM",))

    assert result.status == "accepted"
    assert (101.004, 3.004) in result.coordinates
    assert (101.004, 2.996) not in result.coordinates


def _graph(
    coordinates: dict[str, tuple[float, float]],
    segments: tuple[tuple[str, str, tuple[str, ...]], ...],
) -> RailGraph:
    nodes = {
        node_id: GraphNode(external_id=node_id, coordinate=coordinate)
        for node_id, coordinate in coordinates.items()
    }
    edges = tuple(
        GraphEdge(
            end_node_external_id=end_node_id,
            external_id=f"{start_node_id}-{end_node_id}",
            length_metres=500.0,
            route_refs=route_refs,
            start_node_external_id=start_node_id,
        )
        for start_node_id, end_node_id, route_refs in segments
    )
    return RailGraph.from_edges(nodes, edges)
