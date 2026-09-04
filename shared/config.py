import os
from functools import lru_cache
from ipaddress import ip_address, ip_network

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
	model_config = SettingsConfigDict(extra="ignore")

	env: str = "production"

	telegram_bot_token: str

	database_url: str

	session_secret_key: str

	api_key_encryption_key: str

	panel_host: str = "127.0.0.1"
	panel_port: int = 8000

	# Host header values the panel will answer to. "*" disables the check.
	panel_allowed_hosts: str = "*"

	# Only these peers may set X-Forwarded-For. Anything else is treated as the
	# client itself, so a direct caller cannot forge its own address.
	trusted_proxies: str = "127.0.0.1,::1"

	# Where this version's source can be fetched. The AGPL requires every operator
	# of a modified version to offer its source to the people using it, so a fork
	# must point this at the fork.
	source_url: str = "https://github.com/BlindSoldier52/translator_bot"

	default_daily_message_limit: int = 500

	log_level: str = "INFO"


def load_dotenv_if_dev() -> None:
	if os.environ.get("ENV", "production") != "development":
		return
	from dotenv import load_dotenv

	load_dotenv()


@lru_cache
def get_settings() -> Settings:
	load_dotenv_if_dev()
	return Settings()


@lru_cache
def trusted_proxy_networks() -> tuple:
	networks = []
	for entry in get_settings().trusted_proxies.split(","):
		entry = entry.strip()
		if entry:
			networks.append(ip_network(entry, strict=False))
	return tuple(networks)


def is_trusted_proxy(address: str) -> bool:
	try:
		parsed = ip_address(address)
	except ValueError:
		return False
	mapped = getattr(parsed, "ipv4_mapped", None)
	if mapped is not None:
		parsed = mapped
	return any(parsed in network for network in trusted_proxy_networks())
