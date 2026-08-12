"""
Database connection — SQLAlchemy engine + session factory.
Uses SQLite by default for local MVP (zero-config).
Swap DATABASE_URL env var to mysql+pymysql://... for MySQL.
"""
import os
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.db_models import Base
from app.utils.paths import ensure_user_data_path, get_user_data_path, is_frozen

# Default: SQLite file colocated with the backend in dev, in the
# per-user app-data folder under a PyInstaller bundle (where the cwd
# may not be writable). To use MySQL: set
#   DATABASE_URL="mysql+pymysql://user:pass@localhost/digital_twin"
# in which case this default is ignored.
_DEFAULT_SQLITE_NAME = "digital_twin.db"


def _default_sqlite_url() -> str:
    if is_frozen():
        ensure_user_data_path()
        return f"sqlite:///{(get_user_data_path() / _DEFAULT_SQLITE_NAME).as_posix()}"
    # Dev: keep the DB next to the backend/ source tree so a developer
    # running `uvicorn app.main:app` gets the same file the seed script
    # and tests use.
    return f"sqlite:///{(Path(__file__).resolve().parents[1] / _DEFAULT_SQLITE_NAME).as_posix()}"


DATABASE_URL = os.getenv("DATABASE_URL", _default_sqlite_url())

engine = create_engine(
    DATABASE_URL,
    # SQLite-only arg — remove if switching to MySQL
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {},
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    """FastAPI dependency — yields a DB session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Create all tables (called once at startup)."""
    Base.metadata.create_all(bind=engine)