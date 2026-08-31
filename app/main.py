"""FastAPI application entry point."""

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pathlib import Path

from app.config import get_settings
from app.database import init_db
from app.routers.api import router as api_router
from app.services.scheduler import start_scheduler, stop_scheduler

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


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    # Startup
    logger.info("Starting Devin Automation System")
    init_db()
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
