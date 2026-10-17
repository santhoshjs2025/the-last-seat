# Concurrency, Correctness, and Horizontal Scaling

This document explores the architectural decisions, concurrency safety mechanisms, and scaling path for **The Last Seat** booking engine.

---

## 1. Why "Check-Then-Update" Without Row Locks is Unsafe

A naive ticket booking implementation typically follows this sequence:
```python
# BROKEN / RACE CONDITION PRONE:
seat = db.query(Seat).filter_by(id=seat_id).first()
if seat.status == "AVAILABLE":
    # Context switch or competing thread runs here!
    seat.status = "RESERVED"
    db.commit()
```
### Race Condition Mechanics:
When 1,000 users attempt to reserve Seat `A001` simultaneously:
1. All 1,000 threads execute `SELECT` at time $T_0$.
2. Every thread reads `status = 'AVAILABLE'`.
3. Every thread enters the `if` branch.
4. Every thread executes `UPDATE seats SET status = 'RESERVED'`.
5. 1,000 reservations are created for the exact same seat, causing catastrophic overselling.

Python in-memory locks (like `threading.Lock` or `asyncio.Lock`) **cannot** solve this problem because:
- In production, FastAPI runs multiple worker processes (`uvicorn -w 4`).
- When scaling horizontally, multiple containers/instances run on separate servers.
- In-memory state is isolated per process and invisible across nodes.

---

## 2. PostgreSQL Row Locks (`SELECT FOR UPDATE`)

To enforce safety across all worker processes and server nodes, concurrency protection must be delegated to the database engine.

In **The Last Seat**, reserving a seat uses PostgreSQL's row-level locking:
```sql
BEGIN;
SELECT * FROM seats WHERE id = :seat_id FOR UPDATE;
-- PostgreSQL grants lock to exactly ONE transaction; all others block until commit/rollback.
-- Revalidate availability:
-- If AVAILABLE: create reservation, update seat to RESERVED, COMMIT;
-- If NOT AVAILABLE: ROLLBACK;
```

### Consistent Lock Hierarchy (Deadlock Prevention):
To prevent database deadlocks (`40P01 deadlocks detected`), all transactions acquire locks in a strict global order:
$$\text{Seat} \longrightarrow \text{Reservation} \longrightarrow \text{Booking} \longrightarrow \text{Payment}$$

---

## 3. Database Constraints as the Ultimate Invariant Safeguard

Application code can have bugs, but relational databases provide mathematically guaranteed invariants.

### Partial Unique Index on Confirmed Bookings:
```sql
CREATE UNIQUE INDEX uq_seat_active_confirmed_booking
ON bookings (seat_id)
WHERE status = 'CONFIRMED';
```
- A seat can have unlimited cancelled bookings in historical logs (`status = 'CANCELLED'`).
- The database engine physically rejects any attempt to insert a second row with `status = 'CONFIRMED'` for the same `seat_id`, throwing a unique constraint violation error (`23505`).

---

## 4. Idempotency Key Architecture

Network glitches often cause clients to retry requests whose responses were lost in transit.
Every confirmation request requires an `Idempotency-Key` header (e.g. UUIDv4).

1. The payment record stores `idempotency_key` as a `UNIQUE` column.
2. A cryptographic SHA-256 hash of `(reservation_id, outcome, amount)` is stored alongside.
3. If an identical key arrives:
   - **Matching Payload**: Returns the existing payment and booking status without reprocessing.
   - **Mismatched Payload**: Raises `409 Conflict`, preventing key hijacking.

---

## 5. Short Transactions vs Long Delays

Holding a database row lock during an external network call (such as a payment gateway or simulated sleep) is an anti-pattern that exhausts connection pools.

### The Delayed Payment State Machine:
1. **Transaction 1 (Sub-millisecond)**:
   - Checks reservation.
   - Inserts `Payment(status=PENDING)`.
   - Commits immediately, releasing all row locks.
   - Responds with `HTTP 202 Accepted`.
2. **Asynchronous Waiting**:
   - Background worker sleeps outside any database transaction.
3. **Transaction 2**:
   - Re-acquires row locks on `Payment`, `Reservation`, and `Seat`.
   - Re-checks if the reservation expired during the delay.
   - If expired: marks `Payment` as `EXPIRED` and frees the seat.
   - If valid: commits `CONFIRMED` booking.

---

## 6. Horizontal Scaling & Architectural Limitations

### Current Architecture:
- Single PostgreSQL database instance.
- Stateless FastAPI backend replicas.
- Background worker runs as an in-process `asyncio` task.

### Limitations of In-Process Workers:
- **No Persistence Across Crashes**: If a container crashes while a delayed payment is sleeping in memory, the in-flight task is lost (though the database keeps it as `PENDING`).
- **Duplicate Work Across Replicas**: If 10 container replicas run the in-process `expiry_worker`, all 10 query the database periodically. While our row locking prevents corrupt writes, it wastes database query cycles.
- **Not a Distributed Scheduler**: An `asyncio.create_task` is local to the OS process.

### Production Scaling Roadmap:
1. **Distributed Queue (Celery / ARQ / Temporal with Redis or RabbitMQ)**:
   - Replace `BackgroundTasks` with durable job queues.
   - Delayed payments become scheduled delayed tasks in Redis/RabbitMQ.
   - Tasks survive application restarts and are distributed evenly across worker pools.
2. **Read Replicas & Connection Pooling**:
   - Deploy **PgBouncer** in transaction pooling mode between FastAPI and PostgreSQL to handle tens of thousands of client connections with minimal database backend processes.
   - Route seat browsing (`GET /api/v1/seats/available`) to PostgreSQL read replicas, while write transactions (`POST /reservations`) target the primary node.
3. **Redis Caching for Seat Availability**:
   - Cache seat availability bitmaps in Redis.
   - Use Redis `DECR` or Lua scripts as a fast front-door filter, backed by PostgreSQL as the authoritative source of truth.
