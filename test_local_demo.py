import uuid
from datetime import timedelta
import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from app.db.models import (
    Seat,
    SeatStatus,
    Reservation,
    ReservationStatus,
    Booking,
    BookingStatus,
    utc_now,
)
from app.db.init_db import init_seats


def test_startup_and_health(client):
    """Verifies application startup and the /health database probe."""
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "healthy"
    assert data["database"] == "connected"
    assert "timestamp" in data


def test_seat_initialization_500(db_session):
    """Verifies that exactly 500 seats are initialized idempotently."""
    total_seats = db_session.scalar(select(Seat.id).order_by(Seat.id.desc()))
    assert total_seats == 500

    seats = db_session.scalars(select(Seat).order_by(Seat.id.asc())).all()
    assert len(seats) == 500
    assert seats[0].seat_number == "A001"
    assert seats[499].seat_number == "A500"

    # Verify idempotency: calling init_seats again should insert 0 new seats
    newly_created = init_seats(500)
    assert newly_created == 0


def test_seat_reservation_and_confirmation(client):
    """Verifies reserving a seat and confirming it with simulated payment."""
    # 1. Create temporary reservation
    res_resp = client.post(
        "/api/v1/reservations",
        json={"user_id": "demo_user_1", "seat_id": 101},
    )
    assert res_resp.status_code == 201
    res_data = res_resp.json()
    assert res_data["status"] == "ACTIVE"
    assert res_data["seat_id"] == 101
    assert res_data["remaining_seconds"] > 0
    res_id = res_data["id"]

    # Verify seat is marked RESERVED
    seat_resp = client.get("/api/v1/seats/101")
    assert seat_resp.status_code == 200
    assert seat_resp.json()["status"] == "RESERVED"

    # 2. Confirm booking with payment
    confirm_resp = client.post(
        f"/api/v1/reservations/{res_id}/confirm",
        headers={"Idempotency-Key": f"demo-key-{uuid.uuid4()}"},
        json={"payment_outcome": "SUCCESS", "amount": 50.00},
    )
    assert confirm_resp.status_code == 200
    confirm_data = confirm_resp.json()
    assert confirm_data["status"] == "SUCCESS"
    assert confirm_data["booking_id"] is not None

    # Verify seat is marked BOOKED
    seat_after = client.get("/api/v1/seats/101")
    assert seat_after.json()["status"] == "BOOKED"


def test_booking_cancellation_and_seat_reallocation(client):
    """Verifies booking cancellation frees the seat for immediate reallocation."""
    # Reserve and confirm seat 102
    res = client.post("/api/v1/reservations", json={"user_id": "demo_user_2", "seat_id": 102})
    assert res.status_code == 201
    res_id = res.json()["id"]

    confirm = client.post(
        f"/api/v1/reservations/{res_id}/confirm",
        headers={"Idempotency-Key": f"demo-key-{uuid.uuid4()}"},
        json={"payment_outcome": "SUCCESS", "amount": 50.00},
    )
    assert confirm.status_code == 200
    booking_id = confirm.json()["booking_id"]

    # Cancel confirmed booking
    cancel_resp = client.post(f"/api/v1/bookings/{booking_id}/cancel")
    assert cancel_resp.status_code == 200
    assert cancel_resp.json()["status"] == "CANCELLED"

    # Verify seat 102 is AVAILABLE again
    seat_check = client.get("/api/v1/seats/102")
    assert seat_check.json()["status"] == "AVAILABLE"

    # Another user can re-book seat 102
    rebook = client.post("/api/v1/reservations", json={"user_id": "demo_user_3", "seat_id": 102})
    assert rebook.status_code == 201


def test_reservation_expiry_prevents_confirmation(client, db_session):
    """Verifies expired reservations cannot be confirmed and seats are released."""
    res = client.post("/api/v1/reservations", json={"user_id": "demo_user_4", "seat_id": 103})
    assert res.status_code == 201
    res_id = res.json()["id"]

    # Simulate 5-minute expiration
    reservation = db_session.get(Reservation, uuid.UUID(res_id))
    reservation.expires_at = utc_now() - timedelta(minutes=6)
    db_session.commit()

    # Attempt confirmation
    confirm = client.post(
        f"/api/v1/reservations/{res_id}/confirm",
        headers={"Idempotency-Key": f"demo-key-{uuid.uuid4()}"},
        json={"payment_outcome": "SUCCESS", "amount": 50.00},
    )
    assert confirm.status_code == 400
    assert "expired" in confirm.json()["detail"].lower()

    # Verify seat is marked AVAILABLE
    seat_check = client.get("/api/v1/seats/103")
    assert seat_check.json()["status"] == "AVAILABLE"


def test_duplicate_booking_prevention(client, db_session):
    """
    Verifies that duplicate confirmed bookings on the same seat are strictly prevented
    both at the API layer and the database constraint layer.
    """
    # 1. API layer prevention: second reservation on already reserved/booked seat
    r1 = client.post("/api/v1/reservations", json={"user_id": "user_a", "seat_id": 104})
    assert r1.status_code == 201
    r1_id = r1.json()["id"]

    r2 = client.post("/api/v1/reservations", json={"user_id": "user_b", "seat_id": 104})
    assert r2.status_code == 409

    # Confirm first reservation
    c1 = client.post(
        f"/api/v1/reservations/{r1_id}/confirm",
        headers={"Idempotency-Key": f"key-{uuid.uuid4()}"},
        json={"payment_outcome": "SUCCESS", "amount": 50.00},
    )
    assert c1.status_code == 200

    # 2. Database constraint layer: partial unique index blocks duplicate CONFIRMED bookings
    with pytest.raises(IntegrityError):
        duplicate_booking = Booking(
            reservation_id=uuid.uuid4(),
            user_id="rogue_user",
            seat_id=104,
            status=BookingStatus.CONFIRMED,
        )
        db_session.add(duplicate_booking)
        db_session.commit()
    db_session.rollback()
