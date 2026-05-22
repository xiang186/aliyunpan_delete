"""
Folder index service.

Builds and maintains a full directory-tree cache per user so the
folder-picker dialog can search across all levels without lazy loading.

Workflow:
  1. Client opens folder-picker → GET /api/scan/folder-index/status
     - If status == 'ready': client uses cached data for search
     - If status == 'idle':  client triggers POST /api/scan/folder-index/build
     - If status == 'building': client polls status until ready
  2. Background task crawls the entire folder tree and writes to folder_cache
  3. GET /api/scan/folder-index/search?q=keyword returns matching folders
  4. GET /api/scan/folders still works for lazy-load tree rendering
"""
from __future__ import annotations

import asyncio
import logging
import time

from sqlalchemy import delete, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.db.database import AsyncSessionLocal
from app.db.models import FolderCache, FolderIndexMeta
from app.services.aliyun_client import AliyunDriveClient
from app.services.auth_service import AuthService

logger = logging.getLogger(__name__)

# In-memory flag to prevent duplicate background builds per user
_building: set[str] = set()


class FolderIndexService:
    def __init__(self, aliyun_client: AliyunDriveClient) -> None:
        self._client = aliyun_client

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def get_status(self, user_id: str) -> dict:
        """Return the current index status for a user."""
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(FolderIndexMeta).where(FolderIndexMeta.user_id == user_id)
            )
            meta = result.scalar_one_or_none()

        if meta is None:
            return {"status": "idle", "total_folders": 0, "built_at": None}

        # If we think it's building but the background task is gone, reset to idle
        if meta.status == "building" and user_id not in _building:
            return {"status": "idle", "total_folders": meta.total_folders, "built_at": meta.built_at}

        return {
            "status": meta.status,
            "total_folders": meta.total_folders,
            "built_at": meta.built_at,
        }

    async def start_build(self, session_id: str, user_id: str, drive_id: str) -> dict:
        """
        Start a background folder-tree crawl if not already running.
        Returns the current status dict.
        """
        if user_id in _building:
            return await self.get_status(user_id)

        # Mark as building
        await self._set_status(user_id, "building", 0)
        _building.add(user_id)

        asyncio.create_task(
            self._crawl(session_id, user_id, drive_id),
            name=f"folder-index-{user_id}",
        )
        logger.info("Started folder index build for user %s", user_id)
        return {"status": "building", "total_folders": 0, "built_at": None}

    async def search(self, user_id: str, keyword: str, limit: int = 50) -> list[dict]:
        """
        Search cached folders by name (case-insensitive substring match).
        Returns up to *limit* results sorted by full_path.
        """
        if not keyword:
            return []

        pattern = f"%{keyword}%"
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(FolderCache)
                .where(
                    FolderCache.user_id == user_id,
                    FolderCache.name.ilike(pattern),
                )
                .order_by(FolderCache.full_path)
                .limit(limit)
            )
            rows = result.scalars().all()

        return [
            {
                "file_id": r.file_id,
                "name": r.name,
                "full_path": r.full_path,
                "parent_id": r.parent_id,
                "has_children": bool(r.has_children),
            }
            for r in rows
        ]

    async def get_children(self, user_id: str, parent_id: str) -> list[dict]:
        """Return cached immediate children of a folder (for tree rendering)."""
        async with AsyncSessionLocal() as db:
            result = await db.execute(
                select(FolderCache)
                .where(
                    FolderCache.user_id == user_id,
                    FolderCache.parent_id == parent_id,
                )
                .order_by(FolderCache.name)
            )
            rows = result.scalars().all()

        return [
            {
                "file_id": r.file_id,
                "name": r.name,
                "full_path": r.full_path,
                "parent_id": r.parent_id,
                "has_children": bool(r.has_children),
            }
            for r in rows
        ]

    # ------------------------------------------------------------------
    # Background crawl
    # ------------------------------------------------------------------

    async def _crawl(self, session_id: str, user_id: str, drive_id: str) -> None:
        total = 0
        try:
            # Clear existing cache for this user
            async with AsyncSessionLocal() as db:
                await db.execute(
                    delete(FolderCache).where(FolderCache.user_id == user_id)
                )
                await db.commit()

            buffer: list[dict] = []
            await self._crawl_recursive(
                session_id=session_id,
                user_id=user_id,
                drive_id=drive_id,
                parent_id="root",
                parent_path="",
                buffer=buffer,
                total_ref=[0],
            )
            total = buffer.__len__()  # already flushed; use total_ref
            # Flush any remaining rows
            if buffer:
                await self._flush(user_id, buffer)
                buffer.clear()

            # Re-count from DB for accuracy
            async with AsyncSessionLocal() as db:
                result = await db.execute(
                    select(FolderCache).where(FolderCache.user_id == user_id)
                )
                total = len(result.scalars().all())

            await self._set_status(user_id, "ready", total)
            logger.info(
                "Folder index build complete for user %s: %d folders", user_id, total
            )

        except Exception as exc:
            logger.error(
                "Folder index build failed for user %s: %s", user_id, exc, exc_info=True
            )
            await self._set_status(user_id, "idle", 0)
        finally:
            _building.discard(user_id)

    async def _crawl_recursive(
        self,
        session_id: str,
        user_id: str,
        drive_id: str,
        parent_id: str,
        parent_path: str,
        buffer: list[dict],
        total_ref: list[int],
    ) -> None:
        from app.config import settings

        marker: str | None = None

        while True:
            async with AsyncSessionLocal() as db:
                auth_service = AuthService(db, settings, self._client)
                access_token = await auth_service.get_valid_access_token(session_id)

            try:
                page = await self._client.list_folders(
                    access_token=access_token,
                    drive_id=drive_id,
                    parent_file_id=parent_id,
                )
            except Exception as exc:
                logger.warning(
                    "Folder index: failed to list %s: %s", parent_id, exc
                )
                return

            for item in page:
                folder_path = (
                    f"{parent_path}/{item['name']}" if parent_path else item["name"]
                )
                buffer.append(
                    {
                        "file_id": item["file_id"],
                        "name": item["name"],
                        "parent_id": parent_id,
                        "full_path": folder_path,
                        "has_children": 1 if item.get("has_children", True) else 0,
                    }
                )
                total_ref[0] += 1

                # Flush every 200 rows to avoid large memory usage
                if len(buffer) >= 200:
                    await self._flush(user_id, buffer)
                    buffer.clear()

                # Recurse into sub-folders
                await self._crawl_recursive(
                    session_id=session_id,
                    user_id=user_id,
                    drive_id=drive_id,
                    parent_id=item["file_id"],
                    parent_path=folder_path,
                    buffer=buffer,
                    total_ref=total_ref,
                )
                await asyncio.sleep(0.05)

            # list_folders already handles pagination internally, so one call
            # returns all children — no next_marker loop needed here.
            break

    async def _flush(self, user_id: str, rows: list[dict]) -> None:
        """Bulk-upsert a batch of folder rows."""
        async with AsyncSessionLocal() as db:
            for row in rows:
                stmt = sqlite_insert(FolderCache).values(
                    user_id=user_id,
                    file_id=row["file_id"],
                    name=row["name"],
                    parent_id=row["parent_id"],
                    full_path=row["full_path"],
                    has_children=row["has_children"],
                )
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

    async def _set_status(
        self, user_id: str, status: str, total_folders: int
    ) -> None:
        built_at = int(time.time()) if status == "ready" else None
        async with AsyncSessionLocal() as db:
            stmt = sqlite_insert(FolderIndexMeta).values(
                user_id=user_id,
                status=status,
                total_folders=total_folders,
                built_at=built_at,
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=["user_id"],
                set_={
                    "status": status,
                    "total_folders": total_folders,
                    "built_at": built_at,
                },
            )
            await db.execute(stmt)
            await db.commit()
