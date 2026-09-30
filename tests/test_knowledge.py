import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from spicecore.knowledge import KnowledgeStore
from spicecore.cli import main


def document(text, **overrides):
    result = dict(text=text, owner='customer-a', tenant='tenant-a', rights='owned',
                  source='local:test', namespace='private_conversation_memory',
                  sensitivity='private', evidence_class='observed', persona='posh', expiry=None)
    result.update(overrides)
    return result


class KnowledgeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = KnowledgeStore(Path(self.tmp.name) / 'knowledge.sqlite')
        self.scope = dict(tenant='tenant-a', owner='customer-a', persona='posh')

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def test_scope_before_limit(self):
        self.store.add(document('diamond diamond diamond', owner='customer-b'))
        allowed = self.store.add(document('diamond available'))
        self.assertEqual([r['document_id'] for r in self.store.search('diamond', self.scope, 1)], [allowed])
        self.assertEqual(self.store.search('diamond', dict(self.scope, tenant='other')), [])
        self.assertEqual(self.store.search('diamond', dict(self.scope, owner='other')), [])

    def test_delete_removes_all_text(self):
        did = self.store.add(document('unique_secret_phrase'))
        self.store.revise(did, document('new unique_secret_phrase'))
        self.store.delete(did)
        for table in ('knowledge_revisions', 'knowledge_chunks', 'knowledge_fts', 'knowledge_vectors', 'knowledge_audit'):
            rows = self.store.db.execute('SELECT * FROM ' + table).fetchall()
            self.assertNotIn('unique_secret_phrase', str([tuple(r) for r in rows]))
        self.assertEqual(self.store.search('unique_secret_phrase', self.scope), [])

    def test_expiry_and_revision(self):
        did = self.store.add(document('# Offer\nold diamond'))
        rid = self.store.revise(did, document('# Offer\nnew ruby'))
        self.assertEqual(self.store.search('diamond', self.scope), [])
        result = self.store.search('ruby', self.scope)[0]
        self.assertEqual(result['revision_id'], rid)
        self.assertEqual(result['mode'], 'lexical-only')
        self.store.add(document('ruby expired', expiry='2000-01-01T00:00:00Z'))
        self.assertEqual(len(self.store.search('ruby', self.scope)), 1)
        self.store.archive(did)
        self.assertEqual(self.store.search('ruby', self.scope), [])

    def test_required_metadata_and_bounded_chunks(self):
        for key in ('owner', 'rights', 'source', 'namespace', 'sensitivity', 'evidence_class', 'persona', 'expiry', 'tenant'):
            item = document('test')
            del item[key]
            with self.assertRaises(ValueError):
                self.store.add(item)
        self.store.add(document('# Large\n' + 'ruby ' * 1200))
        rows = self.store.search('ruby', self.scope)
        self.assertEqual(len(rows), 3)
        self.assertTrue(all(len(r['text'].split()) <= 512 for r in rows))
        self.assertEqual(self.store.search('ruby', {}), [])

    def test_optional_vectors_remain_scoped(self):
        self.store.close()
        self.store = KnowledgeStore(Path(self.tmp.name) / 'vector.sqlite', embedder=lambda text: [1., 0.])
        self.store.add(document('hidden', owner='other'))
        allowed = self.store.add(document('visible'))
        results = self.store.search('unmatched', self.scope, 1)
        self.assertEqual(results[0]['document_id'], allowed)
        self.assertEqual(results[0]['mode'], 'hybrid')

    def test_cli_lifecycle_without_persona_files(self):
        source = Path(self.tmp.name) / 'source.json'
        source.write_text(json.dumps(document('ruby offer')))
        db = str(Path(self.tmp.name) / 'cli.sqlite')
        def run(*args):
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                main(['--db', db, '--personas', '/missing', 'knowledge', *args])
            return json.loads(out.getvalue())
        did = run('add', '--document', str(source))['document_id']
        results = run('search', 'ruby', '--scope', json.dumps(self.scope))
        self.assertEqual(results['mode'], 'lexical-only')
        self.assertEqual(results['results'][0]['document_id'], did)
        source.write_text(json.dumps(document('sapphire offer')))
        run('revise', did, '--document', str(source))
        self.assertEqual(run('search', 'ruby', '--scope', json.dumps(self.scope))['results'], [])
        run('archive', did)
        self.assertEqual(run('search', 'sapphire', '--scope', json.dumps(self.scope))['results'], [])
        run('delete', did)
