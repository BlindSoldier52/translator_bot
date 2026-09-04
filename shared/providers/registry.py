from shared.providers.anthropic_provider import AnthropicProvider
from shared.providers.base import ProviderAdapter
from shared.providers.openai_compatible import (
	DeepSeekProvider,
	GLMProvider,
	OpenAIProvider,
	OpenRouterProvider,
	XAIProvider,
)

PROVIDERS: dict[str, ProviderAdapter] = {
	provider.code: provider
	for provider in (
		AnthropicProvider(),
		OpenAIProvider(),
		OpenRouterProvider(),
		XAIProvider(),
		DeepSeekProvider(),
		GLMProvider(),
	)
}


def get_provider(code: str) -> ProviderAdapter | None:
	return PROVIDERS.get(code)
