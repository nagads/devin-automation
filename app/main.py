"""FastAPI application entry point."""

import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pathlib import Path

from app.config import get_settings
from app.database import init_db, get_db_context
from app.routers.api import router as api_router
from app.services.scheduler import start_scheduler, stop_scheduler
from app.services.orchestrator import Orchestrator

# Configure logging
settings = get_settings()
logging.basicConfig(
    level=getattr(logging, settings.log_level),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Templates
BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


async def check_sessions_on_startup():
    """Check and update status of any active Devin sessions on startup."""
    logger.info("Checking active Devin sessions on startup...")
    try:
        with get_db_context() as db:
            orchestrator = Orchestrator(db)
            result = await orchestrator.check_sessions()
            if result.get("status") == "no_active_sessions":
                logger.info("No active sessions to check")
            else:
                logger.info(f"Startup session check complete: {result}")
    except Exception as e:
        logger.error(f"Error checking sessions on startup: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    # Startup
    logger.info("Starting Devin Automation System")
    init_db()
    
    # Check active sessions to update stale statuses
    await check_sessions_on_startup()
    
    start_scheduler()
    
    yield
    
    # Shutdown
    logger.info("Shutting down Devin Automation System")
    stop_scheduler()


# Create FastAPI app
app = FastAPI(
    title="Devin Automation",
    description="Event-driven automation for Apache Superset bug remediation using Devin",
    version="1.0.0",
    lifespan=lifespan
)

# Include routers
app.include_router(api_router)


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    """Serve the dashboard UI."""
    return templates.TemplateResponse(request, "dashboard.html")


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
