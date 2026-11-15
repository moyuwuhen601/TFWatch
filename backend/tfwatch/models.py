from sqlalchemy import Boolean, ForeignKey, Index, Integer, LargeBinary, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base, now


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True)
    password_hash: Mapped[str] = mapped_column(String(250))
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    notify_mode: Mapped[str] = mapped_column(String(10), default="open")


class SessionToken(Base):
    __tablename__ = "sessions"

    digest: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    expires: Mapped[int] = mapped_column(Integer, index=True)


class AccountToken(Base):
    __tablename__ = "account_tokens"

    digest: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    expires: Mapped[int] = mapped_column(Integer, index=True)
    purpose: Mapped[str] = mapped_column(String(10))


class Settings(Base):
    __tablename__ = "settings"

    id: Mapped[int] = mapped_column(primary_key=True)
    registration: Mapped[bool] = mapped_column(Boolean, default=True)
    anonymous: Mapped[bool] = mapped_column(Boolean, default=True)
    interval: Mapped[int] = mapped_column(Integer, default=300)


class App(Base):
    __tablename__ = "apps"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(180), index=True)
    aliases: Mapped[str] = mapped_column(String(300), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    icon: Mapped[str] = mapped_column(String(1000), default="")


class Invite(Base):
    __tablename__ = "invites"

    code: Mapped[str] = mapped_column(String(8), primary_key=True)
    app_id: Mapped[int] = mapped_column(ForeignKey("apps.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(10), default="unknown")
    last_known: Mapped[str | None] = mapped_column(String(10))
    checked_at: Mapped[int | None] = mapped_column(Integer)
    due_at: Mapped[int] = mapped_column(Integer, default=0, index=True)
    lease_until: Mapped[int] = mapped_column(Integer, default=0)
    failures: Mapped[int] = mapped_column(Integer, default=0)


class CheckLog(Base):
    __tablename__ = "check_logs"
    __table_args__ = (Index("ix_check_logs_code_time", "code", "checked_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(ForeignKey("invites.code", ondelete="CASCADE"))
    checked_at: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(10))
    interval: Mapped[int] = mapped_column(Integer)


class StatusEvent(Base):
    __tablename__ = "status_events"
    __table_args__ = (Index("ix_status_events_code_time", "code", "checked_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(ForeignKey("invites.code", ondelete="CASCADE"))
    checked_at: Mapped[int] = mapped_column(Integer)
    previous: Mapped[str | None] = mapped_column(String(10))
    status: Mapped[str] = mapped_column(String(10))


class Subscription(Base):
    __tablename__ = "subscriptions"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    code: Mapped[str] = mapped_column(ForeignKey("invites.code", ondelete="CASCADE"), primary_key=True, index=True)


class Channel(Base):
    __tablename__ = "channels"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(10))
    label: Mapped[str] = mapped_column(String(60))
    encrypted: Mapped[bytes] = mapped_column(LargeBinary)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class Delivery(Base):
    __tablename__ = "deliveries"

    id: Mapped[int] = mapped_column(primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("status_events.id", ondelete="CASCADE"))
    channel_id: Mapped[int] = mapped_column(ForeignKey("channels.id", ondelete="CASCADE"), index=True)
    state: Mapped[str] = mapped_column(String(12), default="pending")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    due_at: Mapped[int] = mapped_column(Integer, default=now)
    lease_until: Mapped[int] = mapped_column(Integer, default=0)

    __table_args__ = (
        UniqueConstraint("event_id", "channel_id"),
        Index("ix_deliveries_queue", "state", "due_at"),
    )

