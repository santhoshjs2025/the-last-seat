from datetime import timedelta
from app.db.models import Reservation, ReservationStatus, Seat, SeatStatus, utc_now


def test_create_reservation_success(client):
    res = client.post("/api/v1/reservations", json={"user_id": "user_101", "seat_id": 10})
    assert res.status_code == 201
    data = res.json()
    assert data["user_id"] == "user_101"
    assert data["seat_id"] == 10
    assert data["status"] == "ACTIVE"
    assert data["remaining_seconds"] > 0

    # Verify seat is marked RESERVED
    seat_res = client.get("/api/v1/seats/10")
    assert seat_res.json()["status"] == "RESERVED"


def test_reject_duplicate_reservation_on_same_seat(client):
    # First reservation succeeds
    res1 = client.post("/api/v1/reservations", json={"user_id": "user_101", "seat_id": 11})
    assert res1.status_code == 201

    # Second reservation on the same seat must fail with 409
    res2 = client.post("/api/v1/reservations", json={"user_id": "user_102", "seat_id": 11})
    assert res2.status_code == 409
    assert "not available" in res2.json()["detail"].lower() or "already reserved" in res2.json()["detail"].lower()


def test_cancel_reservation_releases_seat(client):
    res = client.post("/api/v1/reservations", json={"user_id": "user_103", "seat_id": 12})
    assert res.status_code == 201
    res_id = res.json()["id"]

    # Cancel reservation
    cancel_res = client.post(f"/api/v1/reservations/{res_id}/cancel")
    assert cancel_res.status_code == 200
    assert cancel_res.json()["status"] == "CANCELLED"

    # Verify seat is AVAILABLE again
    seat_res = client.get("/api/v1/seats/12")
    assert seat_res.json()["status"] == "AVAILABLE"

    # Another user can now reserve this seat
    res_rebook = client.post("/api/v1/reservations", json={"user_id": "user_104", "seat_id": 12})
    assert res_rebook.status_code == 201


def test_lazy_expiry_of_reservation(client, db_session):
    res = client.post("/api/v1/reservations", json={"user_id": "user_105", "seat_id": 13})
    assert res.status_code == 201
    res_id = res.json()["id"]

    # Manually backdate the expires_at timestamp to simulate 6 minutes elapsed
    import uuid as _uuid
    reservation = db_session.get(Reservation, _uuid.UUID(res_id))
    reservation.expires_at = utc_now() - timedelta(minutes=1)
    db_session.commit()

    # Querying reservation should mark it EXPIRED lazily
    get_res = client.get(f"/api/v1/reservations/{res_id}")
    assert get_res.status_code == 200
    assert get_res.json()["status"] == "EXPIRED"

    # Seat should be marked AVAILABLE
    seat_res = client.get("/api/v1/seats/13")
    assert seat_res.json()["status"] == "AVAILABLE"


def test_invalid_reservation_payload(client):
    # Invalid seat_id <= 0
    res = client.post("/api/v1/reservations", json={"user_id": "user_001", "seat_id": 0})
    assert res.status_code == 422

    # Missing user_id
    res = client.post("/api/v1/reservations", json={"seat_id": 1})
    assert res.status_code == 422
