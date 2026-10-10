import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from spicecore.cli import main
from spicecore.control_plane import _asset_generator
from spicecore.core import Store
from spicecore.swarm import SwarmConfig
from spicecore.swarm_factory import production_blockers


ROOT = Path(__file__).resolve().parents[1]


class SwarmCLITests(unittest.TestCase):
    def test_status_is_machine_readable_and_reports_missing_credentials(self):
        with tempfile.TemporaryDirectory() as root, patch.dict(os.environ, {}, clear=True):
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                main(["--db", str(Path(root) / "ledger.sqlite"), "--personas", str(ROOT / "personas"),
                      "--json", "swarm-status"])
            status = json.loads(output.getvalue())
            self.assertIn("local_chat_unavailable", status["blockers"])
            self.assertIn("INSTAGRAM_ACCESS_TOKEN", status["blockers"])
            self.assertFalse(status["generation_enabled"])

    def test_single_tick_terminates_cleanly_without_live_credentials(self):
        with tempfile.TemporaryDirectory() as root, patch.dict(os.environ, {}, clear=True):
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                main(["--db", str(Path(root) / "ledger.sqlite"), "--personas", str(ROOT / "personas"),
                      "--json", "swarm-run", "--once"])
            report = json.loads(output.getvalue())
            self.assertEqual(report["generation"]["reason"], "generation_disabled")
            self.assertIn("budget", report)

    def test_operator_generation_uses_selected_native_media_provider(self):
        with tempfile.TemporaryDirectory() as root, \
                patch("spicecore.control_plane.media_provider") as provider:
            store = Store(Path(root) / "ledger.sqlite")
            generator = _asset_generator(store)
            self.assertIs(generator.provider, provider.return_value)
            provider.assert_called_once()
            store.close()

    def test_invalid_media_credentials_block_paid_generation(self):
        with tempfile.TemporaryDirectory() as root, patch.dict(os.environ, {
            "MOA_BASE_URL": "http://127.0.0.1:8083/v1", "MOA_MODEL": "strategy",
            "INSTAGRAM_ACCESS_TOKEN": "test-token", "STRIPE_WEBHOOK_SECRET": "whsec-test",
            "SPICE_MEDIA_BIN": sys.executable, "SPICE_QNN_MODEL_DIR": root,
            "SPICE_MEDIA_PUBLIC_BASE_URL": "invalid",
        }, clear=True):
            self.assertIn("valid_public_media_configuration", production_blockers(SwarmConfig()))
