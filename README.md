# The Last Seat - High Concurrency Ticket Booking Backend

A production-minded, concurrency-safe ticket booking backend built with **FastAPI**, **PostgreSQL**, **SQLite** (for local demo), and **SQLAlchemy 2.x**. Designed for a high-demand college concert with **500 seats** and **10,000 potential concurrent users**, preventing double bookings, managing temporary reservations with automatic expiry, supporting idempotent payments, and ensuring atomic seat reallocation.

---

## 1. Project Overview & Features

- **500-Seat Inventory**: Automatically initialized with human-readable seat numbers (`A001` through `A500`).
- **Pessimistic Row-Level Locking (`SELECT FOR UPDATE`) on PostgreSQL**: Eliminates race conditions at the database row level for production workloads.
- **Database-Level Partial Unique Constraints**:
  - `uq_seat_active_confirmed_booking`: Ensures at the database engine level that no seat can ever have more than one active `CONFIRMED` booking.
  - `uq_seat_active_reservation`: Ensures at the database engine level that no seat can ever have more than one concurrent `ACTIVE` reservation.
- **Dual-Database Architecture**:
  - **PostgreSQL**: Production deployment with Docker Compose, row-level locking (`SELECT FOR UPDATE`), and connection pooling.
  - **SQLite**: Standalone local demo execution without requiring Docker or a local PostgreSQL installation, configured with WAL journal mode, busy timeouts, and enforced foreign keys.
- **5-Minute Temporary Reservations**: Seats are held temporarily while payment proceeds.
- **Dual Expiry Strategy**:
  - **Background Worker**: Periodically checks and frees stale reservations.
  - **Lazy Expiry**: On-demand checks during seat availability queries and confirmation attempts.
- **Payment Simulation State Machine**:
  - `SUCCESS`: Confirms booking and marks seat `BOOKED`.
  - `FAILURE`: Aborts confirmation, marks reservation `CANCELLED`, and releases seat to `AVAILABLE`.
  - `DELAYED`: Commits pending payment immediately (releasing row locks) and executes asynchronously.
- **Idempotency Protection**: Unique `Idempotency-Key` header prevents duplicate bookings and duplicate payment processing.
- **Booking Cancellation & Reallocation**: Cancelling a confirmed booking immediately frees the seat for other users.
- **Administrative Telemetry**: Real-time aggregated statistics protected by an administrative API key.

---

## 2. Architecture & Tech Stack

- **Language**: Python 3.12+ (tested on Python 3.13)
- **Web Framework**: FastAPI (high-performance ASGI)
- **Server**: Uvicorn
- **ORM**: SQLAlchemy 2.x
- **Databases**:
  - **PostgreSQL 16** (Production & Docker, connected via `psycopg` 3)
  - **SQLite 3** (Local standalone demo with WAL mode and partial unique indexes)
- **Migrations**: Alembic
- **Validation**: Pydantic v2 & Pydantic-Settings
- **Testing**: Pytest & HTTPX
- **Load Testing**: Locust
- **Containerization**: Docker & Docker Compose

---

## 3. Quick-Start Guide (Windows PowerShell)

### Option A: Local Demo Mode (SQLite - No Docker or PostgreSQL Required)

If Docker or PostgreSQL is unavailable on your system, run the local demo directly with SQLite:

1. **Verify Environment Configuration (`.env`)**:
The `.env` file is pre-configured for local demo mode:
```ini
DATABASE_URL=sqlite:///./the_last_seat.db
ADMIN_API_KEY=admin-dev-key-change-in-production
RESERVATION_EXPIRY_MINUTES=5
EXPIRY_WORKER_INTERVAL_SECONDS=10
TOTAL_SEATS=500
```

2. **Initialize Exactly 500 Seats**:
```powershell
cd the-last-seat
python -m app.db.init_db
```
*Output: `INFO:__main__:Initialized 500 new seats out of 500.`* (Idempotent to run repeatedly).

3. **Start the FastAPI Application**:
```powershell
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

4. **Verify Health Endpoint (in a new PowerShell window)**:
```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/health" -Method Get | ConvertTo-Json
```
*Response:*
```json
{
  "status": "healthy",
  "database": "connected",
  "timestamp": "2026-10-17T09:35:04.341702Z"
}
```

- **Interactive Swagger Docs**: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- **Interactive ReDoc**: [http://127.0.0.1:8000/redoc](http://127.0.0.1:8000/redoc)

---

### Option B: Production Mode with Docker Compose (PostgreSQL)

When Docker Desktop is installed and running:

```powershell
cd the-last-seat
docker compose up --build
```

The database container will start, pass health checks, apply Alembic migrations, initialize the 500 seats idempotently, and launch the backend at `http://localhost:8000`.

---

## 4. API Endpoints Reference

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `GET` | `/health` | Application health and DB connectivity |
| `GET` | `/api/v1/seats` | List seats with pagination & status filter |
| `GET` | `/api/v1/seats/available` | List available seats with lazy expiry check |
| `GET` | `/api/v1/seats/{seat_id}` | Retrieve details for a specific seat |
| `POST` | `/api/v1/reservations` | Create temporary 5-minute seat reservation |
| `GET` | `/api/v1/reservations/{id}` | Get reservation status and countdown time |
| `POST` | `/api/v1/reservations/{id}/confirm` | Confirm reservation (Idempotency-Key required) |
| `POST` | `/api/v1/reservations/{id}/cancel` | Cancel active reservation and free seat |
| `GET` | `/api/v1/bookings/{id}` | Get booking details |
| `POST` | `/api/v1/bookings/{id}/cancel` | Cancel confirmed booking and release seat |
| `GET` | `/api/v1/users/{user_id}/bookings` | Get user booking history |
| `GET` | `/api/v1/payments/{payment_id}` | Retrieve payment status |
| `GET` | `/api/v1/admin/stats` | System telemetry (Requires `X-Admin-Key`) |

---

## 5. Walkthrough Examples (PowerShell)

### 1. View Available Seats
```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/v1/seats/available?limit=5" -Method Get | ConvertTo-Json
```

### 2. Reserve Seat #1
```powershell
$body = @{ user_id = "user_42"; seat_id = 1 } | ConvertTo-Json
$res = Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/v1/reservations" -Method Post -Body $body -ContentType "application/json"
$res | ConvertTo-Json
$resId = $res.id
```

### 3. Check Reservation Status & Remaining Time
```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/v1/reservations/$resId" -Method Get | ConvertTo-Json
```

### 4. Confirm Reservation (Simulate Payment SUCCESS)
```powershell
$headers = @{ "Idempotency-Key" = "pay-key-student-42" }
$body = @{
    payment_outcome = "SUCCESS"
    amount = 50.00
    simulated_delay_seconds = 0
} | ConvertTo-Json

$confirm = Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/v1/reservations/$resId/confirm" -Method Post -Headers $headers -Body $body -ContentType "application/json"
$confirm | ConvertTo-Json
$bookingId = $confirm.booking_id
```

### 5. Check User Booking History
```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/v1/users/user_42/bookings" -Method Get | ConvertTo-Json
```

### 6. Cancel Confirmed Booking (Releases Seat to Available)
```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/v1/bookings/$bookingId/cancel" -Method Post | ConvertTo-Json
```

### 7. Simulate Payment FAILURE (Releases Seat)
```powershell
# Reserve seat 2
$res2 = Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/v1/reservations" -Method Post -Body (@{ user_id = "user_43"; seat_id = 2 } | ConvertTo-Json) -ContentType "application/json"

# Confirm with FAILURE
$failHeaders = @{ "Idempotency-Key" = "pay-key-fail-001" }
$failBody = @{ payment_outcome = "FAILURE"; amount = 50.00 } | ConvertTo-Json
try {
    Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/v1/reservations/$($res2.id)/confirm" -Method Post -Headers $failHeaders -Body $failBody -ContentType "application/json"
} catch {
    $_.ErrorDetails.Message
}
```

### 8. Simulate DELAYED Payment
```powershell
# Reserve seat 3
$res3 = Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/v1/reservations" -Method Post -Body (@{ user_id = "user_44"; seat_id = 3 } | ConvertTo-Json) -ContentType "application/json"

# Confirm with DELAYED
$delayedHeaders = @{ "Idempotency-Key" = "pay-key-delayed-001" }
$delayedBody = @{ payment_outcome = "DELAYED"; simulated_delay_seconds = 3; amount = 50.00 } | ConvertTo-Json
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/v1/reservations/$($res3.id)/confirm" -Method Post -Headers $delayedHeaders -Body $delayedBody -ContentType "application/json" | ConvertTo-Json
```

---

## 6. Concurrency & Locking Mechanics

### PostgreSQL Concurrency (Production)
When multiple concurrent requests attempt to reserve the same seat in PostgreSQL:
1. Every request starts a database transaction and issues:
   ```sql
   SELECT * FROM seats WHERE id = :seat_id FOR UPDATE;
   ```
2. PostgreSQL grants the row lock to the first transaction. All other transactions wait.
3. The winner checks `seat.status == AVAILABLE`, creates the `Reservation`, sets `seat.status = RESERVED`, and commits.
4. The waiting transactions acquire the lock in turn, re-evaluate `seat.status`, discover it is `RESERVED`, rollback, and return `409 Conflict`.
5. No two active reservations can ever own the same seat.

### SQLite Concurrency & Invariants (Local Demo)
*Note on SQLite Semantics*: SQLite does **not** provide granular `SELECT FOR UPDATE` row locks. Instead, SQLite ensures safety through:
1. **Database-level serialization** with WAL mode (`PRAGMA journal_mode=WAL`) and `PRAGMA busy_timeout=30000`.
2. **Partial Unique Indexes**:
   ```sql
   CREATE UNIQUE INDEX uq_seat_active_confirmed_booking ON bookings (seat_id) WHERE status = 'CONFIRMED';
   CREATE UNIQUE INDEX uq_seat_active_reservation ON reservations (seat_id) WHERE status = 'ACTIVE';
   ```
   Even under multi-threaded SQLite execution, SQLite's storage engine enforces that only **one** `CONFIRMED` booking and at most **one** `ACTIVE` reservation can ever exist per `seat_id`. Any collision immediately triggers an `IntegrityError`, caught and converted to a safe `409 Conflict`.

---

## 7. Automated Testing Instructions

Run the pytest suite:
```powershell
cd the-last-seat
python -m pytest -v
```
*Current test results: 23 passed, 2 skipped (PostgreSQL concurrency tests requiring Docker).*

### Running PostgreSQL Concurrency Integration Tests:
When a live PostgreSQL server is running (e.g., via Docker Compose):
```powershell
$env:CONCURRENCY_TEST_DB_URL="postgresql+psycopg://postgres:postgres@localhost:5432/the_last_seat"
python -m pytest tests/test_concurrency.py -v
```

---

## 8. Load Testing Instructions

Run Locust to stress test concurrency across the 500-seat inventory:
```powershell
locust -f loadtest/locustfile.py --host http://127.0.0.1:8000
```
Open `http://localhost:8089` to view live throughput and latency graphs.
