"""
Delete service for batch-deleting duplicate files on AliyunDrive.

Manages background delete tasks, SSE event queues, and batched API calls
to either move files to the recycle bin or permanently delete them.

Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 9.4, 9.5, 9.6, 9.7, 9.8, 9.10
"""
from __future__ import annotations

import asyncio
import logging
import time
import uuid
from typing import AsyncGenerator, Literal

from app.db.database import AsyncSessionLocal
from app.db.models import Task, TaskFile
from app.services.aliyun_client import AliyunDriveClient
from app.services.auth_service import AuthService

logger = logging.getLogger(__name__)

# In-memory queue store keyed by task_id.
# Each queue holds SSE event dicts until the consumer reads them.
_delete_queues: dict[str, asyncio.Queue] = {}

# Batch size limit imposed by the AliyunDrive batch API.
_BATCH_SIZE = 100


class DeleteService:
    """
    Orchestrates batch file-delete tasks.

    A delete task is started with ``start_delete``, which creates a DB record,
    launches a background coroutine that calls the AliyunDrive batch API in
    chunks of up to 100 files, and pushes SSE events into an asyncio.Queue.
    The caller can then stream those events via ``get_delete_events``.
    """

    def __init__(
        self,
        auth_service: AuthService,
        aliyun_client: AliyunDriveClient,
    ) -> None:
        self._auth_service = auth_service
        self._client = aliyun_client

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def start_delete(
        self,
        session_id: str,
        file_ids: list[str],
        delete_type: Literal["trash", "permanent"],
        file_meta: list[dict] | None = None,
    ) -> str:
        """
        Start a background batch-delete task.

        Creates a Task record in the database, registers an asyncio.Queue for
        SSE events, and fires off the background coroutine.

        Parameters
        ----------
        session_id:
            The authenticated session whose access token will be used.
        file_ids:
            List of AliyunDrive file IDs to delete.
        delete_type:
            ``"trash"`` to move to the recycle bin, ``"permanent"`` to delete
            permanently.
        file_meta:
            Optional list of dicts with keys ``file_id``, ``file_name``,
            ``file_path``, and ``file_size``.  Used to populate TaskFile
            records and compute ``freed_bytes``.

        Returns
        -------
        str
            A UUID string identifying this delete task.
        """
        task_id = str(uuid.uuid4())

        # Create the SSE queue before launching the background task so the
        # consumer can open the stream immediately after this call returns.
        queue: asyncio.Queue = asyncio.Queue()
        _delete_queues[task_id] = queue

        # The initial Task DB record is created inside the background task to
        # avoid session lifecycle conflicts with the request-scoped session.
        asyncio.create_task(
            self._execute_batch_delete(
                session_id=session_id,
                task_id=task_id,
                file_ids=file_ids,
                delete_type=delete_type,
                file_meta=file_meta,
            ),
            name=f"delete-{task_id}",
        )

        logger.info(
            "Started delete task %s (%s) for session %s — %d files",
            task_id,
            delete_type,
            session_id,
            len(file_ids),
        )
        return task_id

    async def get_delete_events(self, task_id: str) -> AsyncGenerator[dict, None]:
        """
        Yield SSE event dicts from the queue for the given task.

        Stops yielding after a ``complete`` or ``error`` event is received.

        Parameters
        ----------
        task_id:
            The delete task whose events should be streamed.

        Yields
        ------
        dict
            SSE event payload dicts with at least an ``"event"`` key.

        Raises
        ------
        KeyError
            If ``task_id`` is not found in the queue store (caller should
            convert this to a 404 response).
        """
        queue = _delete_queues[task_id]  # raises KeyError if not found

        while True:
            event = await queue.get()
            yield event
            if event.get("event") in ("complete", "error"):
                # Clean up the queue entry to free memory
                _delete_queues.pop(task_id, None)
                break

    # ------------------------------------------------------------------
    # Background task
    # ------------------------------------------------------------------

    async def _execute_batch_delete(
        self,
        session_id: str,
        task_id: str,
        file_ids: list[str],
        delete_type: Literal["trash", "permanent"],
        file_meta: list[dict] | None,
    ) -> None:
        """
        Execute the batch delete in the background, pushing SSE events.

        Splits ``file_ids`` into batches of up to 100, calls the appropriate
        AliyunDrive batch API for each batch, and pushes ``progress`` events
        after each batch.  On completion pushes a ``complete`` event and
        updates the Task record; on unrecoverable error pushes an ``error``
        event and marks the Task as failed.

        Parameters
        ----------
        session_id:
            The authenticated session to use for API calls.
        task_id:
            The task ID whose queue will receive the events.
        file_ids:
            Full list of file IDs to delete.
        delete_type:
            ``"trash"`` or ``"permanent"``.
        file_meta:
            Optional per-file metadata for size accounting and TaskFile records.
        """
        queue = _delete_queues.get(task_id)
        if queue is None:
            logger.error("Queue for delete task %s not found", task_id)
            return

        # Persist the initial Task record now that we're in the background task,
        # safely outside the request-scoped session lifecycle.
        now = int(time.time())
        try:
            async with AsyncSessionLocal() as db:
                task_row = Task(
                    id=task_id,
                    session_id=session_id,
                    delete_type=delete_type,
                    status="running",
                    total_count=len(file_ids),
                    success_count=0,
                    failed_count=0,
                    freed_bytes=0,
                    started_at=now,
                    completed_at=None,
                )
                db.add(task_row)
                await db.commit()
        except Exception as db_exc:
            logger.error("Failed to create Task record for %s: %s", task_id, db_exc)

        # Build a lookup map from file_id → metadata for O(1) access.
        meta_map: dict[str, dict] = {}
        if file_meta:
            for m in file_meta:
                fid = m.get("file_id", "")
                if fid:
                    meta_map[fid] = m

        total_count = len(file_ids)
        success_count = 0
        failed_count = 0
        freed_bytes = 0
        processed_count = 0

        # Accumulate per-file results for TaskFile bulk insert.
        file_results: list[dict] = []
        # Accumulate failed file info for the complete event.
        failed_files: list[dict] = []

        # Split into batches of up to _BATCH_SIZE.
        batches = [
            file_ids[i : i + _BATCH_SIZE]
            for i in range(0, total_count, _BATCH_SIZE)
        ]

        try:
            # Fetch drive_id once before processing batches.
            # Use a fresh DB session — the request-scoped auth_service session
            # is already closed by the time this background task runs.
            from app.config import settings as app_settings
            from app.services.auth_service import AuthService as _AuthService

            async with AsyncSessionLocal() as db:
                bg_auth = _AuthService(db, app_settings, self._client)
                access_token = await bg_auth.get_valid_access_token(session_id)
                drive_id = await self._client.get_default_drive_id(access_token)
            logger.info("Delete task %s: drive_id=%s", task_id, drive_id)

            for batch in batches:
                async with AsyncSessionLocal() as db:
                    bg_auth = _AuthService(db, app_settings, self._client)
                    access_token = await bg_auth.get_valid_access_token(session_id)

                if delete_type == "trash":
                    result = await self._client.batch_trash(access_token, batch, drive_id)
                else:
                    result = await self._client.batch_delete_permanently(
                        access_token, batch, drive_id
                    )

                # Tally successes
                for fid in result.success_ids:
                    success_count += 1
                    meta = meta_map.get(fid, {})
                    freed_bytes += meta.get("file_size", 0)
                    file_results.append(
                        {
                            "file_id": fid,
                            "file_name": meta.get("file_name", fid),
                            "file_path": meta.get("file_path", ""),
                            "file_size": meta.get("file_size", 0),
                            "result": "success",
                            "error_msg": None,
                        }
                    )

                # Tally failures
                for item in result.failed_items:
                    fid = item.get("file_id", "")
                    error_msg = item.get("error_msg", "Unknown error")
                    failed_count += 1
                    meta = meta_map.get(fid, {})
                    file_results.append(
                        {
                            "file_id": fid,
                            "file_name": meta.get("file_name", fid),
                            "file_path": meta.get("file_path", ""),
                            "file_size": meta.get("file_size", 0),
                            "result": "failed",
                            "error_msg": error_msg,
                        }
                    )
                    failed_files.append({"file_id": fid, "error_msg": error_msg})

                processed_count += len(batch)
                percentage = (
                    round(processed_count / total_count * 100.0, 2)
                    if total_count > 0
                    else 100.0
                )

                await queue.put(
                    {
                        "event": "progress",
                        "processed_count": processed_count,
                        "total_count": total_count,
                        "success_count": success_count,
                        "failed_count": failed_count,
                        "percentage": percentage,
                    }
                )

                logger.debug(
                    "Delete task %s: processed %d/%d (success=%d, failed=%d)",
                    task_id,
                    processed_count,
                    total_count,
                    success_count,
                    failed_count,
                )

            # All batches done — persist results and push complete event.
            now = int(time.time())
            async with AsyncSessionLocal() as db:
                from sqlalchemy import select

                result_row = await db.execute(
                    select(Task).where(Task.id == task_id)
                )
                task_row = result_row.scalar_one_or_none()
                if task_row is not None:
                    task_row.status = "completed"
                    task_row.success_count = success_count
                    task_row.failed_count = failed_count
                    task_row.freed_bytes = freed_bytes
                    task_row.completed_at = now

                # Bulk-insert TaskFile records
                for fr in file_results:
                    db.add(
                        TaskFile(
                            task_id=task_id,
                            file_id=fr["file_id"],
                            file_name=fr["file_name"],
                            file_path=fr["file_path"],
                            file_size=fr["file_size"],
                            result=fr["result"],
                            error_msg=fr["error_msg"],
                        )
                    )

                await db.commit()

            await queue.put(
                {
                    "event": "complete",
                    "task_id": task_id,
                    "success_count": success_count,
                    "failed_count": failed_count,
                    "freed_bytes": freed_bytes,
                    "failed_files": failed_files,
                }
            )

            logger.info(
                "Delete task %s complete: success=%d, failed=%d, freed=%d bytes",
                task_id,
                success_count,
                failed_count,
                freed_bytes,
            )

        except Exception as exc:
            logger.error(
                "Delete task %s failed with exception: %s", task_id, exc, exc_info=True
            )

            # Mark the task as failed in the database.
            try:
                async with AsyncSessionLocal() as db:
                    from sqlalchemy import select

                    result_row = await db.execute(
                        select(Task).where(Task.id == task_id)
                    )
                    task_row = result_row.scalar_one_or_none()
                    if task_row is not None:
                        task_row.status = "failed"
                        task_row.success_count = success_count
                        task_row.failed_count = failed_count
                        task_row.freed_bytes = freed_bytes
                        task_row.completed_at = int(time.time())
                    await db.commit()
            except Exception as db_exc:
                logger.error(
                    "Failed to update task %s status to failed: %s", task_id, db_exc
                )

            await queue.put({"event": "error", "message": str(exc)})
