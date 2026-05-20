"""
SQLAlchemy ORM models for the application database.

Tables:
  - sessions: stores encrypted OAuth tokens per user session
  - tasks:    stores delete task history
  - task_files: stores per-file results for each task
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

    id: Mapped[str] = mapped_column(Text, primary_key=True)          # UUID
    user_id: Mapped[str] = mapped_column(Text, nullable=False)
    nickname: Mapped[str | None] = mapped_column(Text, nullable=True)
    access_token_enc: Mapped[str] = mapped_column(Text, nullable=False)
    refresh_token_enc: Mapped[str] = mapped_column(Text, nullable=False)
    token_expires_at: Mapped[int] = mapped_column(Integer, nullable=False)  # Unix timestamp
    created_at: Mapped[int] = mapped_column(Integer, nullable=False)        # Unix timestamp
    updated_at: Mapped[int] = mapped_column(Integer, nullable=False)        # Unix timestamp

    # Relationship
    tasks: Mapped[list["Task"]] = relationship("Task", back_populates="session")


class Task(Base):
    """Delete task history record."""

    __tablename__ = "tasks"

    id: Mapped[str] = mapped_column(Text, primary_key=True)          # UUID
    session_id: Mapped[str] = mapped_column(
        Text, ForeignKey("sessions.id"), nullable=False
    )
    delete_type: Mapped[str] = mapped_column(Text, nullable=False)   # 'trash' | 'permanent'
    status: Mapped[str] = mapped_column(Text, nullable=False)        # 'running' | 'completed' | 'failed'
    total_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    success_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    freed_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    started_at: Mapped[int] = mapped_column(Integer, nullable=False)         # Unix timestamp
    completed_at: Mapped[int | None] = mapped_column(Integer, nullable=True) # Unix timestamp, nullable

    # Relationships
    session: Mapped["UserSession"] = relationship("UserSession", back_populates="tasks")
    files: Mapped[list["TaskFile"]] = relationship("TaskFile", back_populates="task")


class TaskFile(Base):
    """Per-file result record for a delete task."""

    __tablename__ = "task_files"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[str] = mapped_column(
        Text, ForeignKey("tasks.id"), nullable=False
    )
    file_id: Mapped[str] = mapped_column(Text, nullable=False)       # AliyunDrive file ID
    file_name: Mapped[str] = mapped_column(Text, nullable=False)
    file_path: Mapped[str] = mapped_column(Text, nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    result: Mapped[str] = mapped_column(Text, nullable=False)        # 'success' | 'failed' | 'skipped'
    error_msg: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationship
    task: Mapped["Task"] = relationship("Task", back_populates="files")

    __table_args__ = (
        Index("idx_task_files_task_id", "task_id"),
    )
