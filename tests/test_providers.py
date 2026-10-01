import unittest
from unittest.mock import patch

from spicecore.providers import AzureEmbeddingProvider, ProviderError


class ProviderTests(unittest.TestCase):
    def test_azure_embedding_provider_uses_v1_embeddings_contract(self):
        provider = AzureEmbeddingProvider(
            endpoint="https://example.openai.azure.com",
            api_key="key",
            deployment="embed-deployment",
        )
        with patch("spicecore.providers._post_json") as post:
            post.return_value = {
                "data": [{"embedding": [0.1, 0.2, 0.3]}],
                "model": "embed-deployment",
            }
            vector = provider.embed("hello world")

        self.assertEqual(vector, [0.1, 0.2, 0.3])
        url, payload, headers = post.call_args.args[:3]
        self.assertEqual(
            url,
            "https://example.openai.azure.com/openai/v1/embeddings",
        )
        self.assertEqual(payload["model"], "embed-deployment")
        self.assertEqual(payload["input"], "hello world")
        self.assertEqual(headers["api-key"], "key")

    def test_embedding_provider_requires_configuration(self):
        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaises(ProviderError):
                AzureEmbeddingProvider()


if __name__ == "__main__":
    unittest.main()
