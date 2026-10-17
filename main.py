import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, status
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.core.config import settings
from app.db.database import get_db, engine, Base
from app.db.init_db import init_seats
from app.db.models import utc_now
from app.schemas.schemas import HealthResponse
from app.api import api_v1_router
from app.workers.expiry_worker import start_expiry_worker, stop_expiry_worker

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("the_last_seat")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Manages application startup and shutdown lifecycle:
    - Automatically creates tables if not present
    - Seeds 500 seats idempotently
    - Starts the background reservation expiry worker
    - Stops the worker cleanly on application shutdown
    """
    if settings.ENVIRONMENT != "testing":
        logger.info("Initializing application resources...")
        try:
            Base.metadata.create_all(bind=engine)
            init_seats(settings.TOTAL_SEATS)
        except Exception as e:
            logger.error(f"Error initializing database during startup: {e}", exc_info=True)

        start_expiry_worker()
        yield
        await stop_expiry_worker()
        logger.info("Application shutdown complete.")
    else:
        yield


app = FastAPI(
    title="The Last Seat - Ticket Booking API",
    description=(
        "Production-minded high-concurrency ticket booking backend for 500 concert seats "
        "and 10,000 potential concurrent users with robust PostgreSQL row-locking, "
        "idempotency, automated expiry, and simulated payment state machine."
    ),
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# Enable CORS for external testing and web dashboards
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", response_model=HealthResponse, tags=["Health"])
def health_check(db: Session = Depends(get_db)):
    """
    Application health and database connectivity probe.
    """
    now = utc_now()
    try:
        db.execute(text("SELECT 1"))
        return HealthResponse(
            status="healthy",
            database="connected",
            timestamp=now,
        )
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "status": "unhealthy",
                "database": "disconnected",
                "timestamp": now.isoformat(),
                "error": str(e),
            },
        )


# Register all API endpoints
app.include_router(api_v1_router)
