from transit.http.api_common import route_mode


def test_ktmb_tram_route_type_is_presented_as_rail() -> None:
    assert route_mode(0, "ktmb") == "rail"
