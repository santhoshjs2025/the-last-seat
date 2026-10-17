import uuid


def test_booking_retrieval_and_cancellation(client):
    # 1. Reserve seat
    res = client.post("/api/v1/reservations", json={"user_id": "user_301", "seat_id": 30})
    assert res.status_code == 201
    res_id = res.json()["id"]

    # 2. Confirm booking
    confirm_res = client.post(
        f"/api/v1/reservations/{res_id}/confirm",
        headers={"Idempotency-Key": f"key-{uuid.uuid4()}"},
        json={"payment_outcome": "SUCCESS", "amount": 50.00},
    )
    assert confirm_res.status_code == 200
    booking_id = confirm_res.json()["booking_id"]

    # 3. Retrieve booking
    b_res = client.get(f"/api/v1/bookings/{booking_id}")
    assert b_res.status_code == 200
    assert b_res.json()["id"] == booking_id
    assert b_res.json()["status"] == "CONFIRMED"

    # 4. User booking history
    hist_res = client.get("/api/v1/users/user_301/bookings")
    assert hist_res.status_code == 200
    items = hist_res.json()
    assert len(items) >= 1
    assert any(b["id"] == booking_id for b in items)

    # 5. Cancel booking
    cancel_res = client.post(f"/api/v1/bookings/{booking_id}/cancel")
    assert cancel_res.status_code == 200
    assert cancel_res.json()["status"] == "CANCELLED"

    # Verify seat is AVAILABLE again
    seat_res = client.get("/api/v1/seats/30")
    assert seat_res.json()["status"] == "AVAILABLE"

    # 6. Reallocate seat to a new user
    res2 = client.post("/api/v1/reservations", json={"user_id": "user_302", "seat_id": 30})
    assert res2.status_code == 201

    # 7. Cannot cancel already cancelled booking
    double_cancel = client.post(f"/api/v1/bookings/{booking_id}/cancel")
    assert double_cancel.status_code == 400


def test_admin_stats_endpoint(client):
    # Missing API key -> 401
    resp_unauth = client.get("/api/v1/admin/stats")
    assert resp_unauth.status_code == 401

    # With correct API key -> 200
    resp_auth = client.get("/api/v1/admin/stats", headers={"X-Admin-Key": "test-admin-key"})
    assert resp_auth.status_code == 200
    data = resp_auth.json()
    assert "seats" in data
    assert "reservations" in data
    assert "bookings" in data
    assert "payments" in data
    assert data["seats"]["TOTAL"] == 500
