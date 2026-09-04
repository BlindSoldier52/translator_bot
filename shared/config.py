import os
from functools import lru_cache
from ipaddress import ip_address, ip_network

from pydantic import model_validator
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

	# Telegram's cloud Bot API refuses to hand a bot any file over 20 MB. Running
	# your own telegram-bot-api server raises that to 2000 MB; point these at it
	# and set the ceiling to match.
	telegram_api_base_url: str = "https://api.telegram.org/bot"
	telegram_api_base_file_url: str = "https://api.telegram.org/file/bot"
	telegram_local_mode: bool = False
	max_file_size_mb: int = 20

	# How much of a file the bot will actually translate, independent of how big
	# the file is. Batches are the real cost control: one batch is one API call.
	max_extracted_chars: int = 400_000
	max_batches_per_file: int = 60
	max_batches_per_image: int = 20

	default_daily_message_limit: int = 500

	log_level: str = "INFO"

	@model_validator(mode="after")
	def check_file_size_against_api(self):
		"""Refuse a ceiling the configured Bot API cannot serve.

		Left unchecked it would not fail here but halfway through a download, as an
		unexplained Telegram error the user reads as "couldn't fetch that file".
		"""
		if self.max_file_size_mb < 1:
			raise ValueError("MAX_FILE_SIZE_MB must be at least 1")

		on_cloud = self.telegram_api_base_url.startswith("https://api.telegram.org/")
		if on_cloud and self.max_file_size_mb > 20:
			raise ValueError(
				f"MAX_FILE_SIZE_MB is {self.max_file_size_mb}, but Telegram's cloud Bot API "
				"never serves a bot a file over 20 MB. Run your own telegram-bot-api server "
				"and point TELEGRAM_API_BASE_URL and TELEGRAM_API_BASE_FILE_URL at it."
			)
		if self.max_file_size_mb > 2000:
			raise ValueError(
				f"MAX_FILE_SIZE_MB is {self.max_file_size_mb}, above the 2000 MB ceiling the "
				"Bot API supports at all."
			)
		return self


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
