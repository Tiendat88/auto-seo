"""ORM models for publish targets and publish jobs."""

import uuid
from datetime import datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class PublishMode(StrEnum):
    DRAFT = "draft"
    PUBLISHED = "published"


class PublishJobStatus(StrEnum):
    PENDING = "pending"
    SENT = "sent"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"


class PublishTarget(Base):
    """A custom website endpoint that can receive auto-posted articles."""

    __tablename__ = "publish_targets"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    name: Mapped[str] = mapped_column(String(200))
    endpoint_url: Mapped[str] = mapped_column(String(2048))
    secret_key: Mapped[str] = mapped_column(String(500))
    default_mode: Mapped[str] = mapped_column(
        Enum(PublishMode), default=PublishMode.DRAFT
    )
    auto_publish: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    def to_dict(self, *, hide_secret: bool = True) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "endpoint_url": self.endpoint_url,
            "secret_key": "sk_***" + self.secret_key[-4:] if hide_secret else self.secret_key,
            "default_mode": self.default_mode,
            "auto_publish": self.auto_publish,
            "created_at": self.created_at.isoformat(),
        }


class PublishJob(Base):
    """A record of an article publish attempt."""

    __tablename__ = "publish_jobs"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    job_id: Mapped[str] = mapped_column(String(36), index=True)          # AutoSEO job id
    target_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("publish_targets.id", ondelete="SET NULL"), nullable=True
    )
    target_name: Mapped[str] = mapped_column(String(200), default="")    # snapshot
    target_url: Mapped[str] = mapped_column(String(2048), default="")    # snapshot
    mode: Mapped[str] = mapped_column(Enum(PublishMode), default=PublishMode.DRAFT)
    status: Mapped[str] = mapped_column(
        Enum(PublishJobStatus), default=PublishJobStatus.PENDING, index=True
    )
    article_title: Mapped[str] = mapped_column(String(500), default="")
    article_slug: Mapped[str] = mapped_column(String(500), default="")
    published_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "job_id": self.job_id,
            "target_id": self.target_id,
            "target_name": self.target_name,
            "target_url": self.target_url,
            "mode": self.mode,
            "status": self.status,
            "article_title": self.article_title,
            "article_slug": self.article_slug,
            "published_url": self.published_url,
            "error_message": self.error_message,
            "retry_count": self.retry_count,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }
