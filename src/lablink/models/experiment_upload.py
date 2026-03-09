"""ExperimentUpload model — many-to-many link between experiments and uploads."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from lablink.database import Base


class ExperimentUpload(Base):
    """Many-to-many link between experiments and uploads.

    Uses a composite primary key (experiment_id, upload_id).
    Tracks which instrument files/uploads are associated with an experiment,
    along with who linked them and when.
    """

    __tablename__ = "experiment_uploads"
    __table_args__ = (UniqueConstraint("experiment_id", "upload_id", name="uq_experiment_upload"),)

    experiment_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("experiments.id", ondelete="CASCADE"),
        primary_key=True,
    )
    upload_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("uploads.id", ondelete="CASCADE"),
        primary_key=True,
    )
    linked_by: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    linked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
        nullable=False,
    )

    # -- relationships -------------------------------------------------------
    experiment: Mapped["Experiment"] = relationship(  # noqa: F821
        "Experiment",
        back_populates="uploads",
    )

    def __repr__(self) -> str:
        return (
            f"<ExperimentUpload experiment_id={self.experiment_id!r} upload_id={self.upload_id!r}>"
        )
