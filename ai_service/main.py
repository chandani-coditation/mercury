"""AI service FastAPI application."""

import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

from ai_service.core import setup_logging, get_logger
from ai_service.api.v1 import router as v1_router
from ai_service.state import get_state_bus
from db.connection import init_db_pool, close_db_pool

load_dotenv()

# Setup logging
log_level = os.getenv("LOG_LEVEL", "INFO")
log_file = os.getenv(
    "LOG_FILE", None
)  # If set, uses exact path; otherwise auto-generates daily log
log_dir = os.getenv("LOG_DIR", None)  # Directory for log files (default: ./logs)
setup_logging(log_level=log_level, log_file=log_file, log_dir=log_dir, service_name="ai_service")
logger = get_logger(__name__)

app = FastAPI(
    title="NOC AI Service",
    version="1.0.0",
    description="AI-powered Network Operations Center for automated alert triage and resolution",
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Startup / shutdown hooks
@app.on_event("startup")
async def startup():
    """Initialize services on startup."""
    # Initialize database connection pool
    pool_min = int(os.getenv("DB_POOL_MIN", "2"))
    pool_max = int(os.getenv("DB_POOL_MAX", "10"))
    init_db_pool(min_size=pool_min, max_size=pool_max)

    # Start state bus
    bus = get_state_bus()
    await bus.start()
    logger.info("AI service started successfully")


@app.on_event("shutdown")
async def shutdown():
    """Cleanup on shutdown."""
    # Stop state bus
    bus = get_state_bus()
    await bus.stop()

    # Close database pool
    close_db_pool()
    logger.info("AI service shutdown complete")


# Include API v1 routes
app.include_router(v1_router)


if __name__ == "__main__":
    import uvicorn

    host = os.getenv("AI_SERVICE_HOST", "0.0.0.0")
    port = int(os.getenv("AI_SERVICE_PORT", "8001"))

    uvicorn.run(app, host=host, port=port)
