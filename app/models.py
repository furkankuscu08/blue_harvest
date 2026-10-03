"""Database models: the shape of the data.

These classes only hold state. The rules that change them live in app.domain.
"""

from datetime import datetime
from enum import StrEnum

from sqlalchemy import ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Role(StrEnum):
    RELATIONSHIP_MANAGER = "RELATIONSHIP_MANAGER"
    REVIEWER = "REVIEWER"
    MORTGAGE_PROCESS = "MORTGAGE_PROCESS"


class Status(StrEnum):
    PENDING = "PENDING"
    DECLINED = "DECLINED"
    APPROVED = "APPROVED"


class Outcome(StrEnum):
    """A decision's outcome. PENDING is a request status, never an outcome."""

    APPROVED = "APPROVED"
    DECLINED = "DECLINED"


class Base(DeclarativeBase):
    pass


class Application(Base):
    __tablename__ = "applications"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    customer_name: Mapped[str] = mapped_column(String(200))


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    roles: Mapped[list["UserRole"]] = relationship(cascade="all, delete-orphan")


class UserRole(Base):
    __tablename__ = "user_roles"

    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), primary_key=True)
    role: Mapped[Role] = mapped_column(primary_key=True)


class ExceptionRequest(Base):
    __tablename__ = "exception_requests"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    # I1: an application has at most one request.
    application_id: Mapped[str] = mapped_column(ForeignKey("applications.id"), unique=True)
    status: Mapped[Status]
    version: Mapped[int]
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]
    revisions: Mapped[list["Revision"]] = relationship(
        order_by="Revision.number", cascade="all, delete-orphan"
    )


class Revision(Base):
    __tablename__ = "revisions"
    __table_args__ = (UniqueConstraint("request_id", "number"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    request_id: Mapped[str] = mapped_column(ForeignKey("exception_requests.id"))
    number: Mapped[int]
    discount_bps: Mapped[int]
    reason: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime]
    decision: Mapped["Decision | None"] = relationship(cascade="all, delete-orphan")


class Decision(Base):
    __tablename__ = "decisions"

    id: Mapped[int] = mapped_column(primary_key=True)
    # I6: a revision has at most one decision.
    revision_id: Mapped[int] = mapped_column(ForeignKey("revisions.id"), unique=True)
    outcome: Mapped[Outcome]
    decided_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    decided_at: Mapped[datetime]
    comment: Mapped[str | None] = mapped_column(Text)
