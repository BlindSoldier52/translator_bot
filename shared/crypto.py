import base64
import logging
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from shared.config import get_settings

logger = logging.getLogger(__name__)


class DecryptionError(Exception):
	pass


@lru_cache
def encryption_secret() -> str:
	"""The secret stored API keys are encrypted with.

	Deliberately separate from SESSION_SECRET_KEY: that one signs session cookies and
	is meant to be rotated freely, while this one can never be rotated without making
	every stored API key unreadable.
	"""
	return get_settings().api_key_encryption_key


def derive_fernet_key(user_id: int) -> bytes:
	hkdf = HKDF(
		algorithm=hashes.SHA256(),
		length=32,
		salt=None,
		info=f"byok-api-key:{user_id}".encode(),
	)
	key_material = hkdf.derive(encryption_secret().encode())
	return base64.urlsafe_b64encode(key_material)


def encrypt_api_key(user_id: int, plain_key: str) -> str:
	fernet = Fernet(derive_fernet_key(user_id))
	return fernet.encrypt(plain_key.encode()).decode()


def decrypt_api_key(user_id: int, encrypted_key: str) -> str:
	fernet = Fernet(derive_fernet_key(user_id))
	try:
		return fernet.decrypt(encrypted_key.encode()).decode()
	except InvalidToken as exc:
		raise DecryptionError("Could not decrypt the stored API key.") from exc
