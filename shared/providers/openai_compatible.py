import asyncio
import logging

import httpx

from shared.providers.base import (
	ProviderAdapter,
	ProviderAuthError,
	ProviderError,
	TruncatedReplyError,
)

logger = logging.getLogger(__name__)

CONNECT_TIMEOUT_SECONDS = 10.0
BASE_READ_TIMEOUT_SECONDS = 20.0
SECONDS_PER_OUTPUT_TOKEN = 0.02
MAX_READ_TIMEOUT_SECONDS = 120.0

MAX_ATTEMPTS = 3
RETRY_BACKOFF_SECONDS = 1.0
RETRYABLE_STATUS = frozenset({408, 409, 425, 429, 500, 502, 503, 504})
AUTH_STATUS = frozenset({401, 403})


def read_timeout(max_tokens: int) -> float:
	return min(
		MAX_READ_TIMEOUT_SECONDS, BASE_READ_TIMEOUT_SECONDS + SECONDS_PER_OUTPUT_TOKEN * max_tokens
	)


class OpenAICompatibleProvider(ProviderAdapter):
	base_url: str
	model: str

	async def complete(self, api_key: str, system: str, user_text: str, max_tokens: int) -> str:
		headers = {"Authorization": f"Bearer {api_key}"}
		payload = {
			"model": self.model,
			"messages": [
				{"role": "system", "content": system},
				{"role": "user", "content": user_text},
			],
			"max_tokens": max_tokens,
		}
		timeout = httpx.Timeout(read_timeout(max_tokens), connect=CONNECT_TIMEOUT_SECONDS)
		response = await self.post_with_retries(headers, payload, timeout)

		try:
			data = response.json()
		except ValueError as exc:
			raise ProviderError(f"{self.label} returned an unexpected response") from exc

		try:
			choice = data["choices"][0]
			content = choice["message"]["content"].strip()
		except (KeyError, IndexError, TypeError, AttributeError) as exc:
			raise ProviderError(f"{self.label} returned an unexpected response") from exc

		if choice.get("finish_reason") == "length":
			raise TruncatedReplyError(f"{self.label} ran out of room before finishing the reply")
		return content

	async def post_with_retries(self, headers: dict, payload: dict, timeout: httpx.Timeout):
		last_error: Exception | None = None
		for attempt in range(1, MAX_ATTEMPTS + 1):
			try:
				async with httpx.AsyncClient(timeout=timeout) as client:
					response = await client.post(
						f"{self.base_url}/chat/completions", headers=headers, json=payload
					)
			except httpx.HTTPError as exc:
				last_error = exc
			else:
				if response.status_code in AUTH_STATUS:
					raise ProviderAuthError(f"{self.label} rejected that API key")
				if response.status_code not in RETRYABLE_STATUS:
					try:
						response.raise_for_status()
					except httpx.HTTPStatusError as exc:
						raise ProviderError(f"{self.label} request failed") from exc
					return response
				last_error = httpx.HTTPStatusError(
					f"status {response.status_code}", request=response.request, response=response
				)

			if attempt < MAX_ATTEMPTS:
				logger.info("%s call failed (attempt %d), retrying", self.label, attempt)
				await asyncio.sleep(RETRY_BACKOFF_SECONDS * attempt)

		raise ProviderError(f"{self.label} request failed") from last_error


class OpenAIProvider(OpenAICompatibleProvider):
	code = "openai"
	label = "OpenAI"
	base_url = "https://api.openai.com/v1"
	model = "gpt-4o-mini"


class OpenRouterProvider(OpenAICompatibleProvider):
	code = "openrouter"
	label = "OpenRouter"
	base_url = "https://openrouter.ai/api/v1"
	model = "openai/gpt-4o-mini"


class XAIProvider(OpenAICompatibleProvider):
	code = "xai"
	label = "xAI (Grok)"
	base_url = "https://api.x.ai/v1"
	model = "grok-2-latest"


class DeepSeekProvider(OpenAICompatibleProvider):
	code = "deepseek"
	label = "DeepSeek"
	base_url = "https://api.deepseek.com/v1"
	model = "deepseek-chat"


class GLMProvider(OpenAICompatibleProvider):
	code = "glm"
	label = "GLM (Zhipu)"
	base_url = "https://open.bigmodel.cn/api/paas/v4"
	model = "glm-4-flash"
	max_output_tokens = 4095
