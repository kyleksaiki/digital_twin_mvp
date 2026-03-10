"""
Database connection — SQLAlchemy engine + session factory.
Uses SQLite by default for local MVP (zero-config).
Swap DATABASE_URL env var to mysql+pymysql://... for MySQL.
"""
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.db_models import Base

# Default: SQLite file in backend/ directory (no MySQL install needed for MVP)
# To use MySQL: export DATABASE_URL="mysql+pymysql://user:pass@localhost/digital_twin"
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./digital_twin.db")

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