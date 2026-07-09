"""Database engine and session management."""
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from .config import DATABASE_URL

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False, "timeout": 30},
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

Base = declarative_base()


def get_db():
    """Yield a request-scoped database session."""
    db = SessionLocal()
    try:
        yield db
    except Exception:
        # Bug 36 fix: always roll back the session on any exception so the
        # underlying connection is returned to the pool in a clean state.
        db.rollback()
        raise
    finally:
        db.close()
