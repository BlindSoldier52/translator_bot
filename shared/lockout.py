import datetime

from sqlalchemy import case, delete, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from shared.db import session_scope
from shared.models import LoginAttempt

MAX_BACKOFF_STEPS = 20
MAX_IDENTIFIER_CHARS = 255


def now() -> datetime.datetime:
	return datetime.datetime.now(datetime.timezone.utc)


def as_utc(value: datetime.datetime) -> datetime.datetime:
	"""Read a stored timestamp as UTC even if the driver hands it back without a zone."""
	if value.tzinfo is None:
		return value.replace(tzinfo=datetime.timezone.utc)
	return value


class LoginGuard:
	"""Tracks failed credential checks per identifier and locks it out with a growing delay.

	State lives in the database, so every process that checks a credential draws on the
	same budget: the bot, the web panel, and any number of panel workers cannot each hand
	out a fresh set of attempts. Counting is done in a single upsert so that simultaneous
	failures cannot overwrite each other.
	"""

	def __init__(
		self,
		name: str,
		threshold: int = 5,
		base_lock_seconds: int = 300,
		max_lock_seconds: int = 24 * 60 * 60,
		forget_after_seconds: int = 24 * 60 * 60,
	) -> None:
		self.name = name
		self.threshold = threshold
		self.base_lock_seconds = base_lock_seconds
		self.max_lock_seconds = max_lock_seconds
		self.forget_after_seconds = forget_after_seconds

	async def remaining_lockout(self, identifier: str) -> int:
		key = self.key_for(identifier)
		async with session_scope() as session:
			locked_until = await session.scalar(
				select(LoginAttempt.locked_until).where(
					LoginAttempt.guard == self.name, LoginAttempt.identifier == key
				)
			)
		if locked_until is None:
			return 0
		remaining = (as_utc(locked_until) - now()).total_seconds()
		return int(remaining) + 1 if remaining > 0 else 0

	async def register_failure(self, identifier: str) -> int:
		key = self.key_for(identifier)
		at = now()
		stale_before = at - datetime.timedelta(seconds=self.forget_after_seconds)

		async with session_scope() as session:
			# One statement, so two concurrent failures increment rather than clobber.
			# A row nobody has touched since forget_after_seconds restarts at 1.
			failures = await session.scalar(
				pg_insert(LoginAttempt)
				.values(guard=self.name, identifier=key, failures=1, last_failure_at=at)
				.on_conflict_do_update(
					index_elements=[LoginAttempt.guard, LoginAttempt.identifier],
					set_={
						"failures": case(
							(LoginAttempt.last_failure_at < stale_before, 1),
							else_=LoginAttempt.failures + 1,
						),
						"last_failure_at": at,
						"locked_until": case(
							(LoginAttempt.last_failure_at < stale_before, None),
							else_=LoginAttempt.locked_until,
						),
					},
				)
				.returning(LoginAttempt.failures)
			)

			if failures < self.threshold:
				return 0

			lock_seconds = self.lock_seconds_for(failures)
			await session.execute(
				update(LoginAttempt)
				.where(LoginAttempt.guard == self.name, LoginAttempt.identifier == key)
				.values(locked_until=at + datetime.timedelta(seconds=lock_seconds))
			)
			return lock_seconds

	async def reset(self, identifier: str) -> None:
		key = self.key_for(identifier)
		async with session_scope() as session:
			await session.execute(
				delete(LoginAttempt).where(
					LoginAttempt.guard == self.name, LoginAttempt.identifier == key
				)
			)

	def lock_seconds_for(self, failures: int) -> int:
		steps = max(0, min(failures - self.threshold, MAX_BACKOFF_STEPS))
		return min(self.base_lock_seconds * (2**steps), self.max_lock_seconds)

	def key_for(self, identifier: str) -> str:
		return identifier.strip().lower()[:MAX_IDENTIFIER_CHARS]


async def forget_stale_attempts(forget_after_seconds: int = 24 * 60 * 60) -> int:
	"""Drop attempt rows that are neither locked nor recent, so the table stays small."""
	at = now()
	stale_before = at - datetime.timedelta(seconds=forget_after_seconds)
	async with session_scope() as session:
		result = await session.execute(
			delete(LoginAttempt).where(
				LoginAttempt.last_failure_at < stale_before,
				(LoginAttempt.locked_until.is_(None)) | (LoginAttempt.locked_until < at),
			)
		)
	return result.rowcount or 0


def describe_wait(seconds: int) -> str:
	if seconds < 90:
		return f"{seconds} seconds"
	minutes = round(seconds / 60)
	if minutes < 90:
		return f"{minutes} minutes"
	return f"{round(minutes / 60)} hours"
