"""Organization model — the top-level multi-tenancy boundary."""

from __future__ import annotations

from enum import Enum as PyEnum

from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from lablink.database import Base
from lablink.models.base import TimestampMixin, SoftDeleteMixin


if TYPE_CHECKING:
    from lablink.models.membership import Membership
    from lablink.models.api_token import ApiToken

class Tier(str, PyEnum):
    """Organization pricing tiers."""

    free = "free"
    starter = "starter"
    professional = "professional"
    enterprise = "enterprise"


class Organization(Base, TimestampMixin, SoftDeleteMixin):
    """A lab or research organization — the top-level tenant.

    All data is scoped to an organization; this is the multi-tenancy
    boundary for the entire platform.
    """

    __tablename__ = "organizations"

    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        doc="Display name",
    )
    slug: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        unique=True,
        index=True,
        doc="URL-safe unique identifier",
    )
    tier: Mapped[str] = mapped_column(
        String(20),
        default=Tier.free.value,
        nullable=False,
        doc="Current pricing tier",
    )
    storage_limit_bytes: Mapped[int] = mapped_column(
        BigInteger,
        default=5_368_709_120,  # 5 GB
        nullable=False,
        doc="Maximum storage in bytes",
    )
    instrument_limit: Mapped[int] = mapped_column(
        Integer,
        default=2,
        nullable=False,
        doc="Max number of registered instruments",
    )
    user_limit: Mapped[int] = mapped_column(
        Integer,
        default=1,
        nullable=False,
        doc="Max number of users",
    )

    # -- relationships -------------------------------------------------------
    memberships: Mapped[list["Membership"]] = relationship(  # noqa: F821
        "Membership",
        back_populates="organization",
        lazy="selectin",
        cascade="all, delete-orphan",
    )
    api_tokens: Mapped[list["ApiToken"]] = relationship(  # noqa: F821
        "ApiToken",
        back_populates="organization",
        lazy="selectin",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Organization id={self.id!r} slug={self.slug!r}>"
