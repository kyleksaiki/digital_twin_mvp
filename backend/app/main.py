import os
from dotenv import load_dotenv

# Load environment variables FIRST, before any other imports
load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routes import runs
from app.routes import network
from app.routes import ai
from app.routes import export
from app.routes import audio
from app.routes import battery
from app.routes import vision
from app.database import init_db
from app.seed import seed

app = FastAPI(
    title="Digital Twin API",
    description="Backend for Digital Twin simulation analysis platform",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],
)

app.include_router(runs.router)
app.include_router(network.router)
app.include_router(ai.router)
app.include_router(export.router)
app.include_router(audio.router)
app.include_router(battery.router)
app.include_router(vision.router)


@app.on_event("startup")
def on_startup():
    """Create tables and seed mock data when enabled."""
    init_db()
    seed_enabled = os.getenv("SEED_MOCK_DATA", "").lower() in {"1", "true", "yes"}
    if seed_enabled:
        seed()


@app.get("/health")
def health_check():
    return {"status": "ok"}