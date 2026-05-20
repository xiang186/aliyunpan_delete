"""
Task history repository.

Provides CRUD operations for Task and TaskFile records.

Requirements: 7.1, 7.2, 7.3, 9.9
"""
from __future__ import annotations

import time
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Task, TaskFile


# ---------------------------------------------------------------------------
# Input / output data classes
# ---------------------------------------------------------------------------


@dataclass
class TaskCreate:
    """Data required to create a new task record."""

    task_id: str
    session_id: str
    delete_type: str          # 'trash' | 'permanent'
    total_count: int


@dataclass
class TaskUpdate:
    """Fields that may be updated on an existing task record."""

    status: str | None = None                # 'running' | 'completed' | 'failed'
    success_count: int | None = None
    failed_count: int | None = None
    freed_bytes: int | None = None
    completed_at: int | None = None


@dataclass
class TaskSummary:
    """Task summary returned to the frontend."""

    task_id: str
    delete_type: str
    status: str
    total_count: int
    success_count: int
    failed_count: int
    freed_bytes: int
    started_at: int
    completed_at: int | None


# ---------------------------------------------------------------------------
# Repository
# ---------------------------------------------------------------------------


class TaskRepository:
    """Async repository for Task and TaskFile persistence."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    # ------------------------------------------------------------------
    # Task operations
    # ------------------------------------------------------------------

    async def create_task(self, data: TaskCreate) -> Task:
        """Insert a new Task record with status='running'."""
        now = int(time.time())
        task = Task(
            id=data.task_id,
            session_id=data.session_id,
            delete_type=data.delete_type,
            status="running",
            total_count=data.total_count,
            success_count=0,
            failed_count=0,
            freed_bytes=0,
            started_at=now,
            completed_at=None,
        )
        self._db.add(task)
        await self._db.commit()
        await self._db.refresh(task)
        return task

    async def update_task(self, task_id: str, update_data: TaskUpdate) -> Task | None:
        """Update specified fields on an existing Task record."""
        result = await self._db.execute(select(Task).where(Task.id == task_id))
        task = result.scalar_one_or_none()
        if task is None:
            return None

        if update_data.status is not None:
            task.status = update_data.status
        if update_data.success_count is not None:
            task.success_count = update_data.success_count
        if update_data.failed_count is not None:
            task.failed_count = update_data.failed_count
        if update_data.freed_bytes is not None:
            task.freed_bytes = update_data.freed_bytes
        if update_data.completed_at is not None:
            task.completed_at = update_data.completed_at

        await self._db.commit()
        await self._db.refresh(task)
        return task

    async def get_task(self, task_id: str) -> Task | None:
        """Return the Task with the given ID, or None if not found."""
        result = await self._db.execute(select(Task).where(Task.id == task_id))
        return result.scalar_one_or_none()

    async def list_tasks(self, session_id: str) -> list[TaskSummary]:
        """Return all tasks for a session, ordered by started_at descending."""
        result = await self._db.execute(
            select(Task)
            .where(Task.session_id == session_id)
            .order_by(Task.started_at.desc())
        )
        tasks = result.scalars().all()
        return [
            TaskSummary(
                task_id=t.id,
                delete_type=t.delete_type,
                status=t.status,
                total_count=t.total_count,
                success_count=t.success_count,
                failed_count=t.failed_count,
                freed_bytes=t.freed_bytes,
                started_at=t.started_at,
                completed_at=t.completed_at,
            )
            for t in tasks
        ]

    # ------------------------------------------------------------------
    # TaskFile operations
    # ------------------------------------------------------------------

    async def get_task_files(self, task_id: str) -> list[TaskFile]:
        """Return all TaskFile records for the given task."""
        result = await self._db.execute(
            select(TaskFile).where(TaskFile.task_id == task_id)
        )
        return list(result.scalars().all())

    async def bulk_insert_task_files(self, files: list[dict]) -> None:
        """Bulk-insert TaskFile records.

        Each dict must contain:
            task_id, file_id, file_name, file_path, file_size, result, error_msg
        """
        task_files = [
            TaskFile(
                task_id=f["task_id"],
                file_id=f["file_id"],
                file_name=f["file_name"],
                file_path=f["file_path"],
                file_size=f.get("file_size", 0),
                result=f["result"],
                error_msg=f.get("error_msg"),
            )
            for f in files
        ]
        self._db.add_all(task_files)
        await self._db.commit()
