"""
Delete API routes.

Endpoints:
  POST /api/delete/start              — Start a batch-delete task
  GET  /api/delete/progress/{task_id} — SSE stream of delete progress events

Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 9.4, 9.5, 9.6, 9.7, 9.8, 9.10
"""
from __future__ import annotations

import json
import logging
from typing import Literal

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
from app.services.delete_service import DeleteService, _delete_queues

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class FileMeta(BaseModel):
    """Metadata for a single file included in a delete request."""

    file_id: str
    file_name: str = ""
    file_path: str = ""
    file_size: int = 0


class StartDeleteRequest(BaseModel):
    """Body for POST /api/delete/start."""

    session_id: str | None = None
    file_ids: list[str]
    delete_type: Literal["trash", "permanent"]
    file_meta: list[FileMeta] | None = None


# ---------------------------------------------------------------------------
# Dependency helpers
# ---------------------------------------------------------------------------


def get_delete_service(db: AsyncSession = Depends(get_db)) -> DeleteService:
    """
    FastAPI dependency that constructs a ``DeleteService`` for the current request.

    Mirrors the pattern used in scan.py.
    """
    rate_limiter = RateLimiter(
        RateLimitConfig(
            interval_ms=settings.api_call_interval_ms,
            max_retries=settings.api_max_retries,
            max_backoff_seconds=settings.api_max_backoff_seconds,
        )
    )
    aliyun_client = AliyunDriveClient(settings, rate_limiter)
    auth_service = AuthService(db, settings, aliyun_client)
    return DeleteService(auth_service, aliyun_client)


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


@router.post("/start", summary="Start a batch-delete task")
async def start_delete(
    body: StartDeleteRequest,
    session_id_header: str | None = Depends(get_session_id),
    delete_service: DeleteService = Depends(get_delete_service),
) -> JSONResponse:
    """
    Start a background batch-delete task.

    The session ID is read from the request body (``session_id`` field),
    the ``session_id`` query parameter, or the ``X-Session-ID`` header —
    in that order of precedence.

    Returns a ``task_id`` that the client should use to open the SSE stream.

    **Requirements 5.1, 5.2, 9.4, 9.5**
    """
    # Resolve session_id: body > query/header
    resolved_session_id = body.session_id or session_id_header

    if not resolved_session_id:
        raise HTTPException(
            status_code=400,
            detail="session_id is required (body field, query param, or X-Session-ID header).",
        )

    if not body.file_ids:
        raise HTTPException(
            status_code=400,
            detail="file_ids must not be empty.",
        )

    # Convert FileMeta objects to plain dicts for the service layer.
    file_meta_dicts: list[dict] | None = None
    if body.file_meta:
        file_meta_dicts = [m.model_dump() for m in body.file_meta]

    task_id = await delete_service.start_delete(
        session_id=resolved_session_id,
        file_ids=body.file_ids,
        delete_type=body.delete_type,
        file_meta=file_meta_dicts,
    )

    logger.info(
        "Delete task %s started for session %s (%s, %d files)",
        task_id,
        resolved_session_id,
        body.delete_type,
        len(body.file_ids),
    )
    return JSONResponse(content={"task_id": task_id})


@router.get("/progress/{task_id}", summary="SSE stream of delete progress")
async def delete_progress(
    task_id: str,
    delete_service: DeleteService = Depends(get_delete_service),
) -> EventSourceResponse:
    """
    Stream delete progress events as Server-Sent Events (SSE).

    Each event has a named ``event`` field (``progress``, ``complete``, or
    ``error``) and a JSON-encoded ``data`` payload.

    The stream terminates automatically after a ``complete`` or ``error``
    event is sent.

    **Requirements 5.3, 5.4, 5.5, 9.6, 9.7, 9.8**
    """
    if task_id not in _delete_queues:
        raise HTTPException(
            status_code=404, detail=f"Delete task '{task_id}' not found."
        )

    async def event_generator():
        async for event_dict in delete_service.get_delete_events(task_id):
            event_type = event_dict.get("event", "message")
            yield {
                "event": event_type,
                "data": json.dumps(event_dict),
            }

    return EventSourceResponse(event_generator())
