"""Database tables: outlets, raw power readings and hourly energy totals.

Datetimes are stored as UTC and always come back timezone-aware (see `UtcDateTime`).
"""

from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Index, String
from sqlalchemy.engine import Dialect
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import TypeDecorator


def utcnow() -> datetime:
    """Current time as a timezone-aware UTC datetime."""
    return datetime.now(UTC)


class UtcDateTime(TypeDecorator[datetime]):
    """A DateTime column that stores UTC and returns timezone-aware datetimes.

    SQLite cannot store a time zone, so the value is written as UTC without one and the
    zone is added back when reading. Naive datetimes are rejected: their zone is unknown.
    """

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("naive datetime: pass a timezone-aware one")
        return value.astimezone(UTC).replace(tzinfo=None)

    def process_result_value(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        return value.replace(tzinfo=UTC)


class Base(DeclarativeBase):
    pass


class Outlet(Base):
    """A smart plug, kept in sync with config/outlets.yaml."""

    __tablename__ = "outlets"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Stable identifier chosen in the YAML; it is how a plug is recognised across restarts.
    slug: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(128))
    ip: Mapped[str] = mapped_column(String(64))


class Reading(Base):
    """One instantaneous power sample. Deleted after `raw_retention_days`."""

    __tablename__ = "readings"

    id: Mapped[int] = mapped_column(primary_key=True)
    outlet_id: Mapped[int] = mapped_column(ForeignKey("outlets.id"))
    ts: Mapped[datetime] = mapped_column(UtcDateTime)
    power_w: Mapped[float]

    __table_args__ = (Index("ix_readings_outlet_ts", "outlet_id", "ts"),)


class HourlyEnergy(Base):
    """Energy used by one outlet during one UTC hour. Kept forever."""

    __tablename__ = "hourly_energy"

    outlet_id: Mapped[int] = mapped_column(ForeignKey("outlets.id"), primary_key=True)
    hour_start: Mapped[datetime] = mapped_column(UtcDateTime, primary_key=True)
    kwh: Mapped[float]
    # Seconds of the hour that have data: 3600 for a full hour, less if the app was off.
    seconds_covered: Mapped[int]
