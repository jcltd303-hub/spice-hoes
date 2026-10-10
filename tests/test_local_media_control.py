import tempfile
import unittest
from pathlib import Path

from spicecore.control_plane import dispatch
from spicecore.core import Store, load_personas


ROOT = Path(__file__).resolve().parents[1]


class LocalMediaControlTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = Store(Path(self.temp.name) / 'ledger.sqlite')
        self.addCleanup(self.store.close)
        self.personas = load_personas(ROOT / 'personas')
        self.persona = self.personas[0]
        self.cid = self.store.propose(self.persona, 'test', 'still', 'test', 'offer', asset_uri='approved.png')

    def test_unapproved_still_cannot_enter_notebook_media_export(self):
        with self.assertRaisesRegex(ValueError, 'approved'):
            dispatch('media_create', {'candidate_id': self.cid, 'persona_id': self.persona['id'],
                                     'script': 'Hello'}, self.store, self.personas)

    def test_media_cannot_substitute_unreviewed_source(self):
        self.store.review(self.cid, 'approved', 'owner')
        with self.assertRaisesRegex(ValueError, 'source'):
            dispatch('media_create', {'candidate_id': self.cid, 'persona_id': self.persona['id'],
                                     'source_asset_uri': 'unapproved.png', 'script': 'Hello'}, self.store, self.personas)

    def test_media_uses_approved_candidate_source(self):
        self.store.review(self.cid, 'approved', 'owner')
        result = dispatch('media_create', {'candidate_id': self.cid, 'persona_id': self.persona['id'],
                                         'script': 'Hello'}, self.store, self.personas)
        self.assertEqual(result['source_asset_uri'], 'approved.png')
