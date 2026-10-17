# API Examples & PowerShell Commands

All examples can be executed against `http://localhost:8000` using Windows PowerShell or bash `curl`.

---

## 1. Application Health Check

### PowerShell
```powershell
Invoke-RestMethod -Uri "http://localhost:8000/health" -Method Get | ConvertTo-Json
```
### Response (200 OK)
```json
{
  "status": "healthy",
  "database": "connected",
  "timestamp": "2026-10-17T08:00:00.123456Z"
}
```

---

## 2. List Available Seats

### PowerShell
```powershell
Invoke-RestMethod -Uri "http://localhost:8000/api/v1/seats/available?page=1&limit=5" -Method Get | ConvertTo-Json
```
### Response (200 OK)
```json
{
  "total": 500,
  "page": 1,
  "limit": 5,
  "items": [
    {
      "id": 1,
      "seat_number": "A001",
      "status": "AVAILABLE",
      "created_at": "2026-10-17T08:00:00Z",
      "updated_at": "2026-10-17T08:00:00Z"
    }
  ]
}
```

---

## 3. Temporarily Reserve a Seat

### PowerShell
```powershell
$body = @{ user_id = "student_001"; seat_id = 1 } | ConvertTo-Json
$res = Invoke-RestMethod -Uri "http://localhost:8000/api/v1/reservations" -Method Post -Body $body -ContentType "application/json"
$res | ConvertTo-Json
```
### Response (201 Created)
```json
{
  "id": "e42e1284-90a6-4b68-80f4-5cb8d203f191",
  "user_id": "student_001",
  "seat_id": 1,
  "seat_number": "A001",
  "status": "ACTIVE",
  "created_at": "2026-10-17T08:05:00Z",
  "expires_at": "2026-10-17T08:10:00Z",
  "updated_at": "2026-10-17T08:05:00Z",
  "remaining_seconds": 300
}
```

---

## 4. Confirm Reservation (Successful Payment)

### PowerShell
```powershell
$resId = "e42e1284-90a6-4b68-80f4-5cb8d203f191"
$headers = @{ "Idempotency-Key" = "pay-key-001" }
$body = @{
    payment_outcome = "SUCCESS"
    amount = 50.00
    simulated_delay_seconds = 0
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://localhost:8000/api/v1/reservations/$resId/confirm" -Method Post -Headers $headers -Body $body -ContentType "application/json" | ConvertTo-Json
```
### Response (200 OK)
```json
{
  "message": "Reservation confirmed successfully and seat booked.",
  "status": "SUCCESS",
  "reservation_id": "e42e1284-90a6-4b68-80f4-5cb8d203f191",
  "seat_id": 1,
  "seat_number": "A001",
  "booking_id": "3b29c9b7-1c6e-450f-bb7e-f6f7091da3c0",
  "payment": {
    "id": "84d5df62-6fe3-4db0-93cb-59bce29b1fbf",
    "reservation_id": "e42e1284-90a6-4b68-80f4-5cb8d203f191",
    "booking_id": "3b29c9b7-1c6e-450f-bb7e-f6f7091da3c0",
    "idempotency_key": "pay-key-001",
    "amount": "50.00",
    "status": "SUCCESS",
    "simulated_delay_seconds": 0,
    "created_at": "2026-10-17T08:05:10Z",
    "updated_at": "2026-10-17T08:05:10Z"
  },
  "booking": {
    "id": "3b29c9b7-1c6e-450f-bb7e-f6f7091da3c0",
    "reservation_id": "e42e1284-90a6-4b68-80f4-5cb8d203f191",
    "user_id": "student_001",
    "seat_id": 1,
    "seat_number": "A001",
    "status": "CONFIRMED",
    "created_at": "2026-10-17T08:05:10Z",
    "updated_at": "2026-10-17T08:05:10Z"
  }
}
```

---

## 5. Simulate Payment Failure

### PowerShell
```powershell
$headers = @{ "Idempotency-Key" = "pay-fail-key-002" }
$body = @{
    payment_outcome = "FAILURE"
    amount = 50.00
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://localhost:8000/api/v1/reservations/<reservation_id>/confirm" -Method Post -Headers $headers -Body $body -ContentType "application/json"
```
### Response (400 Bad Request)
```json
{
  "message": "Payment simulation failed. Reservation cancelled and seat released.",
  "status": "FAILED",
  "reservation_id": "<reservation_id>",
  "seat_id": 2,
  "seat_number": "A002",
  "booking_id": null
}
```

---

## 6. Simulate Delayed Payment

### PowerShell
```powershell
$headers = @{ "Idempotency-Key" = "pay-delayed-key-003" }
$body = @{
    payment_outcome = "DELAYED"
    simulated_delay_seconds = 5
    amount = 50.00
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://localhost:8000/api/v1/reservations/<reservation_id>/confirm" -Method Post -Headers $headers -Body $body -ContentType "application/json" | ConvertTo-Json
```
### Response (202 Accepted)
```json
{
  "message": "Payment processing started asynchronously. Check payment status for updates.",
  "status": "PENDING",
  "reservation_id": "<reservation_id>",
  "seat_id": 3,
  "booking_id": null,
  "payment": {
    "id": "e924a274-0f2c-4cfd-b2a6-b51cbb0ec028",
    "status": "PENDING",
    "simulated_delay_seconds": 5
  }
}
```

---

## 7. Cancel a Confirmed Booking

### PowerShell
```powershell
Invoke-RestMethod -Uri "http://localhost:8000/api/v1/bookings/<booking_id>/cancel" -Method Post | ConvertTo-Json
```
### Response (200 OK)
```json
{
  "id": "<booking_id>",
  "user_id": "student_001",
  "seat_id": 1,
  "seat_number": "A001",
  "status": "CANCELLED"
}
```

---

## 8. Administrative Statistics

### PowerShell
```powershell
$adminHeaders = @{ "X-Admin-Key" = "admin-dev-key-change-in-production" }
Invoke-RestMethod -Uri "http://localhost:8000/api/v1/admin/stats" -Method Get -Headers $adminHeaders | ConvertTo-Json
```
### Response (200 OK)
```json
{
  "timestamp": "2026-10-17T08:15:00Z",
  "seats": {
    "AVAILABLE": 498,
    "RESERVED": 1,
    "BOOKED": 1,
    "TOTAL": 500
  },
  "reservations": {
    "ACTIVE": 1,
    "CONFIRMED": 1,
    "EXPIRED": 0,
    "CANCELLED": 0
  },
  "bookings": {
    "CONFIRMED": 1,
    "CANCELLED": 0
  },
  "payments": {
    "PENDING": 0,
    "SUCCESS": 1,
    "FAILED": 0,
    "EXPIRED": 0
  }
}
```
