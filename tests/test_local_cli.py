import contextlib
import io
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from spicecore.cli import main
from spicecore.local_compute import LocalChatProvider


class LocalCLIPlanningTests(unittest.TestCase):
    def test_campaign_and_responder_accept_keyless_local_model(self):
        for command in [
            ['campaign-moa', '--persona', 'zara_voss', '--goal', 'draft', '--cause', 'music', '--neighborhood', 'local'],
            ['auto-respond', '--persona', 'zara_voss', '--poll'],
        ]:
            with self.subTest(command=command[0]), tempfile.TemporaryDirectory() as root, \
                    patch.dict(os.environ, {'SPICE_TEXT_PROVIDER': 'local'}, clear=True), \
                    patch('spicecore.cli.engineer_campaign', return_value={'drafted': True}) as campaign, \
                    patch('spicecore.cli.AutoResponder') as responder, \
                    contextlib.redirect_stdout(io.StringIO()):
                responder.return_value.poll.return_value = []
                main(['--db', str(Path(root) / 'local.sqlite'), '--json', *command])
                if command[0] == 'campaign-moa':
                    self.assertIsInstance(campaign.call_args.args[1], LocalChatProvider)
                else:
                    responder.return_value.poll.assert_called_once()
