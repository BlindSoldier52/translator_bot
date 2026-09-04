import logging

from sqlalchemy import select
from starlette.requests import Request
from starlette.responses import RedirectResponse

from shared.config import is_trusted_proxy
from shared.db import session_scope
from shared.lockout import LoginGuard, describe_wait
from shared.models import AdminUser
from shared.security import verify_password_async

logger = logging.getLogger(__name__)

SESSION_KEY = "admin_id"

login_guard = LoginGuard("panel-admin", threshold=5)
address_guard = LoginGuard("panel-address", threshold=10)


class LoginOutcome:
	def __init__(self, admin: AdminUser | None = None, locked_for: int = 0) -> None:
		self.admin = admin
		self.locked_for = locked_for

	def is_locked(self) -> bool:
		return self.locked_for > 0

	def lock_message(self) -> str:
		return (
			f"Too many failed sign-ins. Try again in {describe_wait(self.locked_for)}."
		)


def client_address(request: Request) -> str:
	"""The caller's address, trusting X-Forwarded-For only from a configured proxy.

	Without that check anyone reaching the app directly could send a fresh header on
	every attempt and never fill up a lockout bucket. The last entry is the one our
	own proxy appended; everything before it came from the caller.
	"""
	peer = request.client.host if request.client else None
	if peer is None:
		return "unknown"
	if not is_trusted_proxy(peer):
		return peer

	forwarded = request.headers.get("x-forwarded-for", "")
	if forwarded:
		return forwarded.split(",")[-1].strip() or peer
	return peer


async def verify_admin_login(request: Request, username: str, password: str) -> LoginOutcome:
	address = client_address(request)
	locked = await login_guard.remaining_lockout(username)
	if not locked:
		locked = await address_guard.remaining_lockout(address)
	if locked:
		logger.warning("Rejected a login for %r from %s while locked out", username, address)
		return LoginOutcome(locked_for=locked)

	async with session_scope() as session:
		admin = await session.scalar(select(AdminUser).where(AdminUser.username == username))
		stored_hash = admin.password_hash if admin is not None else None
		password_ok = await verify_password_async(stored_hash, password)
		if password_ok:
			session.expunge(admin)

	if not password_ok:
		admin_lock = await login_guard.register_failure(username)
		address_lock = await address_guard.register_failure(address)
		logger.warning("Failed panel login for %r from %s", username, address)
		return LoginOutcome(locked_for=max(admin_lock, address_lock))

	await login_guard.reset(username)
	await address_guard.reset(address)
	logger.info("Panel login for %r from %s", username, address)
	return LoginOutcome(admin=admin)


async def get_current_admin(request: Request) -> AdminUser | None:
	admin_id = request.session.get(SESSION_KEY)
	if admin_id is None:
		return None
	async with session_scope() as session:
		admin = await session.get(AdminUser, admin_id)
		if admin is not None:
			session.expunge(admin)
		return admin


def require_admin_or_redirect(admin: AdminUser | None) -> RedirectResponse | None:
	if admin is None:
		return RedirectResponse("/login", status_code=303)
	return None
