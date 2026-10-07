import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from spicecore.azure_moa import AzureChatProvider
from spicecore.core import Store
from spicecore.moa import MixtureOfAgents


class AzureMoATests(unittest.TestCase):
    def test_azure_endpoint_auth_and_deployment_without_router_extensions(self):
        provider = AzureChatProvider("https://launch.openai.azure.com", "test-key", "strategy")
        with patch("spicecore.providers._post_json") as request:
            request.return_value = {"choices": [{"message": {"content": "ok"}}]}
            provider.chat("s", "u", models=["openrouter/free"])
        url, body, headers = request.call_args.args[:3]
        self.assertEqual(url, "https://launch.openai.azure.com/openai/v1/chat/completions")
        self.assertEqual(headers["api-key"], "test-key")
        self.assertNotIn("X-Title", headers)
        self.assertNotIn("models", body)
        self.assertEqual(body["model"], "strategy")

    def test_wrong_host_and_missing_secret_fail_closed(self):
        with self.assertRaises(ValueError):
            AzureChatProvider("https://openrouter.ai/api/v1", "key", "model")
        with self.assertRaises(ValueError):
            AzureChatProvider("https://launch.openai.azure.com", "", "model")

    def test_moa_uses_azure_deployments_for_every_role(self):
        with tempfile.TemporaryDirectory() as root:
            store = Store(Path(root) / "moa.sqlite")
            provider = AzureChatProvider("https://launch.openai.azure.com", "key", "default-deployment")
            with patch.dict("os.environ", {"MOA_MODEL_REVENUE": "unrelated/router-model"}, clear=True), \
                    patch.object(provider, "chat_detailed") as call:
                call.return_value = {"content": json.dumps({"action": "test", "evidence": []}),
                                     "model": "default-deployment"}
                result = MixtureOfAgents(provider, store).deliberate("Make a measurable sales experiment")
            self.assertEqual(call.call_count, 5)
            self.assertTrue(all(c.kwargs["model"] == "default-deployment" for c in call.call_args_list))
            self.assertTrue(all(c.kwargs["models"] == [] for c in call.call_args_list))
            self.assertEqual(result["architecture"], "moa-v3-azure")
            store.close()
