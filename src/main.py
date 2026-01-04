"""Main FastAPI application entry point for Lumiera WhatsApp Copilot."""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import os

from src.config import settings
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

    yield

    # Shutdown
    log.info("Shutting down Lumiera WhatsApp Copilot")


# Create FastAPI app
app = FastAPI(
    title="Lumiera WhatsApp Copilot",
    description="WhatsApp-first agentic copilot for construction subcontractors",
    version="1.0.0",
    lifespan=lifespan,
)

# Store config in app state
app.state.config = settings

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
