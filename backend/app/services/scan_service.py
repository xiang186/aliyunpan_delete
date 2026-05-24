"""
Scan service — recursively lists all files and finds duplicates locally.

Two scan modes:

Full scan (default — "扫描重复文件" button):
  1. Recursively traverse the entire drive (or selected folders).
  2. Collect all files, build duplicate groups.
  3. After a complete full-drive scan, record every visited directory in
     scanned_folder (folder_id + updated_at at scan time).

Incremental scan ("增量扫描" button, full-drive only):
  1. Walk the directory tree.
  2. For each directory, look up its folder_id in scanned_folder:
     - updated_at unchanged → skip the whole subtree.
     - updated_at changed or not recorded → scan this directory's files,
       then recurse into sub-directories.
  3. Collect files from scanned directories, build duplicate groups.
  4. Update scanned_folder records for all visited directories.

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
_scan_running: dict[str, bool] = {}
_scan_pause_events: dict[str, asyncio.Event] = {}
_scan_stop_flags: dict[str, bool] = {}

# Global concurrency control for API-intensive tasks
_MAX_CONCURRENT_API_TASKS = 2  # Maximum concurrent API-intensive tasks
_current_api_tasks: set[str] = set()  # Set of currently running API-intensive task IDs
_api_tasks_lock = asyncio.Lock()  # Lock for managing concurrent tasks

_PROGRESS_INTERVAL = 100


def _expand_dirty_ancestors(
    dirty: set[str],
    folder_parents: dict[str, str],
) -> set[str]:
    """
    Given a set of dirty folder IDs and a child→parent mapping, return an
    expanded set that also includes every ancestor of each dirty folder.

    This ensures that incremental scan will not skip a subtree whose
    updated_at appears unchanged but whose descendants contain duplicates.
    """
    expanded: set[str] = set(dirty)
    for folder_id in dirty:
        current = folder_id
        while current in folder_parents:
            parent = folder_parents[current]
            if parent in expanded:
                break  # already processed this ancestor chain
            expanded.add(parent)
            current = parent
    return expanded



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

    async def start_scan(
        self,
        session_id: str,
        folder_ids: list[str] | None = None,
        folder_names: list[str] | None = None,
        incremental: bool = False,
    ) -> str:
        task_id = str(uuid.uuid4())
        _scan_queues[task_id] = []
        _scan_running[task_id] = True
        pause_event = asyncio.Event()
        pause_event.set()
        _scan_pause_events[task_id] = pause_event
        _scan_stop_flags[task_id] = False

        # Wait for available slot if too many concurrent API tasks
        async with _api_tasks_lock:
            while len(_current_api_tasks) >= _MAX_CONCURRENT_API_TASKS:
                logger.info(
                    "Too many concurrent API tasks (%d/%d), waiting for slot...",
                    len(_current_api_tasks), _MAX_CONCURRENT_API_TASKS
                )
                await asyncio.sleep(5.0)  # Wait 5 seconds before checking again
            
            _current_api_tasks.add(task_id)
            logger.info(
                "Scan task %s started (concurrent tasks: %d/%d)",
                task_id, len(_current_api_tasks), _MAX_CONCURRENT_API_TASKS
            )

        asyncio.create_task(
            self._run_scan_with_cleanup(
                session_id, task_id,
                folder_ids=folder_ids,
                folder_names=folder_names,
                incremental=incremental,
            ),
            name=f"scan-{task_id}",
        )
        logger.info(
            "Started scan task %s for session %s (folder_ids=%s, incremental=%s)",
            task_id, session_id, folder_ids, incremental,
        )
        return task_id

    def pause_scan(self, task_id: str) -> bool:
        event = _scan_pause_events.get(task_id)
        if event is None:
            return False
        event.clear()
        logger.info("Scan task %s paused", task_id)
        return True

    def resume_scan(self, task_id: str) -> bool:
        event = _scan_pause_events.get(task_id)
        if event is None:
            return False
        event.set()
        logger.info("Scan task %s resumed", task_id)
        return True

    def stop_scan(self, task_id: str) -> bool:
        if task_id not in _scan_running:
            return False
        _scan_stop_flags[task_id] = True
        event = _scan_pause_events.get(task_id)
        if event:
            event.set()
        logger.info("Scan task %s stop requested", task_id)
        return True

    async def get_scan_events(self, task_id: str) -> AsyncGenerator[dict, None]:
        if task_id in _scan_results and task_id not in _scan_running:
            result = _scan_results[task_id]
            yield {
                "event": "complete",
                "groups": [g.model_dump(mode="json") for g in result.groups],
                "total_count": result.total_files,
                "total_groups": result.total_groups,
                "total_size_bytes": result.total_size_bytes,
                "scanned_file_count": result.scanned_file_count,
            }
            return

        subscriber: asyncio.Queue = asyncio.Queue()
        subscribers = _scan_queues.get(task_id)
        if subscribers is None:
            return
        subscribers.append(subscriber)

        try:
            while True:
                event = await subscriber.get()
                yield event
                if event.get("event") in ("complete", "error"):
                    break
        finally:
            try:
                subscribers.remove(subscriber)
            except ValueError:
                pass

    # ------------------------------------------------------------------
    # Background orchestration
    # ------------------------------------------------------------------

    async def _refresh_token(self, session_id: str) -> str:
        """Fetch a valid access token from the database (refreshes if near expiry)."""
        from app.config import settings
        from app.db.database import AsyncSessionLocal
        from app.services.auth_service import AuthService as _AuthService
        async with AsyncSessionLocal() as db:
            auth_service = _AuthService(db, settings, self._client)
            return await auth_service.get_valid_access_token(session_id)

    async def _run_scan(
        self,
        session_id: str,
        task_id: str,
        folder_ids: list[str] | None = None,
        folder_names: list[str] | None = None,
        incremental: bool = False,
    ) -> None:
        subscribers = _scan_queues.get(task_id)
        if subscribers is None:
            return

        async def broadcast(event: dict) -> None:
            for q in list(subscribers):
                await q.put(event)

        try:
            from app.config import settings
            from app.core.rate_limiter import RateLimiter, RateLimitConfig
            from app.db.database import AsyncSessionLocal
            from app.services.auth_service import AuthService as _AuthService
            from sqlalchemy import select
            from app.db.models import UserSession

            async with AsyncSessionLocal() as db:
                rate_limiter = RateLimiter(RateLimitConfig(
                    interval_ms=settings.api_call_interval_ms,
                    max_retries=settings.api_max_retries,
                    max_backoff_seconds=settings.api_max_backoff_seconds,
                ))
                auth_service = _AuthService(db, settings, self._client)
                access_token = await auth_service.get_valid_access_token(session_id)
                drive_id = await self._client.get_default_drive_id(access_token)
                result = await db.execute(
                    select(UserSession.user_id).where(UserSession.id == session_id)
                )
                user_id: str = result.scalar_one()

            logger.info(
                "Scan task %s: drive_id=%s user_id=%s incremental=%s folder_ids=%s",
                task_id, drive_id, user_id, incremental, folder_ids,
            )

            # Incremental scan requires prior scanned-folder data
            use_incremental = incremental
            if use_incremental:
                has_prior = await self._has_scanned_folders(user_id)
                use_incremental = has_prior

            if use_incremental:
                groups, stopped, scanned_file_count = await self._incremental_scan(
                    session_id=session_id,
                    task_id=task_id,
                    user_id=user_id,
                    drive_id=drive_id,
                    folder_ids=folder_ids,
                    folder_names=folder_names,
                    broadcast=broadcast,
                    access_token=access_token,
                )
            else:
                groups, stopped, scanned_file_count = await self._full_scan(
                    session_id=session_id,
                    task_id=task_id,
                    user_id=user_id,
                    drive_id=drive_id,
                    folder_ids=folder_ids,
                    folder_names=folder_names,
                    broadcast=broadcast,
                    access_token=access_token,
                )

            total_files = sum(g.duplicate_count for g in groups)
            total_size_bytes = sum(g.file_size * (g.duplicate_count - 1) for g in groups)
            # unique_duplicate_files: files that are duplicated (one copy per group is "kept")
            unique_duplicate_files = len(groups)  # one unique content per group

            if stopped:
                await broadcast({
                    "event": "stopped",
                    "groups": [g.model_dump(mode="json") for g in groups],
                    "total_count": total_files,
                    "total_groups": len(groups),
                    "total_size_bytes": total_size_bytes,
                    "fetched_count": total_files,
                    "scanned_file_count": scanned_file_count,
                })
                logger.info("Scan task %s stopped early: %d groups", task_id, len(groups))
            else:
                result_obj = ScanResult(
                    task_id=task_id,
                    total_groups=len(groups),
                    total_files=total_files,
                    total_size_bytes=total_size_bytes,
                    scanned_file_count=scanned_file_count,
                    groups=groups,
                )
                _scan_results[task_id] = result_obj
                await broadcast({
                    "event": "complete",
                    "groups": [g.model_dump(mode="json") for g in groups],
                    "total_count": total_files,
                    "total_groups": len(groups),
                    "total_size_bytes": total_size_bytes,
                    "scanned_file_count": scanned_file_count,
                })
                logger.info("Scan task %s complete: %d groups", task_id, len(groups))

        except Exception as exc:
            logger.error("Scan task %s failed: %s", task_id, exc, exc_info=True)
            await broadcast({"event": "error", "message": str(exc)})
        finally:
            _scan_running.pop(task_id, None)
            _scan_queues.pop(task_id, None)
            _scan_pause_events.pop(task_id, None)
            _scan_stop_flags.pop(task_id, None)

    # ------------------------------------------------------------------
    # Full scan
    # ------------------------------------------------------------------

    async def _full_scan(
        self,
        session_id: str,
        task_id: str,
        user_id: str,
        drive_id: str,
        folder_ids: list[str] | None,
        folder_names: list[str] | None,
        broadcast,
        access_token: str,
    ) -> tuple[list[DuplicateGroup], bool, int]:
        """Returns (groups, stopped, scanned_file_count)."""
        all_files: list[dict] = []
        # folder_id -> updated_at string, collected during traversal
        visited_folders: dict[str, str] = {}
        # folder_id -> parent_folder_id, used to propagate dirty state upward
        folder_parents: dict[str, str] = {}
        stopped = False

        if folder_ids:
            name_map: dict[str, str] = {}
            if folder_names and len(folder_names) == len(folder_ids):
                name_map = dict(zip(folder_ids, folder_names))

            root_set: set[str] = set(folder_ids)
            for folder_id in folder_ids:
                if stopped:
                    break
                parent_path = name_map.get(folder_id, folder_id)
                stopped, access_token = await self._traverse(
                    session_id=session_id,
                    task_id=task_id,
                    user_id=user_id,
                    drive_id=drive_id,
                    parent_file_id=folder_id,
                    parent_path=parent_path,
                    all_files=all_files,
                    visited_folders=visited_folders,
                    folder_parents=folder_parents,
                    broadcast=broadcast,
                    skip_folder_ids=root_set - {folder_id},
                    access_token=access_token,
                )
        else:
            stopped, access_token = await self._traverse(
                session_id=session_id,
                task_id=task_id,
                user_id=user_id,
                drive_id=drive_id,
                parent_file_id="root",
                parent_path="",
                all_files=all_files,
                visited_folders=visited_folders,
                folder_parents=folder_parents,
                broadcast=broadcast,
                access_token=access_token,
            )

        groups = self._build_duplicate_groups(all_files)

        # Leaf directories are persisted immediately during traversal.
        # visited_folders now contains only non-leaf directories.
        # Only persist non-leaf folder cache when the scan completed fully —
        # a partial scan cannot reliably determine which non-leaf folders are
        # clean because some of their subtrees may not have been visited.
        if visited_folders and not stopped:
            dup_file_ids: set[str] = {
                f.file_id for group in groups for f in group.files
            }
            # Collect direct parents of duplicate files
            dirty_folder_ids: set[str] = set()
            for raw in all_files:
                if raw.get("file_id", "") in dup_file_ids:
                    parent_id = raw.get("parent_file_id", "")
                    if parent_id:
                        dirty_folder_ids.add(parent_id)

            # Propagate dirty state up to all ancestors so that incremental
            # scan does not skip a subtree that contains dirty descendants.
            dirty_folder_ids = _expand_dirty_ancestors(dirty_folder_ids, folder_parents)

            clean_folders = {
                fid: upd
                for fid, upd in visited_folders.items()
                if fid not in dirty_folder_ids
            }
            if clean_folders:
                await self._save_scanned_folders(user_id, clean_folders)
            # Remove previously-recorded folders that are now known to be dirty
            dirty_visited = dirty_folder_ids & set(visited_folders.keys())
            if dirty_visited:
                await self._remove_scanned_folders(user_id, dirty_visited)

            logger.info(
                "Scan task %s: saved %d clean non-leaf folders, removed %d dirty folders for user %s",
                task_id, len(clean_folders), len(dirty_visited), user_id,
            )

        return groups, stopped, len(all_files)

    # ------------------------------------------------------------------
    # Incremental scan
    # ------------------------------------------------------------------

    async def _incremental_scan(
        self,
        session_id: str,
        task_id: str,
        user_id: str,
        drive_id: str,
        folder_ids: list[str] | None,
        folder_names: list[str] | None,
        broadcast,
        access_token: str,
    ) -> tuple[list[DuplicateGroup], bool, int]:
        """
        Walk the directory tree incrementally.  Returns (groups, stopped, scanned_file_count).
          - Look up its folder_id in scanned_folder.
          - If updated_at is unchanged → skip the entire subtree.
          - If changed or not recorded → scan files, recurse, update record.

        When folder_ids is specified, only traverse those roots (not the whole
        drive).  The skip logic still applies within each selected root.
        """
        known: dict[str, str] = await self._load_scanned_folders(user_id)
        logger.info(
            "Scan task %s: incremental scan, %d known folders, folder_ids=%s",
            task_id, len(known), folder_ids,
        )

        await broadcast({
            "event": "progress",
            "fetched_count": 0,
            "total_count": None,
            "percentage": 0,
            "partial_groups": [],
            "mode": "incremental",
        })

        all_files: list[dict] = []
        updated_folders: dict[str, str] = {}
        # folder_id -> parent_folder_id, used to propagate dirty state upward
        folder_parents: dict[str, str] = {}
        stopped = False

        if folder_ids:
            name_map: dict[str, str] = {}
            if folder_names and len(folder_names) == len(folder_ids):
                name_map = dict(zip(folder_ids, folder_names))

            root_set: set[str] = set(folder_ids)
            for folder_id in folder_ids:
                if stopped:
                    break
                parent_path = name_map.get(folder_id, folder_id)
                stopped, access_token = await self._incremental_traverse(
                    session_id=session_id,
                    task_id=task_id,
                    drive_id=drive_id,
                    parent_file_id=folder_id,
                    parent_path=parent_path,
                    known=known,
                    all_files=all_files,
                    updated_folders=updated_folders,
                    folder_parents=folder_parents,
                    broadcast=broadcast,
                    skip_folder_ids=root_set - {folder_id},
                    access_token=access_token,
                )
        else:
            stopped, access_token = await self._incremental_traverse(
                session_id=session_id,
                task_id=task_id,
                drive_id=drive_id,
                parent_file_id="root",
                parent_path="",
                known=known,
                all_files=all_files,
                updated_folders=updated_folders,
                folder_parents=folder_parents,
                broadcast=broadcast,
                access_token=access_token,
            )

        groups = self._build_duplicate_groups(all_files)

        # Update folder records regardless of whether scan completed or stopped.
        # Clean folders (no duplicates found) are saved; dirty ones are removed.
        if updated_folders:
            dup_file_ids: set[str] = {
                f.file_id for group in groups for f in group.files
            }
            dirty_folder_ids: set[str] = set()
            for raw in all_files:
                if raw.get("file_id", "") in dup_file_ids:
                    parent_id = raw.get("parent_file_id", "")
                    if parent_id:
                        dirty_folder_ids.add(parent_id)

            # Propagate dirty state up to all ancestors so that incremental
            # scan does not skip a subtree that contains dirty descendants.
            dirty_folder_ids = _expand_dirty_ancestors(dirty_folder_ids, folder_parents)

            clean_folders = {
                fid: upd
                for fid, upd in updated_folders.items()
                if fid not in dirty_folder_ids
            }
            if clean_folders:
                await self._save_scanned_folders(user_id, clean_folders)
            dirty_visited = dirty_folder_ids & set(updated_folders.keys())
            if dirty_visited:
                await self._remove_scanned_folders(user_id, dirty_visited)

            logger.info(
                "Scan task %s: incremental — saved %d clean, removed %d dirty folders for user %s",
                task_id, len(clean_folders), len(dirty_visited), user_id,
            )

        return groups, stopped, len(all_files)

    async def _incremental_traverse(
        self,
        session_id: str,
        task_id: str,
        drive_id: str,
        parent_file_id: str,
        parent_path: str,
        known: dict[str, str],
        all_files: list[dict],
        updated_folders: dict[str, str],
        folder_parents: dict[str, str],
        broadcast,
        skip_folder_ids: set[str] | None = None,
        access_token: str = "",
    ) -> tuple[bool, str]:
        """
        Recursively walk the tree for incremental scan.

        For each sub-folder encountered:
          - If its updated_at matches known[folder_id] → skip subtree entirely.
          - Otherwise → scan its files, recurse, record new updated_at.

        Returns (stopped, access_token) — the token may have been refreshed.
        """
        import httpx

        pause_event = _scan_pause_events.get(task_id)
        marker: str | None = None

        while True:
            if _scan_stop_flags.get(task_id):
                return True, access_token
            if pause_event:
                await pause_event.wait()
                if _scan_stop_flags.get(task_id):
                    return True, access_token

            try:
                page = await self._client.list_files(
                    access_token=access_token,
                    drive_id=drive_id,
                    parent_file_id=parent_file_id,
                    marker=marker,
                    limit=200,
                )
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 401:
                    logger.info(
                        "Scan task %s: access token expired listing %s, refreshing…",
                        task_id, parent_file_id,
                    )
                    access_token = await self._refresh_token(session_id)
                    try:
                        page = await self._client.list_files(
                            access_token=access_token,
                            drive_id=drive_id,
                            parent_file_id=parent_file_id,
                            marker=marker,
                            limit=200,
                        )
                    except Exception as retry_exc:
                        logger.warning(
                            "Scan task %s: failed to list %s after token refresh: %s",
                            task_id, parent_file_id, retry_exc,
                        )
                        break
                else:
                    logger.warning(
                        "Scan task %s: failed to list %s: %s", task_id, parent_file_id, exc
                    )
                    break
            except Exception as exc:
                logger.warning(
                    "Scan task %s: failed to list %s: %s", task_id, parent_file_id, exc
                )
                break

            items: list[dict] = page.get("items", [])

            for item in items:
                if _scan_stop_flags.get(task_id):
                    return True, access_token

                if item.get("type") == "file":
                    item["_resolved_path"] = parent_path
                    all_files.append(item)
                    if len(all_files) % _PROGRESS_INTERVAL == 0:
                        await broadcast({
                            "event": "progress",
                            "fetched_count": len(all_files),
                            "total_count": None,
                            "percentage": 0,
                            "partial_groups": [],
                            "mode": "incremental",
                        })

                elif item.get("type") == "folder":
                    sub_id: str = item["file_id"]
                    sub_name: str = item.get("name", sub_id)
                    sub_path = f"{parent_path}/{sub_name}" if parent_path else sub_name
                    sub_updated_at: str = item.get("updated_at", "")

                    # Skip folders that are themselves selected as scan roots
                    if skip_folder_ids and sub_id in skip_folder_ids:
                        logger.debug(
                            "Scan task %s: skipping sub-folder %s (already a scan root)",
                            task_id, sub_path,
                        )
                        continue

                    # Record parent relationship for dirty-ancestor propagation
                    folder_parents[sub_id] = parent_file_id

                    # Skip if unchanged
                    if sub_id in known and known[sub_id] == sub_updated_at:
                        logger.debug(
                            "Scan task %s: skipping unchanged folder %s",
                            task_id, sub_path,
                        )
                        continue

                    # Changed or new — recurse
                    stopped, access_token = await self._incremental_traverse(
                        session_id=session_id,
                        task_id=task_id,
                        drive_id=drive_id,
                        parent_file_id=sub_id,
                        parent_path=sub_path,
                        known=known,
                        all_files=all_files,
                        updated_folders=updated_folders,
                        folder_parents=folder_parents,
                        broadcast=broadcast,
                        skip_folder_ids=skip_folder_ids,
                        access_token=access_token,
                    )
                    if stopped:
                        return True, access_token

                    # Record the new updated_at for this folder
                    if sub_updated_at:
                        updated_folders[sub_id] = sub_updated_at

                    await asyncio.sleep(0.05)

            next_marker: str | None = page.get("next_marker") or None
            if not next_marker:
                break
            marker = next_marker
            await asyncio.sleep(0.15)

        return False, access_token

    # ------------------------------------------------------------------
    # Full traversal (used by full scan)
    # ------------------------------------------------------------------

    async def _traverse(
        self,
        session_id: str,
        task_id: str,
        user_id: str,
        drive_id: str,
        parent_file_id: str,
        parent_path: str,
        all_files: list[dict],
        visited_folders: dict[str, str],
        folder_parents: dict[str, str],
        broadcast,
        skip_folder_ids: set[str] | None = None,
        access_token: str = "",
    ) -> tuple[bool, str]:
        """
        Recursively list all files.  Collects visited folder updated_at values
        into visited_folders for later persistence.

        Leaf directories (no sub-folders) are written to the scanned_folder
        table immediately after they are fully traversed, so that progress is
        preserved even if the backend process crashes mid-scan.  Non-leaf
        directories are still collected in visited_folders and persisted in
        bulk at the end of a complete scan.

        Returns (stopped, access_token) — the token may have been refreshed.
        """
        import httpx

        pause_event = _scan_pause_events.get(task_id)
        marker: str | None = None

        # Files collected directly inside this directory (not sub-dirs)
        local_files: list[dict] = []
        # updated_at values of sub-folders found in this directory
        sub_folder_updated_ats: dict[str, str] = {}

        while True:
            if _scan_stop_flags.get(task_id):
                return True, access_token
            if pause_event:
                await pause_event.wait()
                if _scan_stop_flags.get(task_id):
                    return True, access_token

            try:
                page = await self._client.list_files(
                    access_token=access_token,
                    drive_id=drive_id,
                    parent_file_id=parent_file_id,
                    marker=marker,
                    limit=200,
                )
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 401:
                    logger.info(
                        "Scan task %s: access token expired listing %s, refreshing…",
                        task_id, parent_file_id,
                    )
                    access_token = await self._refresh_token(session_id)
                    try:
                        page = await self._client.list_files(
                            access_token=access_token,
                            drive_id=drive_id,
                            parent_file_id=parent_file_id,
                            marker=marker,
                            limit=200,
                        )
                    except Exception as retry_exc:
                        logger.warning(
                            "Scan task %s: failed to list %s after token refresh: %s",
                            task_id, parent_file_id, retry_exc,
                        )
                        break
                else:
                    logger.warning(
                        "Scan task %s: failed to list %s: %s", task_id, parent_file_id, exc
                    )
                    break
            except Exception as exc:
                logger.warning(
                    "Scan task %s: failed to list %s: %s", task_id, parent_file_id, exc
                )
                break

            items: list[dict] = page.get("items", [])

            for item in items:
                if _scan_stop_flags.get(task_id):
                    return True, access_token

                if item.get("type") == "file":
                    item["_resolved_path"] = parent_path
                    all_files.append(item)
                    local_files.append(item)
                    if len(all_files) % _PROGRESS_INTERVAL == 0:
                        partial_groups = ScanService._build_duplicate_groups(all_files)
                        await broadcast({
                            "event": "progress",
                            "fetched_count": len(all_files),
                            "total_count": None,
                            "percentage": 0,
                            "partial_groups": [g.model_dump(mode="json") for g in partial_groups],
                        })

                elif item.get("type") == "folder":
                    sub_id: str = item["file_id"]
                    if skip_folder_ids and sub_id in skip_folder_ids:
                        logger.debug(
                            "Scan task %s: skipping sub-folder %s (already a scan root)",
                            task_id, sub_id,
                        )
                        continue

                    sub_name: str = item.get("name", sub_id)
                    sub_path = f"{parent_path}/{sub_name}" if parent_path else sub_name
                    sub_updated_at: str = item.get("updated_at", "")

                    # Record parent relationship for dirty-ancestor propagation
                    folder_parents[sub_id] = parent_file_id

                    # Track sub-folders found in this directory
                    if sub_updated_at:
                        sub_folder_updated_ats[sub_id] = sub_updated_at

                    # Record this folder's updated_at for later persistence
                    if sub_updated_at:
                        visited_folders[sub_id] = sub_updated_at

                    stopped, access_token = await self._traverse(
                        session_id=session_id,
                        task_id=task_id,
                        user_id=user_id,
                        drive_id=drive_id,
                        parent_file_id=sub_id,
                        parent_path=sub_path,
                        all_files=all_files,
                        visited_folders=visited_folders,
                        folder_parents=folder_parents,
                        broadcast=broadcast,
                        skip_folder_ids=skip_folder_ids,
                        access_token=access_token,
                    )
                    if stopped:
                        return True, access_token
                    await asyncio.sleep(0.05)

            next_marker: str | None = page.get("next_marker") or None
            if not next_marker:
                break
            marker = next_marker
            await asyncio.sleep(0.15)

        # After all pages of this directory are processed, check if it is a
        # leaf directory (no sub-folders).  If so, we can immediately determine
        # whether it is clean and persist the result to the database — this
        # ensures progress is saved even if the backend crashes later.
        #
        # Note: we can only do this for leaf directories because non-leaf
        # directories may have duplicate files spread across multiple subtrees,
        # and we cannot know the full duplicate set until the entire scan
        # completes.
        is_leaf = len(sub_folder_updated_ats) == 0
        if is_leaf and parent_file_id != "root":
            # Check if any local file is a duplicate within this directory
            local_hashes: dict[tuple, int] = {}
            has_local_dup = False
            for f in local_files:
                content_hash = f.get("content_hash") or f.get("sha1") or ""
                size = f.get("size", 0)
                if not content_hash or not size:
                    continue
                key = (content_hash, size)
                local_hashes[key] = local_hashes.get(key, 0) + 1
                if local_hashes[key] >= 2:
                    has_local_dup = True
                    break

            # Retrieve the updated_at for this directory from visited_folders
            # (it was recorded by the parent call before recursing into us)
            this_updated_at = visited_folders.get(parent_file_id, "")
            if this_updated_at and not has_local_dup:
                # Clean leaf directory — persist immediately
                await self._save_scanned_folders(user_id, {parent_file_id: this_updated_at})
                # Remove from visited_folders so the end-of-scan logic does
                # not process it again
                visited_folders.pop(parent_file_id, None)
                logger.debug(
                    "Scan task %s: persisted clean leaf folder %s immediately",
                    task_id, parent_file_id,
                )
            elif this_updated_at and has_local_dup:
                # Dirty leaf directory — remove any stale clean record
                await self._remove_scanned_folders(user_id, {parent_file_id})
                visited_folders.pop(parent_file_id, None)
                logger.debug(
                    "Scan task %s: removed dirty leaf folder %s from cache",
                    task_id, parent_file_id,
                )

        return False, access_token

    # ------------------------------------------------------------------
    # scanned_folder persistence helpers
    # ------------------------------------------------------------------

    async def _has_scanned_folders(self, user_id: str) -> bool:
        from app.db.database import AsyncSessionLocal
        from sqlalchemy import select
        from app.db.models import ScannedFolder
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(ScannedFolder.id)
                .where(ScannedFolder.user_id == user_id)
                .limit(1)
            )
            return result.scalar_one_or_none() is not None

    async def _load_scanned_folders(self, user_id: str) -> dict[str, str]:
        """Return {folder_id: updated_at} for all known folders of this user."""
        from app.db.database import AsyncSessionLocal
        from sqlalchemy import select
        from app.db.models import ScannedFolder
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(ScannedFolder.folder_id, ScannedFolder.updated_at)
                .where(ScannedFolder.user_id == user_id)
            )
            return {row.folder_id: row.updated_at for row in result.all()}

    async def _save_scanned_folders(
        self, user_id: str, folders: dict[str, str]
    ) -> None:
        """Upsert {folder_id: updated_at} records for this user."""
        from app.db.database import AsyncSessionLocal
        from sqlalchemy.dialects.sqlite import insert as sqlite_insert
        from app.db.models import ScannedFolder

        async with AsyncSessionLocal() as db:
            for folder_id, updated_at in folders.items():
                stmt = sqlite_insert(ScannedFolder).values(
                    user_id=user_id,
                    folder_id=folder_id,
                    updated_at=updated_at,
                )
                stmt = stmt.on_conflict_do_update(
                    index_elements=["user_id", "folder_id"],
                    set_={"updated_at": updated_at},
                )
                await db.execute(stmt)
            await db.commit()

    async def _remove_scanned_folders(
        self, user_id: str, folder_ids: set[str]
    ) -> None:
        """Remove folder records that are now dirty (contain duplicates)."""
        if not folder_ids:
            return
        from app.db.database import AsyncSessionLocal
        from sqlalchemy import delete
        from app.db.models import ScannedFolder
        async with AsyncSessionLocal() as db:
            await db.execute(
                delete(ScannedFolder).where(
                    ScannedFolder.user_id == user_id,
                    ScannedFolder.folder_id.in_(folder_ids),
                )
            )
            await db.commit()

    # ------------------------------------------------------------------
    # Duplicate group builder
    # ------------------------------------------------------------------

    @staticmethod
    def _build_duplicate_groups(all_files: list[dict]) -> list[DuplicateGroup]:
        hash_map: dict[tuple, list[dict]] = defaultdict(list)
        skipped = 0
        seen_file_ids: set[str] = set()

        for f in all_files:
            file_id = f.get("file_id", "")
            if file_id and file_id in seen_file_ids:
                logger.warning("Duplicate file_id in scan results, skipping: %s", file_id)
                continue
            if file_id:
                seen_file_ids.add(file_id)

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
                    file_path=(
                        f.get("_resolved_path", "")
                        or f.get("file_path", "")
                        or f.get("parent_file_id", "")
                    ),
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
