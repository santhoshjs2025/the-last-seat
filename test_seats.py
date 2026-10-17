def test_initial_seat_inventory(client):
    response = client.get("/api/v1/seats?limit=500")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 500
    assert len(data["items"]) == 500
    assert data["items"][0]["seat_number"] == "A001"
    assert data["items"][0]["status"] == "AVAILABLE"
    assert data["items"][499]["seat_number"] == "A500"


def test_get_available_seats(client):
    response = client.get("/api/v1/seats/available?limit=10")
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 10
    for item in data["items"]:
        assert item["status"] == "AVAILABLE"


def test_get_seat_by_id(client):
    response = client.get("/api/v1/seats/1")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == 1
    assert data["seat_number"] == "A001"


def test_get_seat_not_found(client):
    response = client.get("/api/v1/seats/9999")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()
