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
    folder_ids: list[str] | None = None    # 指定扫描目录，None 表示全盘扫描
    folder_names: list[str] | None = None  # 对应 folder_ids 的目录名称，用于路径显示
    incremental: bool = False              # True = 增量扫描（跳过未变更目录）


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

    task_id = await scan_service.start_scan(
        resolved_session_id,
        folder_ids=body.folder_ids if body else None,
        folder_names=body.folder_names if body else None,
        incremental=body.incremental if body else False,
    )
    logger.info("Scan task %s started for session %s", task_id, resolved_session_id)
    return JSONResponse(content={"task_id": task_id})


@router.post("/pause/{task_id}", summary="Pause a running scan")
async def pause_scan(
    task_id: str,
    scan_service: ScanService = Depends(get_scan_service),
) -> JSONResponse:
    from app.services.scan_service import _scan_queues, _scan_running
    if task_id not in _scan_running and task_id not in _scan_queues:
        raise HTTPException(status_code=404, detail=f"Scan task '{task_id}' not found.")
    scan_service.pause_scan(task_id)
    return JSONResponse(content={"status": "paused"})


@router.post("/resume/{task_id}", summary="Resume a paused scan")
async def resume_scan(
    task_id: str,
    scan_service: ScanService = Depends(get_scan_service),
) -> JSONResponse:
    from app.services.scan_service import _scan_queues, _scan_running
    if task_id not in _scan_running and task_id not in _scan_queues:
        raise HTTPException(status_code=404, detail=f"Scan task '{task_id}' not found.")
    scan_service.resume_scan(task_id)
    return JSONResponse(content={"status": "resumed"})


@router.post("/stop/{task_id}", summary="Stop a scan and return partial results")
async def stop_scan(
    task_id: str,
    scan_service: ScanService = Depends(get_scan_service),
) -> JSONResponse:
    from app.services.scan_service import _scan_queues, _scan_running, _scan_stop_flags
    # If the task is already stopped/finished, return 200 (idempotent)
    if task_id not in _scan_running and task_id not in _scan_queues:
        # Check if a stop was already requested (race: stop flag set but finally not yet run)
        if _scan_stop_flags.get(task_id):
            return JSONResponse(content={"status": "stopping"})
        raise HTTPException(status_code=404, detail=f"Scan task '{task_id}' not found.")
    scan_service.stop_scan(task_id)
    return JSONResponse(content={"status": "stopping"})


@router.get("/folders", summary="List sub-folders in a directory")
async def list_folders(
    parent_id: str = Query(default="root", alias="parent_id"),
    parent_path: str = Query(default="", alias="parent_path"),
    session_id_param: str | None = Depends(get_session_id),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """
    Return the immediate sub-folders of *parent_id* (only folders, no files).

    Also writes the returned folders into folder_cache so they become
    immediately searchable without waiting for the background index build.
    """
    if not session_id_param:
        raise HTTPException(
            status_code=400,
            detail="session_id is required (query param or X-Session-ID header).",
        )

    rate_limiter = RateLimiter(RateLimitConfig(
        interval_ms=settings.api_call_interval_ms,
        max_retries=settings.api_max_retries,
        max_backoff_seconds=settings.api_max_backoff_seconds,
    ))
    aliyun_client = AliyunDriveClient(settings, rate_limiter)
    auth_service = AuthService(db, settings, aliyun_client)

    access_token = await auth_service.get_valid_access_token(session_id_param)
    drive_id = await aliyun_client.get_default_drive_id(access_token)
    folders = await aliyun_client.list_folders(access_token, drive_id, parent_file_id=parent_id)

    # Write lazily-loaded folders into folder_cache so they are searchable immediately.
    # This is best-effort — failures are silently ignored.
    try:
        user_id = await _resolve_user_id(session_id_param, db)
        from app.db.models import FolderCache
        from sqlalchemy.dialects.sqlite import insert as sqlite_insert
        rows = []
        for f in folders:
            folder_name = f.get("name", "")
            full_path = f"{parent_path}/{folder_name}" if parent_path else folder_name
            rows.append({
                "user_id": user_id,
                "file_id": f["file_id"],
                "name": folder_name,
                "parent_id": parent_id,
                "full_path": full_path,
                "has_children": 1 if f.get("has_children", True) else 0,
            })
        for row in rows:
            stmt = sqlite_insert(FolderCache).values(**row)
            stmt = stmt.on_conflict_do_update(
                index_elements=["user_id", "file_id"],
                set_={
                    "name": row["name"],
                    "parent_id": row["parent_id"],
                    "full_path": row["full_path"],
                    "has_children": row["has_children"],
                },
            )
            await db.execute(stmt)
        await db.commit()
    except Exception as cache_exc:
        logger.debug("list_folders: failed to cache results: %s", cache_exc)

    return JSONResponse(content={"folders": folders})


# ---------------------------------------------------------------------------
# Folder index (background crawl + search)
# ---------------------------------------------------------------------------

def _get_folder_index_service():
    from app.services.folder_index_service import FolderIndexService
    rate_limiter = RateLimiter(RateLimitConfig(
        interval_ms=settings.api_call_interval_ms,
        max_retries=settings.api_max_retries,
        max_backoff_seconds=settings.api_max_backoff_seconds,
    ))
    aliyun_client = AliyunDriveClient(settings, rate_limiter)
    return FolderIndexService(aliyun_client)


async def _resolve_user_id(session_id: str, db: AsyncSession) -> str:
    from sqlalchemy import select as sa_select
    from app.db.models import UserSession
    result = await db.execute(
        sa_select(UserSession.user_id).where(UserSession.id == session_id)
    )
    user_id = result.scalar_one_or_none()
    if user_id is None:
        raise HTTPException(status_code=401, detail="Session not found.")
    return user_id


@router.get("/folder-index/status", summary="Get folder index build status")
async def folder_index_status(
    session_id_param: str | None = Depends(get_session_id),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """Return the current folder index status for the authenticated user."""
    if not session_id_param:
        raise HTTPException(status_code=400, detail="session_id is required.")
    user_id = await _resolve_user_id(session_id_param, db)
    svc = _get_folder_index_service()
    status = await svc.get_status(user_id)
    return JSONResponse(content=status)


@router.post("/folder-index/build", summary="Start background folder index build")
async def folder_index_build(
    session_id_param: str | None = Depends(get_session_id),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """Trigger a background crawl to build the folder index for the user."""
    if not session_id_param:
        raise HTTPException(status_code=400, detail="session_id is required.")
    user_id = await _resolve_user_id(session_id_param, db)

    rate_limiter = RateLimiter(RateLimitConfig(
        interval_ms=settings.api_call_interval_ms,
        max_retries=settings.api_max_retries,
        max_backoff_seconds=settings.api_max_backoff_seconds,
    ))
    aliyun_client = AliyunDriveClient(settings, rate_limiter)
    auth_service = AuthService(db, settings, aliyun_client)
    access_token = await auth_service.get_valid_access_token(session_id_param)
    drive_id = await aliyun_client.get_default_drive_id(access_token)

    from app.services.folder_index_service import FolderIndexService
    svc = FolderIndexService(aliyun_client)
    result = await svc.start_build(session_id_param, user_id, drive_id)
    return JSONResponse(content=result)


@router.get("/folder-index/search", summary="Search folders by keyword")
async def folder_index_search(
    q: str = Query(default="", description="Search keyword"),
    limit: int = Query(default=50, ge=1, le=200),
    session_id_param: str | None = Depends(get_session_id),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """Search cached folders by name (case-insensitive substring match)."""
    if not session_id_param:
        raise HTTPException(status_code=400, detail="session_id is required.")
    user_id = await _resolve_user_id(session_id_param, db)
    svc = _get_folder_index_service()
    results = await svc.search(user_id, q, limit=limit)
    return JSONResponse(content={"folders": results})


@router.delete("/scan-cache", summary="Clear incremental scan cache for the current user")
async def clear_scan_cache(
    session_id_param: str | None = Depends(get_session_id),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """
    Delete all scanned_folder records for the authenticated user.

    This forces the next scan to perform a full traversal regardless of
    whether incremental mode is selected.  Useful when the cached folder
    state has become stale or inconsistent.
    """
    if not session_id_param:
        raise HTTPException(status_code=400, detail="session_id is required.")
    user_id = await _resolve_user_id(session_id_param, db)

    from sqlalchemy import delete as sa_delete
    from app.db.models import ScannedFolder

    result = await db.execute(
        sa_delete(ScannedFolder).where(ScannedFolder.user_id == user_id)
    )
    await db.commit()
    deleted_count = result.rowcount
    logger.info("Cleared scan cache for user %s: %d rows deleted", user_id, deleted_count)
    return JSONResponse(content={"deleted_count": deleted_count})


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
