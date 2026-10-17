import uuid
from datetime import timedelta
from app.db.models import Reservation, utc_now


def test_confirm_reservation_success(client):
    res = client.post("/api/v1/reservations", json={"user_id": "user_201", "seat_id": 20})
    assert res.status_code == 201
    res_id = res.json()["id"]

    idempotency_key = f"key-{uuid.uuid4()}"
    confirm_res = client.post(
        f"/api/v1/reservations/{res_id}/confirm",
        headers={"Idempotency-Key": idempotency_key},
        json={"payment_outcome": "SUCCESS", "amount": 50.00},
    )
    assert confirm_res.status_code == 200
    data = confirm_res.json()
    assert data["status"] == "SUCCESS"
    assert data["booking_id"] is not None
    assert data["payment"]["status"] == "SUCCESS"

    # Verify seat is now BOOKED
    seat_res = client.get("/api/v1/seats/20")
    assert seat_res.json()["status"] == "BOOKED"

    # Payment lookup
    pay_id = data["payment"]["id"]
    pay_res = client.get(f"/api/v1/payments/{pay_id}")
    assert pay_res.status_code == 200
    assert pay_res.json()["id"] == pay_id


def test_confirm_reservation_failure_releases_seat(client):
    res = client.post("/api/v1/reservations", json={"user_id": "user_202", "seat_id": 21})
    assert res.status_code == 201
    res_id = res.json()["id"]

    idempotency_key = f"key-{uuid.uuid4()}"
    confirm_res = client.post(
        f"/api/v1/reservations/{res_id}/confirm",
        headers={"Idempotency-Key": idempotency_key},
        json={"payment_outcome": "FAILURE", "amount": 50.00},
    )
    assert confirm_res.status_code == 400
    data = confirm_res.json()
    assert data["status"] == "FAILED"

    # Verify seat is AVAILABLE again
    seat_res = client.get("/api/v1/seats/21")
    assert seat_res.json()["status"] == "AVAILABLE"


def test_confirm_reservation_delayed(client):
    res = client.post("/api/v1/reservations", json={"user_id": "user_203", "seat_id": 22})
    assert res.status_code == 201
    res_id = res.json()["id"]

    idempotency_key = f"key-{uuid.uuid4()}"
    confirm_res = client.post(
        f"/api/v1/reservations/{res_id}/confirm",
        headers={"Idempotency-Key": idempotency_key},
        json={"payment_outcome": "DELAYED", "simulated_delay_seconds": 2, "amount": 50.00},
    )
    assert confirm_res.status_code == 202
    data = confirm_res.json()
    assert data["status"] == "PENDING"
    assert data["payment"]["status"] == "PENDING"


def test_idempotent_confirmation_requests(client):
    res = client.post("/api/v1/reservations", json={"user_id": "user_204", "seat_id": 23})
    assert res.status_code == 201
    res_id = res.json()["id"]

    idempotency_key = f"idemp-{uuid.uuid4()}"

    # First request
    resp1 = client.post(
        f"/api/v1/reservations/{res_id}/confirm",
        headers={"Idempotency-Key": idempotency_key},
        json={"payment_outcome": "SUCCESS", "amount": 50.00},
    )
    assert resp1.status_code == 200
    b_id1 = resp1.json()["booking_id"]

    # Repeated request with same idempotency key
    resp2 = client.post(
        f"/api/v1/reservations/{res_id}/confirm",
        headers={"Idempotency-Key": idempotency_key},
        json={"payment_outcome": "SUCCESS", "amount": 50.00},
    )
    assert resp2.status_code == 200
    assert resp2.json()["booking_id"] == b_id1

    # Reusing same idempotency key with different payload returns 409
    resp_conflict = client.post(
        f"/api/v1/reservations/{res_id}/confirm",
        headers={"Idempotency-Key": idempotency_key},
        json={"payment_outcome": "FAILURE", "amount": 99.00},
    )
    assert resp_conflict.status_code == 409


def test_cannot_confirm_expired_reservation(client, db_session):
    res = client.post("/api/v1/reservations", json={"user_id": "user_205", "seat_id": 24})
    assert res.status_code == 201
    res_id = res.json()["id"]

    # Backdate expires_at
    reservation = db_session.get(Reservation, uuid.UUID(res_id))
    reservation.expires_at = utc_now() - timedelta(minutes=2)
    db_session.commit()

    confirm_res = client.post(
        f"/api/v1/reservations/{res_id}/confirm",
        headers={"Idempotency-Key": str(uuid.uuid4())},
        json={"payment_outcome": "SUCCESS", "amount": 50.00},
    )
    assert confirm_res.status_code == 400
    assert "expired" in confirm_res.json()["detail"].lower()

    # Seat should be marked AVAILABLE
    seat_res = client.get("/api/v1/seats/24")
    assert seat_res.json()["status"] == "AVAILABLE"
