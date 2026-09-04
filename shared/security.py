import asyncio
import re
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError, InvalidHash

hasher = PasswordHasher()

USERNAME_MIN_LEN = 5
USERNAME_MAX_LEN = 20
PASSWORD_MIN_LEN = 16
PASSWORD_MAX_LEN = 128

USERNAME_RE = re.compile(r"^[A-Za-z0-9_.\-]+$")

DECOY_HASH = hasher.hash(secrets.token_urlsafe(32))


def hash_password(plain_password: str) -> str:
	return hasher.hash(plain_password)


def verify_password(stored_hash: str, plain_password: str) -> bool:
	if len(plain_password) > PASSWORD_MAX_LEN:
		return False
	try:
		return hasher.verify(stored_hash, plain_password)
	except (VerifyMismatchError, VerificationError, InvalidHash):
		return False


def burn_verification_time(plain_password: str) -> None:
	"""Spend the same time as a real check, so a missing account cannot be told apart."""
	verify_password(DECOY_HASH, plain_password)


async def verify_password_async(stored_hash: str | None, plain_password: str) -> bool:
	if stored_hash is None:
		await asyncio.to_thread(burn_verification_time, plain_password)
		return False
	return await asyncio.to_thread(verify_password, stored_hash, plain_password)


async def hash_password_async(plain_password: str) -> str:
	return await asyncio.to_thread(hash_password, plain_password)


def needs_rehash(stored_hash: str) -> bool:
	return hasher.check_needs_rehash(stored_hash)


def validate_username(username: str) -> str | None:
	if " " in username:
		return "Username must not contain spaces."
	if not (USERNAME_MIN_LEN <= len(username) <= USERNAME_MAX_LEN):
		return f"Username must be between {USERNAME_MIN_LEN} and {USERNAME_MAX_LEN} characters."
	if not USERNAME_RE.match(username):
		return "Username may only contain letters, numbers, dots, underscores and hyphens."
	return None


def validate_password(password: str) -> str | None:
	if " " in password:
		return "Password must not contain spaces."
	if len(password) < PASSWORD_MIN_LEN:
		return f"Password must be at least {PASSWORD_MIN_LEN} characters."
	if len(password) > PASSWORD_MAX_LEN:
		return f"Password must be at most {PASSWORD_MAX_LEN} characters."
	return None


def generate_random_secret(length: int = 48) -> str:
	return secrets.token_urlsafe(length)
