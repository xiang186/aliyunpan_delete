"""
SQLAlchemy ORM models for the application database.

Tables:
  - sessions:        stores encrypted OAuth tokens per user session
  - tasks:           stores delete task history
  - task_files:      stores per-file results for each task
  - scanned_folder:  per-user directory scan state (for incremental scan)
  - folder_cache:    cached folder tree for the folder-picker dialog
  - folder_index_meta: per-user folder index build status
"""
from sqlalchemy import (
    Index,
    Integer,
    Text,
    ForeignKey,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


class UserSession(Base):
    """OAuth session with encrypted token storage."""

    __tablename__ = "sessions"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    user_id: Mapped[str] = mapped_column(Text, nullable=False)
    nickname: Mapped[str | None] = mapped_column(Text, nullable=True)
    access_token_enc: Mapped[str] = mapped_column(Text, nullable=False)
    refresh_token_enc: Mapped[str] = mapped_column(Text, nullable=False)
    token_expires_at: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[int] = mapped_column(Integer, nullable=False)
    updated_at: Mapped[int] = mapped_column(Integer, nullable=False)

    tasks: Mapped[list["Task"]] = relationship("Task", back_populates="session")


class Task(Base):
    """Delete task history record."""

    __tablename__ = "tasks"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    session_id: Mapped[str] = mapped_column(Text, ForeignKey("sessions.id"), nullable=False)
    delete_type: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    total_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    success_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    freed_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    started_at: Mapped[int] = mapped_column(Integer, nullable=False)
    completed_at: Mapped[int | None] = mapped_column(Integer, nullable=True)

    session: Mapped["UserSession"] = relationship("UserSession", back_populates="tasks")
    files: Mapped[list["TaskFile"]] = relationship("TaskFile", back_populates="task")


class TaskFile(Base):
    """Per-file result record for a delete task."""

    __tablename__ = "task_files"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[str] = mapped_column(Text, ForeignKey("tasks.id"), nullable=False)
    file_id: Mapped[str] = mapped_column(Text, nullable=False)
    file_name: Mapped[str] = mapped_column(Text, nullable=False)
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    result: Mapped[str] = mapped_column(Text, nullable=False)
    error_msg: Mapped[str | None] = mapped_column(Text, nullable=True)

    task: Mapped["Task"] = relationship("Task", back_populates="files")

    __table_args__ = (
        Index("idx_task_files_task_id", "task_id"),
    )


class ScannedFolder(Base):
    """
    Per-user directory scan state used for incremental scanning.

    After a full scan, every directory that was visited is recorded here with
    the ``updated_at`` value returned by the AliyunDrive API at scan time.

    On the next incremental scan, if a directory's current ``updated_at``
    matches the stored value, the directory is skipped entirely.  If it has
    changed (or is not in the table), the directory is re-scanned.

    Keyed by (user_id, folder_id) — one row per directory per user.
    """

    __tablename__ = "scanned_folder"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(Text, nullable=False)
    folder_id: Mapped[str] = mapped_column(Text, nullable=False)   # AliyunDrive folder ID
    updated_at: Mapped[str] = mapped_column(Text, nullable=False)  # ISO-8601 from API at scan time

    __table_args__ = (
        Index("idx_scanned_folder_user", "user_id"),
        Index("idx_scanned_folder_user_folder", "user_id", "folder_id", unique=True),
    )


class FolderCache(Base):
    """
    Cached folder tree for the folder-picker dialog.

    Built in the background after the folder-picker dialog is first opened.
    Enables full-text search across all directory levels without lazy loading.
    """

    __tablename__ = "folder_cache"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(Text, nullable=False)
    file_id: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    parent_id: Mapped[str] = mapped_column(Text, nullable=False)
    full_path: Mapped[str] = mapped_column(Text, nullable=False)
    has_children: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    __table_args__ = (
        Index("idx_folder_cache_user_id", "user_id"),
        Index("idx_folder_cache_user_file", "user_id", "file_id", unique=True),
        Index("idx_folder_cache_user_parent", "user_id", "parent_id"),
        Index("idx_folder_cache_user_name", "user_id", "name"),
    )


class FolderIndexMeta(Base):
    """Per-user folder index build status for the folder-picker dialog."""

    __tablename__ = "folder_index_meta"

    user_id: Mapped[str] = mapped_column(Text, primary_key=True)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="idle")
    total_folders: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    built_at: Mapped[int | None] = mapped_column(Integer, nullable=True)
