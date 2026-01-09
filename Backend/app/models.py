import uuid
from datetime import datetime, time, timezone
from enum import Enum

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Enum as PgEnum,
    ForeignKey,
    Integer,
    String,
    Time,
    UniqueConstraint,
    func,
    JSON,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from .core.db import Base


class BookingStatus(str, Enum):
    HOLD = "HOLD"
    CONFIRMED = "CONFIRMED"
    EXPIRED = "EXPIRED"


class AppointmentStatus(str, Enum):
    """Operational status of an appointment (separate from BookingStatus)."""
    SCHEDULED = "SCHEDULED"
    IN_PROGRESS = "IN_PROGRESS"
    RUNNING_LATE = "RUNNING_LATE"
    COMPLETED = "COMPLETED"
    NO_SHOW = "NO_SHOW"


class TimeOffRequestStatus(str, Enum):
    """Status of employee time-off requests."""
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class CallSummaryStatus(str, Enum):
    """Status of the call outcome for owner summaries."""
    CONFIRMED = "confirmed"
    NOT_CONFIRMED = "not_confirmed"
    FOLLOW_UP = "follow_up"


class Shop(Base):
    __tablename__ = "shops"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Service(Base):
    __tablename__ = "services"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    price_cents: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (UniqueConstraint("shop_id", "name", name="uq_service_shop_name"),)


class Stylist(Base):
    __tablename__ = "stylists"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    work_start: Mapped[time] = mapped_column(Time, nullable=False)
    work_end: Mapped[time] = mapped_column(Time, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    pin_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    pin_set_at_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (UniqueConstraint("shop_id", "name", name="uq_stylist_shop_name"),)


class StylistSpecialty(Base):
    __tablename__ = "stylist_specialties"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    stylist_id: Mapped[int] = mapped_column(ForeignKey("stylists.id"), nullable=False, index=True)
    tag: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (UniqueConstraint("stylist_id", "tag", name="uq_stylist_specialty"),)


class TimeOffBlock(Base):
    __tablename__ = "time_off_blocks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    stylist_id: Mapped[int] = mapped_column(ForeignKey("stylists.id"), nullable=False, index=True)
    start_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    end_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class TimeOffRequest(Base):
    """Employee-submitted time-off requests pending owner approval."""
    __tablename__ = "time_off_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    stylist_id: Mapped[int] = mapped_column(ForeignKey("stylists.id"), nullable=False, index=True)
    start_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[TimeOffRequestStatus] = mapped_column(
        PgEnum(TimeOffRequestStatus), nullable=False, default=TimeOffRequestStatus.PENDING,
        server_default="PENDING"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    reviewed_at_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reviewer: Mapped[str | None] = mapped_column(String(255), nullable=True)


class Booking(Base):
    __tablename__ = "bookings"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, unique=True
    )
    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id"), nullable=False, index=True)
    service_id: Mapped[int] = mapped_column(ForeignKey("services.id"), nullable=False, index=True)
    secondary_service_id: Mapped[int | None] = mapped_column(
        ForeignKey("services.id"), nullable=True, index=True
    )
    stylist_id: Mapped[int] = mapped_column(ForeignKey("stylists.id"), nullable=False, index=True)
    customer_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    customer_email: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    customer_phone: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    preferred_style_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    preferred_style_image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    promo_id: Mapped[int | None] = mapped_column(ForeignKey("promos.id"), nullable=True, index=True)
    discount_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    start_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    end_at_utc: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    status: Mapped[BookingStatus] = mapped_column(PgEnum(BookingStatus), nullable=False)
    hold_expires_at_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sms_sent_at_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Employee view fields
    appointment_status: Mapped[AppointmentStatus] = mapped_column(
        PgEnum(AppointmentStatus), nullable=False, default=AppointmentStatus.SCHEDULED,
        server_default="SCHEDULED"
    )
    appointment_status_updated_at_utc: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    acknowledged_at_utc: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    internal_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint(
            "stylist_id",
            "start_at_utc",
            "end_at_utc",
            name="uq_booking_stylist_time_range",
        ),
    )

    def is_hold_active(self, now: datetime) -> bool:
        return (
            self.status == BookingStatus.HOLD
            and self.hold_expires_at_utc is not None
            and self.hold_expires_at_utc > now
        )

    def is_confirmed(self) -> bool:
        return self.status == BookingStatus.CONFIRMED

    @staticmethod
    def now_utc() -> datetime:
        return datetime.now(timezone.utc)


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    preferred_stylist_id: Mapped[int | None] = mapped_column(ForeignKey("stylists.id"), nullable=True)
    average_spend_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    no_show_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class CustomerBookingStats(Base):
    __tablename__ = "customer_booking_stats"

    customer_id: Mapped[int] = mapped_column(
        ForeignKey("customers.id"), primary_key=True, nullable=False
    )
    total_bookings: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_spend_cents: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_booking_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class CustomerStylistPreference(Base):
    __tablename__ = "customer_stylist_preferences"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), nullable=False, index=True)
    stylist_id: Mapped[int] = mapped_column(ForeignKey("stylists.id"), nullable=False, index=True)
    booking_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint(
            "customer_id",
            "stylist_id",
            name="uq_customer_stylist_preference",
        ),
    )


class CustomerServicePreference(Base):
    __tablename__ = "customer_service_preferences"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), nullable=False, index=True)
    service_id: Mapped[int] = mapped_column(ForeignKey("services.id"), nullable=False, index=True)
    preferred_style_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    preferred_style_image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at_utc: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    __table_args__ = (
        UniqueConstraint(
            "customer_id",
            "service_id",
            name="uq_customer_service_preference",
        ),
    )


class ServiceRule(Base):
    __tablename__ = "service_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    service_id: Mapped[int] = mapped_column(ForeignKey("services.id"), nullable=False, unique=True, index=True)
    rule: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class PromoType(str, Enum):
    FIRST_USER_PROMO = "FIRST_USER_PROMO"
    DAILY_PROMO = "DAILY_PROMO"
    SEASONAL_PROMO = "SEASONAL_PROMO"
    SERVICE_COMBO_PROMO = "SERVICE_COMBO_PROMO"


class PromoTriggerPoint(str, Enum):
    AT_CHAT_START = "AT_CHAT_START"
    AFTER_EMAIL_CAPTURE = "AFTER_EMAIL_CAPTURE"
    AFTER_SERVICE_SELECTED = "AFTER_SERVICE_SELECTED"
    AFTER_SLOT_SHOWN = "AFTER_SLOT_SHOWN"
    AFTER_HOLD_CREATED = "AFTER_HOLD_CREATED"


class PromoDiscountType(str, Enum):
    PERCENT = "PERCENT"
    FIXED = "FIXED"
    FREE_ADDON = "FREE_ADDON"
    BUNDLE = "BUNDLE"


class Promo(Base):
    __tablename__ = "promos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id"), nullable=False, index=True)
    type: Mapped[PromoType] = mapped_column(PgEnum(PromoType), nullable=False)
    trigger_point: Mapped[PromoTriggerPoint] = mapped_column(PgEnum(PromoTriggerPoint), nullable=False)
    service_id: Mapped[int | None] = mapped_column(
        ForeignKey("services.id"), nullable=True, index=True
    )
    discount_type: Mapped[PromoDiscountType] = mapped_column(PgEnum(PromoDiscountType), nullable=False)
    discount_value: Mapped[int | None] = mapped_column(Integer, nullable=True)
    constraints_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    custom_copy: Mapped[str | None] = mapped_column(Text, nullable=True)
    start_at_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    end_at_utc: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class PromoImpression(Base):
    __tablename__ = "promo_impressions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    promo_id: Mapped[int] = mapped_column(ForeignKey("promos.id"), nullable=False, index=True)
    shop_id: Mapped[int] = mapped_column(ForeignKey("shops.id"), nullable=False, index=True)
    identity_key: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    day_bucket: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint(
            "promo_id",
            "shop_id",
            "identity_key",
            "day_bucket",
            name="uq_promo_impression_daily",
        ),
    )


# ────────────────────────────────────────────────────────────────
# Call Summaries - Internal owner feature for voice call tracking
# ────────────────────────────────────────────────────────────────


class CallSummary(Base):
    """
    Stores AI-generated summaries of voice calls for salon owners.
    Generated after each completed phone call handled by the voice agent.
    """
    __tablename__ = "call_summaries"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    call_sid: Mapped[str] = mapped_column(String(64), nullable=False, index=True, unique=True)
    customer_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    customer_phone: Mapped[str] = mapped_column(String(20), nullable=False)
    service: Mapped[str | None] = mapped_column(String(255), nullable=True)
    stylist: Mapped[str | None] = mapped_column(String(255), nullable=True)
    appointment_date: Mapped[str | None] = mapped_column(String(20), nullable=True)  # YYYY-MM-DD
    appointment_time: Mapped[str | None] = mapped_column(String(20), nullable=True)  # HH:MM format
    booking_status: Mapped[CallSummaryStatus] = mapped_column(
        PgEnum(CallSummaryStatus), nullable=False, default=CallSummaryStatus.NOT_CONFIRMED
    )
    key_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    transcript: Mapped[str | None] = mapped_column(Text, nullable=True)  # Full transcript for reference
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
