"""
FastAPI application entry point.
Registers all routers and configures CORS middleware.
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize resources on startup and clean up on shutdown."""
    # Initialize database on startup
    from app.db.database import init_db
    await init_db()
    yield
    # Cleanup (if needed) goes here


app = FastAPI(
    title="AliyunDrive Duplicate Cleaner",
    description="API for scanning and cleaning duplicate files on AliyunDrive",
    version="0.1.0",
    lifespan=lifespan,
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register API routers
from app.api import auth, scan, delete, tasks  # noqa: E402

app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(scan.router, prefix="/api/scan", tags=["scan"])
app.include_router(delete.router, prefix="/api/delete", tags=["delete"])
app.include_router(tasks.router, prefix="/api/tasks", tags=["tasks"])


@app.get("/health", tags=["health"])
async def health_check():
    """Health check endpoint."""
    return {"status": "ok"}
