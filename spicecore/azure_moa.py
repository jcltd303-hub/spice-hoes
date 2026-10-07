"""Azure v1 chat deployment adapter; no third-party model routing."""

import os
from urllib.parse import urlsplit

from .providers import OpenAICompatibleChatProvider


class AzureChatProvider(OpenAICompatibleChatProvider):
    restrict_to_azure = True

    def __init__(self, endpoint=None, api_key=None, deployment=None):
        endpoint = (endpoint or os.getenv("AZURE_OPENAI_ENDPOINT", "")).rstrip("/")
        api_key = api_key if api_key is not None else os.getenv("AZURE_OPENAI_API_KEY", "")
        deployment = deployment or os.getenv("AZURE_MOA_DEPLOYMENT", "")
        parsed = urlsplit(endpoint)
        if (parsed.scheme != "https" or parsed.username or parsed.password or parsed.query
                or not parsed.hostname or not parsed.hostname.endswith(
                    (".openai.azure.com", ".services.ai.azure.com", ".cognitiveservices.azure.com"))):
            raise ValueError("AZURE_OPENAI_ENDPOINT must be an HTTPS Azure model resource")
        if not api_key or not deployment:
            raise ValueError("AZURE_OPENAI_API_KEY and AZURE_MOA_DEPLOYMENT are required")
        base = endpoint if endpoint.endswith("/openai/v1") else endpoint + "/openai/v1"
        super().__init__(base, api_key, deployment)

    def _headers(self):
        return {"api-key": self.api_key}

    def chat_detailed(self, system, user, **kwargs):
        kwargs.pop("models", None)
        kwargs.pop("reasoning_enabled", None)
        return super().chat_detailed(system, user, **kwargs)
