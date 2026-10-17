import os
import concurrent.futures
import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient
from app.main import app
from app.db.models import Reservation, ReservationStatus, Booking, BookingStatus, Seat, SeatStatus
from app.core.config import settings

# Concurrency tests require a real PostgreSQL database with actual row-locking semantics
POSTGRES_URL = os.getenv("CONCURRENCY_TEST_DB_URL", settings.DATABASE_URL)


def is_postgres_available() -> bool:
    """Detect if PostgreSQL is reachable for live row-level concurrency verification."""
    if not POSTGRES_URL.startswith("postgresql"):
        return False
    try:
        engine = create_engine(POSTGRES_URL, connect_args={"connect_timeout": 2})
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        engine.dispose()
        return True
    except Exception:
        return False


@pytest.mark.skipif(
    not is_postgres_available(),
    reason=(
        "PostgreSQL is not reachable in this environment. "
        "Concurrency tests require live PostgreSQL row-locking (SELECT FOR UPDATE) "
        "and partial unique indexes. Run in Docker Compose: 'docker compose up --build'."
    ),
)
def test_concurrent_reservations_single_winner():
    """
    Simultaneously submits 20 concurrent reservation requests for the EXACT SAME SEAT.
    Guarantees:
    - Exactly 1 request succeeds (HTTP 201).
    - Exactly 19 requests are rejected (HTTP 409 Conflict).
    - Database state invariant: exactly 1 ACTIVE reservation exists for the seat.
    """
    engine = create_engine(POSTGRES_URL, pool_size=25, max_overflow=10)
    Session = sessionmaker(bind=engine)

    target_seat_id = 50
    # Ensure seat is available
    with Session() as session:
        seat = session.get(Seat, target_seat_id)
        if seat:
            seat.status = SeatStatus.AVAILABLE
            # Clean up old reservations
            session.execute(
                Reservation.__table__.delete().where(Reservation.seat_id == target_seat_id)
            )
            session.commit()

    num_threads = 20
    results = []

    def make_reservation_request(user_index: int):
        with TestClient(app) as client:
            resp = client.post(
                "/api/v1/reservations",
                json={"user_id": f"concurrent_user_{user_index}", "seat_id": target_seat_id},
            )
            return resp.status_code, resp.json()

    with concurrent.futures.ThreadPoolExecutor(max_workers=num_threads) as executor:
        futures = [executor.submit(make_reservation_request, i) for i in range(num_threads)]
        for f in concurrent.futures.as_completed(futures):
            results.append(f.result())

    status_codes = [r[0] for r in results]
    success_count = status_codes.count(201)
    conflict_count = status_codes.count(409)

    assert success_count == 1, f"Expected exactly 1 success, got {success_count}"
    assert conflict_count == num_threads - 1, f"Expected {num_threads - 1} conflicts, got {conflict_count}"

    # Verify DB invariant
    with Session() as session:
        active_reservations = session.scalars(
            select(Reservation).where(
                Reservation.seat_id == target_seat_id,
                Reservation.status == ReservationStatus.ACTIVE,
            )
        ).all()
        assert len(active_reservations) == 1

    engine.dispose()


@pytest.mark.skipif(
    not is_postgres_available(),
    reason="PostgreSQL is required for concurrency integration testing.",
)
def test_concurrent_confirmations_single_booking():
    """
    Simultaneously submits 10 concurrent confirmation requests for the same reservation.
    Guarantees:
    - Only 1 confirmed booking can ever be created for a seat.
    - PostgreSQL partial unique index and row lock prevent double bookings.
    """
    engine = create_engine(POSTGRES_URL, pool_size=20, max_overflow=10)
    Session = sessionmaker(bind=engine)

    target_seat_id = 51
    reservation_id = None

    with Session() as session:
        seat = session.get(Seat, target_seat_id)
        if seat:
            seat.status = SeatStatus.AVAILABLE
            session.execute(
                Reservation.__table__.delete().where(Reservation.seat_id == target_seat_id)
            )
            session.commit()

        # Create active reservation
        with TestClient(app) as client:
            res = client.post(
                "/api/v1/reservations",
                json={"user_id": "test_confirm_user", "seat_id": target_seat_id},
            )
            assert res.status_code == 201
            reservation_id = res.json()["id"]

    num_threads = 10
    results = []

    def make_confirm_request(thread_idx: int):
        with TestClient(app) as client:
            resp = client.post(
                f"/api/v1/reservations/{reservation_id}/confirm",
                headers={"Idempotency-Key": f"concurrent-key-{thread_idx}"},
                json={"payment_outcome": "SUCCESS", "amount": 50.00},
            )
            return resp.status_code

    with concurrent.futures.ThreadPoolExecutor(max_workers=num_threads) as executor:
        futures = [executor.submit(make_confirm_request, i) for i in range(num_threads)]
        for f in concurrent.futures.as_completed(futures):
            results.append(f.result())

    # Verify database state: exactly ONE confirmed booking exists
    with Session() as session:
        confirmed_bookings = session.scalars(
            select(Booking).where(
                Booking.seat_id == target_seat_id,
                Booking.status == BookingStatus.CONFIRMED,
            )
        ).all()
        assert len(confirmed_bookings) == 1

    engine.dispose()
