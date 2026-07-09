"""CoWork API application entrypoint."""
from fastapi import FastAPI

from .database import Base, engine
from .errors import AppError, app_error_handler
from .routers import admin, auth, bookings, health, rooms

Base.metadata.create_all(bind=engine)

app = FastAPI(title="CoWork API", version="1.0.0")

# Seed the reference-code counter from the database on startup so codes
# remain monotonically increasing across server restarts.
# Note: stats no longer require seeding because stats.get() now queries
# the database directly on every request (Bug 17/46 fix).
from sqlalchemy.orm import Session
from .database import SessionLocal
from .models import Booking
from .services import reference


def _init_startup_state():
    db: Session = SessionLocal()
    try:
        max_ref = (
            db.query(Booking.reference_code)
            .order_by(Booking.reference_code.desc())
            .first()
        )
        if max_ref and max_ref[0] and max_ref[0].startswith("CW-"):
            try:
                num = int(max_ref[0][3:])
                reference._counter["value"] = num + 1
            except ValueError:
                pass
    except Exception:
        pass
    finally:
        db.close()


_init_startup_state()

app.add_exception_handler(AppError, app_error_handler)

app.include_router(health.router)
app.include_router(auth.router)
app.include_router(rooms.router)
app.include_router(bookings.router)
app.include_router(admin.router)
