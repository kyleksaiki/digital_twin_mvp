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


def _start_stdin_watchdog() -> None:
    """Daemon thread that terminates the backend if the parent Tauri pipe closes."""
    import sys
    import threading

    def _watch():
        try:
            sys.stdin.read()
        except Exception:
            pass
        finally:
            os._exit(0)

    t = threading.Thread(target=_watch, daemon=True)
    t.start()


def _serve() -> None:
    """Start uvicorn from inside the frozen sidecar."""
    import sys
    import uvicorn

    # Monitor parent stdin pipe so sidecar exits if parent crashes
    _start_stdin_watchdog()

    if getattr(sys, "frozen", False):
        sys.modules.setdefault("app.main", sys.modules["__main__"])
    host = os.getenv("BACKEND_HOST", "127.0.0.1")
    port = int(os.getenv("BACKEND_PORT", "8000"))
    uvicorn.run(
        "app.main:app",
        host=host,
        port=port,
        log_level=os.getenv("BACKEND_LOG_LEVEL", "info"),
    )


if __name__ == "__main__":
    import sys
    if "--serve" in sys.argv or getattr(sys, "frozen", False):
        _serve()
    else:
        print(
            "App imported. Run `uvicorn app.main:app --reload` for dev, "
            "or `python -m app.main --serve` to start uvicorn in-process.",
            flush=True,
        )