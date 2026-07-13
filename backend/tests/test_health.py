from django.test import Client


def test_health_endpoint_when_application_is_ready_returns_ok() -> None:
    # Given
    client = Client()

    # When
    response = client.get("/api/v1/healthz")

    # Then
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
