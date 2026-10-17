import random
import uuid
from locust import HttpUser, task, between, tag


class ConcertGoerUser(HttpUser):
    """
    Simulates a concert attendee attempting to reserve and book concert seats.
    Exercises both normal browsing/booking and high-contention hotspot scenarios.
    """

    wait_time = between(0.1, 1.0)

    def on_start(self):
        """Initialize user profile with unique identifier."""
        self.user_id = f"user_{uuid.uuid4().hex[:8]}"
        self.current_reservation = None
        self.confirmed_bookings = []

    @task(3)
    @tag("browse")
    def browse_available_seats(self):
        """View currently available seats."""
        with self.client.get(
            "/api/v1/seats/available?page=1&limit=50",
            catch_response=True,
            name="/api/v1/seats/available",
        ) as resp:
            if resp.status_code == 200:
                resp.success()
            else:
                resp.failure(f"Failed to fetch available seats: {resp.status_code}")

    @task(5)
    @tag("reserve_general")
    def reserve_and_book_random_seat(self):
        """
        Attempts to reserve a random seat out of the 500-seat inventory,
        and proceeds to simulated payment and confirmation if successful.
        """
        target_seat_id = random.randint(1, 500)
        res_payload = {"user_id": self.user_id, "seat_id": target_seat_id}

        with self.client.post(
            "/api/v1/reservations",
            json=res_payload,
            catch_response=True,
            name="/api/v1/reservations [Create]",
        ) as resp:
            if resp.status_code == 201:
                resp.success()
                data = resp.json()
                res_id = data["id"]

                # Decide action: 80% confirm immediately, 10% cancel, 10% simulated delayed payment
                dice = random.random()
                idempotency_key = f"locust-key-{uuid.uuid4()}"

                if dice < 0.80:
                    # Confirm with payment success
                    with self.client.post(
                        f"/api/v1/reservations/{res_id}/confirm",
                        headers={"Idempotency-Key": idempotency_key},
                        json={"payment_outcome": "SUCCESS", "amount": 50.00},
                        catch_response=True,
                        name="/api/v1/reservations/{id}/confirm [Success]",
                    ) as confirm_resp:
                        if confirm_resp.status_code == 200:
                            confirm_resp.success()
                            b_id = confirm_resp.json().get("booking_id")
                            if b_id:
                                self.confirmed_bookings.append(b_id)
                        else:
                            confirm_resp.failure(f"Confirmation failed: {confirm_resp.status_code}")

                elif dice < 0.90:
                    # Cancel active reservation
                    with self.client.post(
                        f"/api/v1/reservations/{res_id}/cancel",
                        catch_response=True,
                        name="/api/v1/reservations/{id}/cancel",
                    ) as cancel_resp:
                        if cancel_resp.status_code == 200:
                            cancel_resp.success()
                        else:
                            cancel_resp.failure(f"Cancellation failed: {cancel_resp.status_code}")

                else:
                    # Delayed payment simulation
                    with self.client.post(
                        f"/api/v1/reservations/{res_id}/confirm",
                        headers={"Idempotency-Key": idempotency_key},
                        json={
                            "payment_outcome": "DELAYED",
                            "simulated_delay_seconds": 2,
                            "amount": 50.00,
                        },
                        catch_response=True,
                        name="/api/v1/reservations/{id}/confirm [Delayed]",
                    ) as delayed_resp:
                        if delayed_resp.status_code == 202:
                            delayed_resp.success()
                        else:
                            delayed_resp.failure(f"Delayed confirmation unexpected code: {delayed_resp.status_code}")

            elif resp.status_code == 409:
                # Conflict is expected and acceptable under high concurrency
                resp.success()
            else:
                resp.failure(f"Unexpected status code: {resp.status_code}")

    @task(2)
    @tag("hotspot")
    def hotspot_seat_competition(self):
        """
        Hotspot simulation: Many users compete for front-row seats 1 through 5.
        Tests high-frequency SELECT FOR UPDATE row-locking contention and guarantees.
        """
        hotspot_seat = random.randint(1, 5)
        with self.client.post(
            "/api/v1/reservations",
            json={"user_id": self.user_id, "seat_id": hotspot_seat},
            catch_response=True,
            name="/api/v1/reservations [Hotspot Contest]",
        ) as resp:
            if resp.status_code in (201, 409):
                # 201: Winner, 409: Graceful rejection
                resp.success()
            else:
                resp.failure(f"Hotspot failure: {resp.status_code}")

    @task(1)
    @tag("history")
    def view_booking_history(self):
        """Check booking history for user."""
        with self.client.get(
            f"/api/v1/users/{self.user_id}/bookings",
            catch_response=True,
            name="/api/v1/users/{id}/bookings",
        ) as resp:
            if resp.status_code == 200:
                resp.success()
            else:
                resp.failure(f"History retrieval failed: {resp.status_code}")
