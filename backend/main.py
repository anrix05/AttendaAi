"""
backend/main.py — FastAPI Application Entrypoint
"""
import logging
from typing import Optional
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from backend.config import settings
from backend.database import init_db
from backend.routes.subjects import router as subjects_router
from backend.routes.attendance import router as attendance_router

# Configure clean logging without PII
logging.basicConfig(
    level=logging.INFO if settings.DEBUG else logging.WARNING,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("attendai")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: ensure tables are created
    init_db()
    logger.info("AttendAI database and tables initialized.")
    yield


app = FastAPI(
    title=settings.APP_NAME,
    version="2.0.0",
    description="VIT Attendance Digitization Platform",
    lifespan=lifespan,
)

# ── CORS ──────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── ROUTERS ───────────────────────────────────────────────────
app.include_router(subjects_router)
app.include_router(attendance_router)


# ── HEALTH & DIAGNOSTICS ENDPOINTS ─────────────────────────────
@app.get("/api/health")
def health_check():
    """Customer-facing health endpoint (branded as AttendAI Vision, no provider names)."""
    from backend.vision.engines import EngineManager
    chip, tooltip, _ = EngineManager().check_health()
    return {
        "status": "ok",
        "app": settings.APP_NAME,
        "engine_chip": chip,
        "engine_tooltip": tooltip,
        "database": "sqlite_connected",
    }


@app.get("/api/diagnostics")
def system_diagnostics():
    """Hidden system diagnostics endpoint (shows internal providers for admin review)."""
    from backend.vision.engines import EngineManager
    chip, tooltip, details = EngineManager().check_health()
    return {
        "status": "ok",
        "app": settings.APP_NAME,
        "engine_chip": chip,
        "engine_order": settings.ENGINE_ORDER,
        "engines": {
            k: {
                "ok": v.ok,
                "reason": v.reason,
                "provider_model": v.provider_model,
            }
            for k, v in details.items()
        },
        "recent_page_stats": EngineManager.get_recent_stats(),
    }


@app.post("/api/vision/clear-cache")
def clear_vision_cache(image_hash: Optional[str] = None):
    """Purge vision cache for a specific image hash or all entries."""
    from backend.vision.engines import EngineManager
    EngineManager().clear_cache(image_hash)
    return {"status": "ok", "cleared": image_hash or "all"}



# ── SAFE GLOBAL EXCEPTION HANDLER ─────────────────────────────
@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    if isinstance(exc, HTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail},
            headers=getattr(exc, "headers", None),
        )
    logger.error("Unhandled error processing %s: %s", request.url.path, str(exc), exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": f"Internal server error: {str(exc)}"},
    )