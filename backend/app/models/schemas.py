"""
Pydantic data models (schemas) for the AliyunDrive duplicate cleaner.
"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from app.core.file_type import FileType


class DuplicateFile(BaseModel):
    """Represents a single duplicate file returned by the AliyunDrive API."""

    file_id: str
    file_name: str
    file_path: str
    file_size: int  # bytes
    content_hash: str  # SHA1 hash
    modified_at: datetime
    file_type: FileType


class DuplicateGroup(BaseModel):
    """A group of files that share the same content hash."""

    group_id: str  # content_hash used as group identifier
    file_name: str  # representative file name for the group
    file_size: int
    content_hash: str
    duplicate_count: int
    file_type: FileType
    files: list[DuplicateFile]


class DuplicateListPage(BaseModel):
    """A single page of duplicate file groups returned by the API."""

    items: list[DuplicateGroup]
    next_marker: str | None = None
    total_count: int | None = None


class TokenPair(BaseModel):
    """OAuth token pair returned after authorization or token refresh."""

    access_token: str
    refresh_token: str
    expires_in: int  # seconds until access_token expires
    token_type: str = "Bearer"


class ScanResult(BaseModel):
    """Aggregated result of a completed duplicate-file scan task."""

    task_id: str
    total_groups: int
    total_files: int
    total_size_bytes: int
    scanned_file_count: int = 0  # total files traversed during scan
    groups: list[DuplicateGroup]


class BatchResult(BaseModel):
    """Result of a batch trash or permanent-delete operation."""

    success_ids: list[str]
    # Each item contains at least "file_id" and "error_msg" keys
    failed_items: list[dict]
