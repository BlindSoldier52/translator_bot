import asyncio
import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select

from shared.db import session_scope
from shared.models import AdminUser
from shared.security import (
	PASSWORD_MIN_LEN,
	hash_password,
	validate_password,
	validate_username,
)


async def create_admin(username: str, password: str) -> None:
	async with session_scope() as session:
		existing = await session.scalar(select(AdminUser).where(AdminUser.username == username))
		if existing is not None:
			print(f"An admin user named '{username}' already exists.")
			return
		session.add(AdminUser(username=username, password_hash=hash_password(password)))
	print(f"Admin user '{username}' created successfully.")


def main() -> None:
	username = input("Choose an admin panel username: ").strip()
	error = validate_username(username)
	if error:
		print(error)
		sys.exit(1)

	password = getpass.getpass(f"Choose an admin panel password (at least {PASSWORD_MIN_LEN} characters, no spaces): ")
	error = validate_password(password)
	if error:
		print(error)
		sys.exit(1)

	confirm = getpass.getpass("Confirm password: ")
	if confirm != password:
		print("Passwords do not match.")
		sys.exit(1)

	asyncio.run(create_admin(username, password))


if __name__ == "__main__":
	main()
