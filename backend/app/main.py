import os
from dotenv import load_dotenv

# Load environment variables FIRST, before any other imports
load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routes import runs, network, ai
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
)

app.include_router(runs.router)
app.include_router(network.router)
app.include_router(ai.router)


@app.on_event("startup")
def on_startup():
    """Create tables and seed mock data on first run."""
    init_db()
    seed()


@app.get("/health")
def health_check():
    return {"status": "ok"}