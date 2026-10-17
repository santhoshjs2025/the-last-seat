import os
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# Ensure test environment variables are set before importing any app modules
os.environ["ENVIRONMENT"] = "testing"
os.environ["DATABASE_URL"] = "sqlite:///./test_suite.db"
os.environ["RESERVATION_EXPIRY_MINUTES"] = "5"
os.environ["ADMIN_API_KEY"] = "test-admin-key"

from app.core.config import settings
settings.ENVIRONMENT = "testing"
settings.DATABASE_URL = "sqlite:///./test_suite.db"
settings.ADMIN_API_KEY = "test-admin-key"

from app.db.database import Base, get_db
from app.db.models import Seat, SeatStatus
from app.main import app

test_engine = create_engine(
    "sqlite:///./test_suite.db",
    connect_args={"check_same_thread": False},
)

TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


@pytest.fixture(scope="session", autouse=True)
def setup_test_db():
    Base.metadata.drop_all(bind=test_engine)
    Base.metadata.create_all(bind=test_engine)
    with TestingSessionLocal() as session:
        # Seed exactly 500 test seats
        seats = [
            Seat(id=i, seat_number=f"A{i:03d}", status=SeatStatus.AVAILABLE)
            for i in range(1, 501)
        ]
        session.add_all(seats)
        session.commit()
    yield
    Base.metadata.drop_all(bind=test_engine)
    test_engine.dispose()
    if os.path.exists("./test_suite.db"):
        try:
            os.remove("./test_suite.db")
        except Exception:
            pass


@pytest.fixture(scope="function", autouse=True)
def clean_state():
    """Ensure each test starts with empty transactions and all 500 seats available."""
    yield
    with TestingSessionLocal() as session:
        session.execute(text("DELETE FROM payments"))
        session.execute(text("DELETE FROM bookings"))
        session.execute(text("DELETE FROM reservations"))
        session.execute(text("UPDATE seats SET status = 'AVAILABLE'"))
        session.commit()


@pytest.fixture(scope="function")
def db_session():
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(scope="function")
def client():
    def override_get_db():
        session = TestingSessionLocal()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
