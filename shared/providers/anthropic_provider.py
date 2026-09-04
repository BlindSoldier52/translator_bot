import httpx
from anthropic import APIStatusError, AsyncAnthropic, AuthenticationError, PermissionDeniedError

from shared.providers.base import (
	ProviderAdapter,
	ProviderAuthError,
	ProviderError,
	TruncatedReplyError,
)

MODEL = "claude-haiku-4-5-20251001"

CONNECT_TIMEOUT_SECONDS = 10.0
BASE_TIMEOUT_SECONDS = 20.0
SECONDS_PER_OUTPUT_TOKEN = 0.02
MAX_TIMEOUT_SECONDS = 120.0
MAX_RETRIES = 2


def request_timeout(max_tokens: int) -> httpx.Timeout:
	total = min(MAX_TIMEOUT_SECONDS, BASE_TIMEOUT_SECONDS + SECONDS_PER_OUTPUT_TOKEN * max_tokens)
	return httpx.Timeout(total, connect=CONNECT_TIMEOUT_SECONDS)


class AnthropicProvider(ProviderAdapter):
	code = "anthropic"
	label = "Anthropic (Claude)"
	max_output_tokens = 8192

	async def complete(self, api_key: str, system: str, user_text: str, max_tokens: int) -> str:
		client = AsyncAnthropic(
			api_key=api_key,
			timeout=request_timeout(max_tokens),
			max_retries=MAX_RETRIES,
		)
		try:
			async with client:
				response = await client.messages.create(
					model=MODEL,
					max_tokens=max_tokens,
					system=system,
					messages=[{"role": "user", "content": user_text}],
				)
		except (AuthenticationError, PermissionDeniedError) as exc:
			raise ProviderAuthError(f"{self.label} rejected that API key") from exc
		except APIStatusError as exc:
			raise ProviderError(f"{self.label} request failed") from exc
		except Exception as exc:
			raise ProviderError(f"{self.label} request failed") from exc

		parts = [block.text for block in response.content if block.type == "text"]
		if response.stop_reason == "max_tokens":
			raise TruncatedReplyError(f"{self.label} ran out of room before finishing the reply")
		return "".join(parts).strip()
