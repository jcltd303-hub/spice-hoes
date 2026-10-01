"""Provider adapters for the allowed compute lanes: Azure text and local-dream media."""

from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.request


class ProviderError(RuntimeError):
    pass


def _post_json(url: str, payload: dict, headers: dict[str, str], timeout: int = 90) -> dict:
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", **headers},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError) as exc:
        raise ProviderError(str(exc)) from exc


class AzureChatProvider:
    """OpenAI-compatible Azure chat adapter using only stdlib HTTP."""

    def __init__(self, endpoint: str | None = None, api_key: str | None = None,
                 deployment: str | None = None, api_version: str | None = None):
        self.endpoint = (endpoint or os.getenv("AZURE_OPENAI_ENDPOINT", "")).rstrip("/")
        self.api_key = api_key or os.getenv("AZURE_OPENAI_API_KEY", "")
        self.deployment = deployment or os.getenv("AZURE_OPENAI_DEPLOYMENT", "")
        self.api_version = api_version or os.getenv("AZURE_OPENAI_API_VERSION", "2025-04-01-preview")
        if not all((self.endpoint, self.api_key, self.deployment)):
            raise ProviderError("Azure provider requires endpoint, API key and deployment")

    @property
    def model_name(self) -> str:
        return f"azure:{self.deployment}"

    def chat(self, system: str, user: str, temperature: float = 0.4) -> str:
        url = (f"{self.endpoint}/openai/deployments/{self.deployment}/chat/completions"
               f"?api-version={self.api_version}")
        data = _post_json(url, {
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": user}],
            "temperature": temperature,
        }, {"api-key": self.api_key})
        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderError("Unexpected Azure response") from exc


class LocalDreamProvider:
    """Thin adapter for a local-dream HTTP endpoint reachable from the operator device."""

    def __init__(self, base_url: str | None = None, token: str | None = None):
        self.base_url = (base_url or os.getenv("LOCAL_DREAM_URL", "http://127.0.0.1:7860")).rstrip("/")
        self.token = token or os.getenv("LOCAL_DREAM_TOKEN", "")

    @property
    def model_name(self) -> str:
        return "local-dream:s24"

    def generate_image(self, prompt: str, negative_prompt: str = "", seed: int | None = None,
                       width: int = 768, height: int = 1024) -> dict:
        headers = {"Authorization": f"Bearer {self.token}"} if self.token else {}
        payload = {
            "prompt": prompt, "negative_prompt": negative_prompt,
            "width": width, "height": height,
        }
        if seed is not None:
            payload["seed"] = seed
        data = _post_json(f"{self.base_url}/generate", payload, headers, timeout=180)
        image_b64 = data.get("image_base64")
        if image_b64:
            # Validate returned base64 now; callers can persist it to private storage.
            base64.b64decode(image_b64, validate=True)
        return data
