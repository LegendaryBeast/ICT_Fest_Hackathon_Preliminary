"""CoWork API application entrypoint."""
from fastapi import FastAPI

from .database import Base, engine
from .errors import AppError, app_error_handler
from .routers import admin, auth, bookings, health, rooms

Base.metadata.create_all(bind=engine)

app = FastAPI(title="CoWork API", version="1.0.0")

# Initialize stats and reference counter from database on startup
from sqlalchemy import func
from .database import SessionLocal
from .models import Booking
from .services import stats, reference

def _init_startup_state():
    db = SessionLocal()
    try:
        # Populate stats._stats
        rows = (
            db.query(
                Booking.room_id,
                func.count(Booking.id).label("count"),
                func.sum(Booking.price_cents).label("revenue")
            )
            .filter(Booking.status == "confirmed")
            .group_by(Booking.room_id)
            .all()
        )
        for r_id, count, revenue in rows:
            stats._stats[r_id] = {
                "count": count,
                "revenue": int(revenue) if revenue is not None else 0
            }
        
        # Populate reference._counter
        max_ref = db.query(Booking.reference_code).order_by(Booking.reference_code.desc()).first()
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

