# Entity-Relationship Diagram (ERD) - The Last Seat

This document defines the relational database architecture and integrity constraints for **The Last Seat** high-concurrency ticket booking engine.

## Mermaid ER Diagram

```mermaid
erDiagram
    SEAT ||--o{ RESERVATION : "has temporary holds"
    SEAT ||--o{ BOOKING : "has confirmed/cancelled records"
    RESERVATION ||--o| BOOKING : "transitions to"
    RESERVATION ||--o{ PAYMENT : "attempted transactions"
    BOOKING ||--o{ PAYMENT : "settled with"

    SEAT {
        int id PK "Autoincrement ID"
        string seat_number UK "Unique e.g. A001..A500"
        string status "AVAILABLE | RESERVED | BOOKED"
        timestamp created_at "UTC timestamp"
        timestamp updated_at "UTC timestamp"
    }

    RESERVATION {
        uuid id PK "UUID primary key"
        string user_id "User identifier"
        int seat_id FK "References seats.id"
        string status "ACTIVE | CONFIRMED | EXPIRED | CANCELLED"
        timestamp created_at "UTC timestamp"
        timestamp expires_at "Expiry deadline (created_at + 5 min)"
        timestamp updated_at "UTC timestamp"
    }

    BOOKING {
        uuid id PK "UUID primary key"
        uuid reservation_id FK,UK "1-to-1 unique hold"
        string user_id "User identifier"
        int seat_id FK "References seats.id"
        string status "CONFIRMED | CANCELLED"
        timestamp created_at "UTC timestamp"
        timestamp updated_at "UTC timestamp"
    }

    PAYMENT {
        uuid id PK "UUID primary key"
        uuid reservation_id FK "References reservations.id"
        uuid booking_id FK "References bookings.id (nullable)"
        string idempotency_key UK "Client deduplication key"
        decimal amount "Booking fee"
        string status "PENDING | SUCCESS | FAILED | EXPIRED"
        int simulated_delay_seconds "Delay parameter"
        string payload_hash "Hash of reservation, outcome, and amount"
        timestamp created_at "UTC timestamp"
        timestamp updated_at "UTC timestamp"
    }
```

## Key Database Constraints & Invariants

1. **Active Confirmed Booking Uniqueness (PostgreSQL Partial Unique Index)**:
   ```sql
   CREATE UNIQUE INDEX uq_seat_active_confirmed_booking
   ON bookings (seat_id)
   WHERE status = 'CONFIRMED';
   ```
   *Guarantees*: A seat can have multiple historical `CANCELLED` bookings, but at most **one** `CONFIRMED` booking can ever exist concurrently.

2. **Idempotency Key Uniqueness**:
   ```sql
   ALTER TABLE payments ADD CONSTRAINT uq_payments_idempotency_key UNIQUE (idempotency_key);
   ```
   *Guarantees*: Prevents double-charging or duplicate confirmation runs even under aggressive network retries.

3. **Foreign Key Integrity**:
   - `reservations.seat_id` -> `seats.id` (`ON DELETE CASCADE`)
   - `bookings.reservation_id` -> `reservations.id` (`ON DELETE RESTRICT`)
   - `bookings.seat_id` -> `seats.id` (`ON DELETE RESTRICT`)
   - `payments.booking_id` -> `bookings.id` (`ON DELETE SET NULL`)
   - `payments.reservation_id` -> `reservations.id` (`ON DELETE CASCADE`)
