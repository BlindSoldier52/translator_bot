import datetime

from sqlalchemy import (
	BigInteger,
	Boolean,
	Date,
	DateTime,
	ForeignKey,
	Integer,
	String,
	Text,
	UniqueConstraint,
	func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
	pass


class User(Base):
	__tablename__ = "users"

	id: Mapped[int] = mapped_column(Integer, primary_key=True)
	telegram_user_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
	username: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
	password_hash: Mapped[str] = mapped_column(Text, nullable=False)
	is_blocked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
	created_at: Mapped[datetime.datetime] = mapped_column(
		DateTime(timezone=True), server_default=func.now(), nullable=False
	)

	api_key_provider: Mapped[str | None] = mapped_column(String(20), nullable=True)
	api_key_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
	api_key_updated_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

	file_translation_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
	file_allowed_extensions: Mapped[list[str]] = mapped_column(
		JSONB, default=lambda: [".txt", ".pdf"], nullable=False
	)
	file_max_size_mb: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
	file_output_mode: Mapped[str] = mapped_column(String(10), default="text", nullable=False)

	image_translation_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
	image_max_size_mb: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
	image_output_mode: Mapped[str] = mapped_column(String(10), default="text", nullable=False)

	groups: Mapped[list["Group"]] = relationship(back_populates="owner")


class AdminUser(Base):
	__tablename__ = "admin_users"

	id: Mapped[int] = mapped_column(Integer, primary_key=True)
	username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
	password_hash: Mapped[str] = mapped_column(Text, nullable=False)
	created_at: Mapped[datetime.datetime] = mapped_column(
		DateTime(timezone=True), server_default=func.now(), nullable=False
	)


class Group(Base):
	__tablename__ = "groups"

	id: Mapped[int] = mapped_column(Integer, primary_key=True)
	telegram_chat_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
	title: Mapped[str] = mapped_column(String(255), nullable=False)

	owner_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
	owner: Mapped[User | None] = relationship(back_populates="groups")

	primary_language: Mapped[str | None] = mapped_column(String(16), nullable=True)
	language_mode: Mapped[str] = mapped_column(String(16), default="manual", nullable=False)
	language_votes: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
	language_sample_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

	is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
	is_blocked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

	daily_message_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)

	file_translation_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
	file_allowed_extensions: Mapped[list[str]] = mapped_column(
		JSONB, default=lambda: [".txt", ".pdf"], nullable=False
	)
	file_max_size_mb: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
	file_output_mode: Mapped[str] = mapped_column(String(10), default="text", nullable=False)
	file_uses_separate_daily_limit: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
	file_daily_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)

	image_translation_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
	image_max_size_mb: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
	image_output_mode: Mapped[str] = mapped_column(String(10), default="text", nullable=False)
	image_uses_separate_daily_limit: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
	image_daily_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)

	created_at: Mapped[datetime.datetime] = mapped_column(
		DateTime(timezone=True), server_default=func.now(), nullable=False
	)
	updated_at: Mapped[datetime.datetime] = mapped_column(
		DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
	)


class Translation(Base):
	"""One row per translation, for counting only. No message content is kept."""

	__tablename__ = "translations"

	id: Mapped[int] = mapped_column(Integer, primary_key=True)
	group_id: Mapped[int] = mapped_column(ForeignKey("groups.id"), nullable=False, index=True)

	source_lang: Mapped[str] = mapped_column(String(16), nullable=False)
	target_lang: Mapped[str] = mapped_column(String(16), nullable=False)

	created_at: Mapped[datetime.datetime] = mapped_column(
		DateTime(timezone=True), server_default=func.now(), nullable=False
	)

	group: Mapped[Group] = relationship()


class AppSettings(Base):
	__tablename__ = "app_settings"

	id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
	daily_message_limit: Mapped[int] = mapped_column(Integer, nullable=False)
	maintenance_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
	maintenance_message: Mapped[str | None] = mapped_column(Text, nullable=True)
	updated_at: Mapped[datetime.datetime] = mapped_column(
		DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
	)


class GroupMaintenanceNotice(Base):
	__tablename__ = "group_maintenance_notices"

	group_id: Mapped[int] = mapped_column(ForeignKey("groups.id"), primary_key=True)
	notified_at: Mapped[datetime.datetime] = mapped_column(
		DateTime(timezone=True), server_default=func.now(), nullable=False
	)


class DailyCounter(Base):
	__tablename__ = "daily_counters"

	date: Mapped[datetime.date] = mapped_column(Date, primary_key=True)
	translated_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class GroupDailyCounter(Base):
	__tablename__ = "group_daily_counters"

	group_id: Mapped[int] = mapped_column(ForeignKey("groups.id"), primary_key=True)
	date: Mapped[datetime.date] = mapped_column(Date, primary_key=True)
	translated_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class GroupFileDailyCounter(Base):
	__tablename__ = "group_file_daily_counters"

	group_id: Mapped[int] = mapped_column(ForeignKey("groups.id"), primary_key=True)
	date: Mapped[datetime.date] = mapped_column(Date, primary_key=True)
	translated_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class GroupImageDailyCounter(Base):
	__tablename__ = "group_image_daily_counters"

	group_id: Mapped[int] = mapped_column(ForeignKey("groups.id"), primary_key=True)
	date: Mapped[datetime.date] = mapped_column(Date, primary_key=True)
	translated_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class GroupWarning(Base):
	__tablename__ = "group_warnings"
	__table_args__ = (UniqueConstraint("group_id", "date"),)

	id: Mapped[int] = mapped_column(Integer, primary_key=True)
	group_id: Mapped[int] = mapped_column(ForeignKey("groups.id"), nullable=False)
	date: Mapped[datetime.date] = mapped_column(Date, nullable=False)
	sent_at: Mapped[datetime.datetime] = mapped_column(
		DateTime(timezone=True), server_default=func.now(), nullable=False
	)


class Announcement(Base):
	__tablename__ = "announcements"

	id: Mapped[int] = mapped_column(Integer, primary_key=True)
	body: Mapped[str] = mapped_column(Text, nullable=False)
	created_by_admin_id: Mapped[int | None] = mapped_column(
		ForeignKey("admin_users.id"), nullable=True, index=True
	)
	created_at: Mapped[datetime.datetime] = mapped_column(
		DateTime(timezone=True), server_default=func.now(), nullable=False
	)


class AnnouncementDelivery(Base):
	__tablename__ = "announcement_deliveries"
	__table_args__ = (UniqueConstraint("announcement_id", "user_id"),)

	id: Mapped[int] = mapped_column(Integer, primary_key=True)
	announcement_id: Mapped[int] = mapped_column(ForeignKey("announcements.id"), nullable=False)
	user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
	status: Mapped[str] = mapped_column(String(10), default="pending", nullable=False)
	attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
	sent_at: Mapped[datetime.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Feedback(Base):
	__tablename__ = "feedback"

	id: Mapped[int] = mapped_column(Integer, primary_key=True)
	user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
	message: Mapped[str] = mapped_column(Text, nullable=False)
	created_at: Mapped[datetime.datetime] = mapped_column(
		DateTime(timezone=True), server_default=func.now(), nullable=False
	)
	is_reviewed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class LoginAttempt(Base):
	"""Failed credential checks, shared by every process that verifies a credential.

	Kept in the database rather than in memory so that the bot, the panel, and any
	number of panel workers enforce one lockout budget between them instead of one
	each. Written and read through LoginGuard in shared/lockout.py.
	"""

	__tablename__ = "login_attempts"

	guard: Mapped[str] = mapped_column(String(32), primary_key=True)
	identifier: Mapped[str] = mapped_column(String(255), primary_key=True)
	failures: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
	last_failure_at: Mapped[datetime.datetime] = mapped_column(
		DateTime(timezone=True), nullable=False
	)
	locked_until: Mapped[datetime.datetime | None] = mapped_column(
		DateTime(timezone=True), nullable=True, index=True
	)
