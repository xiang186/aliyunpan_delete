"""
Repository for file_cache and scan_meta tables.

Provides helpers used by ScanService and DeleteService to:
  - Read/write cached file metadata per user
  - Track the last full-scan timestamp
  - Remove deleted files from the cache
"""
from __future__ import annotations

import logging
import time
from typing import Sequence

from sqlalchemy import delete, select, text
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import FileCache, ScanMeta

logger = logging.getLogger(__name__)


class FileCacheRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    # ------------------------------------------------------------------
    # ScanMeta helpers
    # ------------------------------------------------------------------

    async def get_scan_meta(self, user_id: str) -> ScanMeta | None:
        result = await self._db.execute(
            select(ScanMeta).where(ScanMeta.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def upsert_scan_meta(
        self,
        user_id: str,
        last_full_scan_at: int,
        drive_id: str,
    ) -> None:
        stmt = sqlite_insert(ScanMeta).values(
            user_id=user_id,
            last_full_scan_at=last_full_scan_at,
            drive_id=drive_id,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["user_id"],
            set_={
                "last_full_scan_at": last_full_scan_at,
                "drive_id": drive_id,
            },
        )
        await self._db.execute(stmt)
        await self._db.commit()

    # ------------------------------------------------------------------
    # FileCache read helpers
    # ------------------------------------------------------------------

    async def has_cache(self, user_id: str) -> bool:
        """Return True if there is at least one cached file for this user."""
        result = await self._db.execute(
            select(FileCache.id).where(FileCache.user_id == user_id).limit(1)
        )
        return result.scalar_one_or_none() is not None

    async def get_all_files(self, user_id: str) -> Sequence[FileCache]:
        """Return all cached file rows for a user."""
        result = await self._db.execute(
            select(FileCache).where(FileCache.user_id == user_id)
        )
        return result.scalars().all()

    async def get_file_ids(self, user_id: str) -> set[str]:
        """Return the set of cached file_ids for a user."""
        result = await self._db.execute(
            select(FileCache.file_id).where(FileCache.user_id == user_id)
        )
        return {row for row in result.scalars().all()}

    # ------------------------------------------------------------------
    # FileCache write helpers
    # ------------------------------------------------------------------

    async def upsert_files(self, user_id: str, files: list[dict]) -> None:
        """
        Insert or update file cache rows.

        Each dict in *files* must have keys:
          file_id, file_name, file_path, file_size, content_hash, updated_at
        """
        if not files:
            return

        for f in files:
            stmt = sqlite_insert(FileCache).values(
                user_id=user_id,
                file_id=f["file_id"],
                file_name=f["file_name"],
                file_path=f["file_path"],
                file_size=f["file_size"],
                content_hash=f["content_hash"],
                updated_at=f["updated_at"],
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=["user_id", "file_id"],
                set_={
                    "file_name": f["file_name"],
                    "file_path": f["file_path"],
                    "file_size": f["file_size"],
                    "content_hash": f["content_hash"],
                    "updated_at": f["updated_at"],
                },
            )
            await self._db.execute(stmt)

        await self._db.commit()
        logger.debug("Upserted %d file cache rows for user %s", len(files), user_id)

    async def delete_files(self, user_id: str, file_ids: list[str]) -> int:
        """
        Remove file_ids from the cache for a user.

        Returns the number of rows deleted.
        """
        if not file_ids:
            return 0
        result = await self._db.execute(
            delete(FileCache).where(
                FileCache.user_id == user_id,
                FileCache.file_id.in_(file_ids),
            )
        )
        await self._db.commit()
        count: int = result.rowcount
        logger.info(
            "Removed %d file(s) from cache for user %s", count, user_id
        )
        return count

    async def clear_cache(self, user_id: str) -> None:
        """Delete all cached files for a user (used before a forced full scan)."""
        await self._db.execute(
            delete(FileCache).where(FileCache.user_id == user_id)
        )
        await self._db.commit()
        logger.info("Cleared file cache for user %s", user_id)
