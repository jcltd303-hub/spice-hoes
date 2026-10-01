import unittest
from unittest.mock import patch

from spicecore.providers import (
    OpenAICompatibleChatProvider,
    OpenAICompatibleEmbeddingProvider,
    ProviderError,
)


class ProviderTests(unittest.TestCase):
    def test_chat_provider_uses_openai_compatible_contract(self):
        provider = OpenAICompatibleChatProvider(
            base_url="https://openrouter.ai/api/v1",
            api_key="key",
            model="openrouter/free",
        )
        with patch("spicecore.providers._post_json") as post:
            post.return_value = {
                "choices": [{"message": {"content": "OK"}}],
            }
            result = provider.chat("system", "hello")

        self.assertEqual(result, "OK")
        url, payload, headers = post.call_args.args[:3]
        self.assertEqual(url, "https://openrouter.ai/api/v1/chat/completions")
        self.assertEqual(payload["model"], "openrouter/free")
        self.assertEqual(payload["messages"][1]["content"], "hello")
        self.assertEqual(headers["Authorization"], "Bearer key")

    def test_embedding_provider_uses_openai_compatible_contract(self):
        provider = OpenAICompatibleEmbeddingProvider(
            base_url="https://example.test/v1",
            api_key="key",
            model="embed-model",
        )
        with patch("spicecore.providers._post_json") as post:
            post.return_value = {
                "data": [{"embedding": [0.1, 0.2, 0.3]}],
            }
            vector = provider.embed("hello world")

        self.assertEqual(vector, [0.1, 0.2, 0.3])
        url, payload, headers = post.call_args.args[:3]
        self.assertEqual(url, "https://example.test/v1/embeddings")
        self.assertEqual(payload["model"], "embed-model")
        self.assertEqual(payload["input"], "hello world")
        self.assertEqual(headers["Authorization"], "Bearer key")

    def test_embedding_provider_requires_model(self):
        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaises(ProviderError):
                OpenAICompatibleEmbeddingProvider()


if __name__ == "__main__":
    unittest.main()
