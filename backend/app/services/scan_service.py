"""
Scan service — recursively lists all files and finds duplicates locally.

Strategy (mirrors Qwen_python_20260519_5vt341lpi.py):
  1. GET /v2/drive/get_default_drive  → drive_id
  2. Recursively list all files via /adrive/v3/file/list
  3. Group by (content_hash, size) — groups with ≥2 files are duplicates
  4. Stream SSE progress events while scanning

Requirements: 2.1, 2.2, 2.3, 2.4, 2.5
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from collections import defaultdict
from typing import AsyncGenerator

from app.core.file_type import classify_file_type
from app.models.schemas import DuplicateFile, DuplicateGroup, ScanResult
from app.services.aliyun_client import AliyunDriveClient
from app.services.auth_service import AuthService

logger = logging.getLogger(__name__)

# In-memory stores keyed by task_id
_scan_queues: dict[str, list[asyncio.Queue]] = {}
_scan_results: dict[str, ScanResult] = {}
# Track running tasks so reconnecting clients can tell the task is still alive
_scan_running: dict[str, bool] = {}
# Pause events: set = running, clear = paused
_scan_pause_events: dict[str, asyncio.Event] = {}
# Stop flags: True = stop requested
_scan_stop_flags: dict[str, bool] = {}

# How often to emit a progress event (every N files fetched)
_PROGRESS_INTERVAL = 100


class ScanService:
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

    async def start_scan(self, session_id: str) -> str:
        task_id = str(uuid.uuid4())
        _scan_queues[task_id] = []
        _scan_running[task_id] = True
        pause_event = asyncio.Event()
        pause_event.set()  # start in running state
        _scan_pause_events[task_id] = pause_event
        _scan_stop_flags[task_id] = False

        asyncio.create_task(
            self._run_scan(session_id, task_id),
            name=f"scan-{task_id}",
        )
        logger.info("Started scan task %s for session %s", task_id, session_id)
        return task_id

    def pause_scan(self, task_id: str) -> bool:
        """Pause a running scan. Returns True if the task exists."""
        event = _scan_pause_events.get(task_id)
        if event is None:
            return False
        event.clear()
        logger.info("Scan task %s paused", task_id)
        return True

    def resume_scan(self, task_id: str) -> bool:
        """Resume a paused scan. Returns True if the task exists."""
        event = _scan_pause_events.get(task_id)
        if event is None:
            return False
        event.set()
        logger.info("Scan task %s resumed", task_id)
        return True

    def stop_scan(self, task_id: str) -> bool:
        """Stop a scan and emit a 'stopped' event with current partial results."""
        if task_id not in _scan_running:
            return False
        _scan_stop_flags[task_id] = True
        # Also resume if paused so the task loop can check the stop flag
        event = _scan_pause_events.get(task_id)
        if event:
            event.set()
        logger.info("Scan task %s stop requested", task_id)
        return True

    async def get_scan_events(self, task_id: str) -> AsyncGenerator[dict, None]:
        """Subscribe to events for *task_id*.

        Each caller gets its own private queue that receives a copy of every
        event broadcast by the background task.  This allows the page to
        reconnect after a refresh and still receive progress / completion
        events.

        If the task has already finished (result cached in ``_scan_results``),
        we immediately replay the final ``complete`` event so the reconnecting
        client gets the result right away.
        """
        # Task already finished — replay the cached result immediately.
        if task_id in _scan_results and task_id not in _scan_running:
            result = _scan_results[task_id]
            yield {
                "event": "complete",
                "groups": [g.model_dump(mode="json") for g in result.groups],
                "total_count": result.total_files,
                "total_groups": result.total_groups,
                "total_size_bytes": result.total_size_bytes,
            }
            return

        # Task is still running — subscribe a new per-client queue.
        subscriber: asyncio.Queue = asyncio.Queue()
        subscribers = _scan_queues.get(task_id)
        if subscribers is None:
            # Task not found and no cached result — nothing to stream.
            return
        subscribers.append(subscriber)

        try:
            while True:
                event = await subscriber.get()
                yield event
                if event.get("event") in ("complete", "error"):
                    break
        finally:
            # Clean up this subscriber's queue.
            try:
                subscribers.remove(subscriber)
            except ValueError:
                pass

    # ------------------------------------------------------------------
    # Background scan
    # ------------------------------------------------------------------

    async def _run_scan(self, session_id: str, task_id: str) -> None:
        subscribers = _scan_queues.get(task_id)
        if subscribers is None:
            return

        async def broadcast(event: dict) -> None:
            for q in list(subscribers):
                await q.put(event)

        all_files: list[dict] = []
        # folder_id → full path string, built as we recurse
        path_cache: dict[str, str] = {"root": ""}

        try:
            from app.config import settings
            from app.core.rate_limiter import RateLimiter, RateLimitConfig
            from app.db.database import AsyncSessionLocal
            from app.services.auth_service import AuthService

            async with AsyncSessionLocal() as db:
                rate_limiter = RateLimiter(RateLimitConfig(
                    interval_ms=settings.api_call_interval_ms,
                    max_retries=settings.api_max_retries,
                    max_backoff_seconds=settings.api_max_backoff_seconds,
                ))
                auth_service = AuthService(db, settings, self._client)

                access_token = await auth_service.get_valid_access_token(session_id)
                drive_id = await self._client.get_default_drive_id(access_token)
                logger.info("Scan task %s: drive_id=%s", task_id, drive_id)

            stopped = await self._list_recursive(
                session_id=session_id,
                task_id=task_id,
                drive_id=drive_id,
                parent_file_id="root",
                parent_path="",
                all_files=all_files,
                path_cache=path_cache,
                broadcast=broadcast,
            )

            # Build duplicate groups from whatever files we collected
            groups = self._build_duplicate_groups(all_files, drive_id)
            total_files = sum(g.duplicate_count for g in groups)
            total_size_bytes = sum(g.file_size * (g.duplicate_count - 1) for g in groups)

            if stopped:
                # Emit a 'stopped' event so the client knows it was paused/stopped
                await broadcast({
                    "event": "stopped",
                    "groups": [g.model_dump(mode="json") for g in groups],
                    "total_count": total_files,
                    "total_groups": len(groups),
                    "total_size_bytes": total_size_bytes,
                    "fetched_count": len(all_files),
                })
                logger.info("Scan task %s stopped early: %d files, %d groups", task_id, len(all_files), len(groups))
            else:
                result = ScanResult(
                    task_id=task_id,
                    total_groups=len(groups),
                    total_files=total_files,
                    total_size_bytes=total_size_bytes,
                    groups=groups,
                )
                _scan_results[task_id] = result

                await broadcast({
                    "event": "complete",
                    "groups": [g.model_dump(mode="json") for g in groups],
                    "total_count": total_files,
                    "total_groups": len(groups),
                    "total_size_bytes": total_size_bytes,
                })
                logger.info("Scan task %s complete: %d groups, %d files", task_id, len(groups), total_files)

        except Exception as exc:
            logger.error("Scan task %s failed: %s", task_id, exc, exc_info=True)
            await broadcast({"event": "error", "message": str(exc)})
        finally:
            _scan_running.pop(task_id, None)
            _scan_queues.pop(task_id, None)
            _scan_pause_events.pop(task_id, None)
            _scan_stop_flags.pop(task_id, None)

    async def _list_recursive(
        self,
        session_id: str,
        task_id: str,
        drive_id: str,
        parent_file_id: str,
        parent_path: str,
        all_files: list[dict],
        path_cache: dict[str, str],
        broadcast,
    ) -> bool:
        """Recursively list all files. Returns True if stopped early."""
        from app.config import settings
        from app.db.database import AsyncSessionLocal
        from app.services.auth_service import AuthService

        pause_event = _scan_pause_events.get(task_id)
        marker: str | None = None

        while True:
            # Check stop flag
            if _scan_stop_flags.get(task_id):
                return True

            # Wait if paused
            if pause_event:
                await pause_event.wait()
                if _scan_stop_flags.get(task_id):
                    return True

            async with AsyncSessionLocal() as db:
                auth_service = AuthService(db, settings, self._client)
                access_token = await auth_service.get_valid_access_token(session_id)

            try:
                page = await self._client.list_files(
                    access_token=access_token,
                    drive_id=drive_id,
                    parent_file_id=parent_file_id,
                    marker=marker,
                    limit=200,
                )
            except Exception as exc:
                logger.warning("Scan task %s: failed to list %s: %s", task_id, parent_file_id, exc)
                break

            items: list[dict] = page.get("items", [])

            for item in items:
                if _scan_stop_flags.get(task_id):
                    return True

                if item.get("type") == "file":
                    # Attach the resolved parent path so _build_duplicate_groups can use it
                    item["_resolved_path"] = parent_path
                    all_files.append(item)
                    if len(all_files) % _PROGRESS_INTERVAL == 0:
                        partial_groups = ScanService._build_duplicate_groups(all_files, drive_id)
                        await broadcast({
                            "event": "progress",
                            "fetched_count": len(all_files),
                            "total_count": None,
                            "percentage": 0,
                            "partial_groups": [g.model_dump(mode="json") for g in partial_groups],
                        })
                elif item.get("type") == "folder":
                    folder_name: str = item.get("name", item["file_id"])
                    folder_path = f"{parent_path}/{folder_name}" if parent_path else folder_name
                    path_cache[item["file_id"]] = folder_path
                    stopped = await self._list_recursive(
                        session_id=session_id,
                        task_id=task_id,
                        drive_id=drive_id,
                        parent_file_id=item["file_id"],
                        parent_path=folder_path,
                        all_files=all_files,
                        path_cache=path_cache,
                        broadcast=broadcast,
                    )
                    if stopped:
                        return True
                    await asyncio.sleep(0.05)

            next_marker: str | None = page.get("next_marker") or None
            if not next_marker:
                break
            marker = next_marker
            await asyncio.sleep(0.15)

        return False

    @staticmethod
    def _build_duplicate_groups(
        all_files: list[dict],
        drive_id: str,
    ) -> list[DuplicateGroup]:
        """Group files by (content_hash, size) and return groups with ≥2 files."""
        hash_map: dict[tuple, list[dict]] = defaultdict(list)
        skipped = 0

        for f in all_files:
            content_hash = f.get("content_hash") or f.get("sha1") or ""
            size = f.get("size", 0)
            if not content_hash or not size:
                skipped += 1
                continue
            hash_map[(content_hash, size)].append(f)

        if skipped:
            logger.info("Skipped %d files with no hash/size", skipped)

        groups: list[DuplicateGroup] = []
        for (content_hash, size), file_list in hash_map.items():
            if len(file_list) < 2:
                continue

            dup_files: list[DuplicateFile] = []
            for f in file_list:
                file_name: str = f.get("name", "")
                dup_files.append(DuplicateFile(
                    file_id=f.get("file_id", ""),
                    file_name=file_name,
                    file_path=f.get("_resolved_path", "") or f.get("file_path", "") or f.get("parent_file_id", ""),
                    file_size=f.get("size", 0),
                    content_hash=content_hash,
                    modified_at=f.get("updated_at", "1970-01-01T00:00:00Z"),
                    file_type=classify_file_type(file_name),
                ))

            representative = dup_files[0]
            groups.append(DuplicateGroup(
                group_id=content_hash,
                file_name=representative.file_name,
                file_size=size,
                content_hash=content_hash,
                duplicate_count=len(dup_files),
                file_type=representative.file_type,
                files=dup_files,
            ))

        logger.info("Found %d duplicate groups from %d files", len(groups), len(all_files))
        return groups
