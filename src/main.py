"""Main FastAPI application entry point for Lumiera WhatsApp Copilot."""

import asyncio
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from src.config import settings
from src.handlers.media import router as media_router
from src.handlers.webhook import router as webhook_router
from src.utils.logger import log

# Initialize Sentry if enabled
if settings.enable_sentry and settings.sentry_dsn:
    import sentry_sdk

    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.environment,
        traces_sample_rate=1.0 if settings.is_development else 0.1,
    )
    log.info("Sentry initialized")


# Initialize rate limiter
limiter = Limiter(key_func=get_remote_address)


async def fsm_cleanup_task():
    """Background task to clean up expired FSM records every 5 minutes."""
    from src.fsm.handlers import run_cleanup_task

    while True:
        try:
            await asyncio.sleep(5 * 60)  # Sleep 5 minutes
            if settings.enable_fsm:
                await run_cleanup_task()
                log.info("✅ FSM cleanup task completed")
        except Exception as e:
            log.error(f"❌ FSM cleanup task failed: {e}")
            # Continue running despite errors


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    # Startup
    log.info("=" * 60)
    log.info("Starting Lumiera WhatsApp Copilot")
    log.info(f"Environment: {settings.environment}")
    log.info(f"Debug mode: {settings.debug}")
    log.info(f"Port: {settings.port}")
    log.info("=" * 60)

    # Create logs directory if it doesn't exist
    os.makedirs("logs", exist_ok=True)

    # Set LangChain environment variables if tracing enabled
    if settings.langchain_tracing_v2 and settings.langchain_api_key:
        os.environ["LANGCHAIN_TRACING_V2"] = "true"
        os.environ["LANGCHAIN_API_KEY"] = settings.langchain_api_key
        os.environ["LANGCHAIN_PROJECT"] = settings.langchain_project
        log.info("LangChain tracing enabled")

    # FSM: Run session recovery on startup
    if settings.enable_fsm:
        try:
            from src.fsm.handlers import session_recovery_manager

            log.info("Running FSM session recovery...")
            stats = await session_recovery_manager.recover_on_startup()
            log.info(f"✅ FSM session recovery complete: {stats}")
        except Exception as e:
            log.error(f"❌ FSM session recovery failed: {e}")
            # Don't fail startup if recovery fails

        # Start background cleanup task
        cleanup_task = asyncio.create_task(fsm_cleanup_task())
        log.info("✅ FSM background cleanup task started (runs every 5 minutes)")
    else:
        log.info("FSM disabled - skipping session recovery and cleanup")
        cleanup_task = None

    yield

    # Shutdown
    log.info("Shutting down Lumiera WhatsApp Copilot")

    # Cancel background task
    if cleanup_task and not cleanup_task.done():
        cleanup_task.cancel()
        try:
            await cleanup_task
        except asyncio.CancelledError:
            log.info("FSM cleanup task cancelled")


# Create FastAPI app
app = FastAPI(
    title="Lumiera WhatsApp Copilot",
    description="WhatsApp-first agentic copilot for construction subcontractors",
    version="1.0.0",
    lifespan=lifespan,
)

# Store config and limiter in app state
app.state.config = settings
app.state.limiter = limiter

# Add rate limit exceeded handler
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore[arg-type]

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.is_development else [],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(webhook_router, tags=["webhooks"])
app.include_router(media_router, tags=["media"])


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "message": "Lumiera WhatsApp Copilot API",
        "version": "1.0.0",
        "status": "running",
        "environment": settings.environment,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "src.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.hot_reload and settings.is_development,
        log_level=settings.log_level.lower(),
    )
