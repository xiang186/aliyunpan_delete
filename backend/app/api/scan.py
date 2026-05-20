"""
Scan API routes.

Endpoints:
  POST /api/scan/start              — Start a duplicate-file scan task
  GET  /api/scan/progress/{task_id} — SSE stream of scan progress events

Requirements: 2.1, 2.2, 2.3, 2.4, 2.5
"""
from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.rate_limiter import RateLimiter, RateLimitConfig
from app.db.database import get_db
from app.services.aliyun_client import AliyunDriveClient
from app.services.auth_service import AuthService
from app.services.scan_service import ScanService

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class StartScanRequest(BaseModel):
    """Body for POST /api/scan/start."""

    session_id: str | None = None


# ---------------------------------------------------------------------------
# Dependency helpers
# ---------------------------------------------------------------------------


def get_scan_service(db: AsyncSession = Depends(get_db)) -> ScanService:
    """
    FastAPI dependency that constructs a ``ScanService`` for the current request.

    Mirrors the pattern used in auth.py.
    """
    rate_limiter = RateLimiter(RateLimitConfig(
        interval_ms=settings.api_call_interval_ms,
        max_retries=settings.api_max_retries,
        max_backoff_seconds=settings.api_max_backoff_seconds,
    ))
    aliyun_client = AliyunDriveClient(settings, rate_limiter)
    auth_service = AuthService(db, settings, aliyun_client)
    return ScanService(auth_service, aliyun_client)


def get_session_id(
    session_id: str | None = Query(default=None),
    x_session_id: str | None = Header(default=None, alias="X-Session-ID"),
) -> str | None:
    """
    Resolve the session ID from the query parameter or the X-Session-ID header.

    Query parameter takes precedence; the header is a fallback.
    """
    return session_id or x_session_id


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post("/start", summary="Start a duplicate-file scan task")
async def start_scan(
    body: StartScanRequest | None = None,
    session_id_header: str | None = Depends(get_session_id),
    scan_service: ScanService = Depends(get_scan_service),
) -> JSONResponse:
    """
    Start a background scan task that pages through all duplicate files.

    The session ID is read from the request body (``session_id`` field),
    the ``session_id`` query parameter, or the ``X-Session-ID`` header —
    in that order of precedence.

    Returns a ``task_id`` that the client should use to open the SSE stream.

    **Requirements 2.1, 2.2**
    """
    # Resolve session_id: body > query/header
    resolved_session_id = (
        (body.session_id if body else None)
        or session_id_header
    )

    if not resolved_session_id:
        raise HTTPException(
            status_code=400,
            detail="session_id is required (body field, query param, or X-Session-ID header).",
        )

    task_id = await scan_service.start_scan(resolved_session_id)
    logger.info("Scan task %s started for session %s", task_id, resolved_session_id)
    return JSONResponse(content={"task_id": task_id})


@router.post("/pause/{task_id}", summary="Pause a running scan")
async def pause_scan(
    task_id: str,
    scan_service: ScanService = Depends(get_scan_service),
) -> JSONResponse:
    from app.services.scan_service import _scan_running
    if task_id not in _scan_running:
        raise HTTPException(status_code=404, detail=f"Scan task '{task_id}' not found.")
    scan_service.pause_scan(task_id)
    return JSONResponse(content={"status": "paused"})


@router.post("/resume/{task_id}", summary="Resume a paused scan")
async def resume_scan(
    task_id: str,
    scan_service: ScanService = Depends(get_scan_service),
) -> JSONResponse:
    from app.services.scan_service import _scan_running
    if task_id not in _scan_running:
        raise HTTPException(status_code=404, detail=f"Scan task '{task_id}' not found.")
    scan_service.resume_scan(task_id)
    return JSONResponse(content={"status": "resumed"})


@router.post("/stop/{task_id}", summary="Stop a scan and return partial results")
async def stop_scan(
    task_id: str,
    scan_service: ScanService = Depends(get_scan_service),
) -> JSONResponse:
    from app.services.scan_service import _scan_running
    if task_id not in _scan_running:
        raise HTTPException(status_code=404, detail=f"Scan task '{task_id}' not found.")
    scan_service.stop_scan(task_id)
    return JSONResponse(content={"status": "stopping"})


@router.get("/progress/{task_id}", summary="SSE stream of scan progress")
async def scan_progress(
    task_id: str,
    scan_service: ScanService = Depends(get_scan_service),
) -> EventSourceResponse:
    """
    Stream scan progress events as Server-Sent Events (SSE).

    Each event has a named ``event`` field (``progress``, ``complete``, or
    ``error``) and a JSON-encoded ``data`` payload.

    The stream terminates automatically after a ``complete`` or ``error``
    event is sent.

    Reconnecting after a page refresh is supported: if the task is still
    running the client will receive subsequent progress events; if it has
    already finished the cached ``complete`` event is replayed immediately.

    **Requirements 2.2, 2.3, 2.4, 2.5**
    """
    from app.services.scan_service import _scan_queues, _scan_results, _scan_running

    task_known = task_id in _scan_queues or task_id in _scan_results
    if not task_known:
        raise HTTPException(status_code=404, detail=f"Scan task '{task_id}' not found.")

    async def event_generator():
        async for event_dict in scan_service.get_scan_events(task_id):
            event_type = event_dict.get("event", "message")
            # Yield in sse_starlette format: dict with "event" and "data" keys
            yield {
                "event": event_type,
                "data": json.dumps(event_dict),
            }

    return EventSourceResponse(event_generator())
