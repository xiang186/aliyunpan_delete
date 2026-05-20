"""
Task history API routes.

Endpoints:
  GET /api/tasks              — List all tasks for a session (by started_at desc)
  GET /api/tasks/{task_id}    — Get task detail + per-file results

Requirements: 7.1, 7.2, 7.3, 9.9
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_db
from app.db.task_repository import TaskRepository

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Dependency helpers
# ---------------------------------------------------------------------------


def get_session_id(
    session_id: str | None = Query(default=None),
    x_session_id: str | None = Header(default=None, alias="X-Session-ID"),
) -> str | None:
    """Resolve session_id from query param or X-Session-ID header."""
    return session_id or x_session_id


def get_task_repo(db: AsyncSession = Depends(get_db)) -> TaskRepository:
    return TaskRepository(db)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("", summary="List task history for a session")
async def list_tasks(
    session_id: str | None = Depends(get_session_id),
    repo: TaskRepository = Depends(get_task_repo),
) -> JSONResponse:
    """
    Return all delete tasks for the given session, ordered by started_at desc.

    The session ID is read from the ``session_id`` query parameter or the
    ``X-Session-ID`` request header.  Returns 400 if neither is provided.

    **Requirements 7.1, 7.2, 9.9**
    """
    if not session_id:
        raise HTTPException(status_code=400, detail="session_id is required")

    summaries = await repo.list_tasks(session_id)
    return JSONResponse(
        content={
            "tasks": [
                {
                    "task_id": s.task_id,
                    "delete_type": s.delete_type,
                    "status": s.status,
                    "total_count": s.total_count,
                    "success_count": s.success_count,
                    "failed_count": s.failed_count,
                    "freed_bytes": s.freed_bytes,
                    "started_at": s.started_at,
                    "completed_at": s.completed_at,
                }
                for s in summaries
            ]
        }
    )


@router.get("/{task_id}", summary="Get task detail with per-file results")
async def get_task(
    task_id: str,
    repo: TaskRepository = Depends(get_task_repo),
) -> JSONResponse:
    """
    Return the task record and its per-file results.

    Returns 404 if the task does not exist.

    **Requirements 7.1, 7.3, 9.9**
    """
    task = await repo.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")

    files = await repo.get_task_files(task_id)

    return JSONResponse(
        content={
            "task": {
                "task_id": task.id,
                "delete_type": task.delete_type,
                "status": task.status,
                "total_count": task.total_count,
                "success_count": task.success_count,
                "failed_count": task.failed_count,
                "freed_bytes": task.freed_bytes,
                "started_at": task.started_at,
                "completed_at": task.completed_at,
            },
            "files": [
                {
                    "file_id": f.file_id,
                    "file_name": f.file_name,
                    "file_path": f.file_path,
                    "file_size": f.file_size,
                    "result": f.result,
                    "error_msg": f.error_msg,
                }
                for f in files
            ],
        }
    )
