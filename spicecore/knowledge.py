"""Scoped, local knowledge retrieval. Retrieved text is data, never authorization."""
from __future__ import annotations

import hashlib
import json
import math
import re
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path


class KnowledgeStore:
    """Immutable source revisions with lexical retrieval and optional supplied embeddings.

    The embedder is an explicitly configured callable; this module performs no network
    inference or provider fallback. Callers must supply an authenticated scope.
    """
    def __init__(self, path: str | Path, *, embedder=None):
        self.embedder = embedder
        self.mode = 'hybrid' if embedder else 'lexical-only'
        self.db = sqlite3.connect(str(path))
        self.db.row_factory = sqlite3.Row
        self.db.execute('PRAGMA foreign_keys=ON')
        self.db.execute('PRAGMA secure_delete=ON')
        self.db.executescript('''
            CREATE TABLE IF NOT EXISTS knowledge_documents(id TEXT PRIMARY KEY, current_revision TEXT, archived INTEGER NOT NULL DEFAULT 0);
            CREATE TABLE IF NOT EXISTS knowledge_revisions(id TEXT PRIMARY KEY, document_id TEXT NOT NULL REFERENCES knowledge_documents(id) ON DELETE CASCADE, metadata TEXT NOT NULL, text TEXT NOT NULL, collected_at TEXT NOT NULL, content_hash TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS knowledge_chunks(id TEXT PRIMARY KEY, revision_id TEXT NOT NULL REFERENCES knowledge_revisions(id) ON DELETE CASCADE, heading TEXT NOT NULL, text TEXT NOT NULL);
            CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_fts USING fts5(chunk_id UNINDEXED, text);
            CREATE TABLE IF NOT EXISTS knowledge_vectors(chunk_id TEXT PRIMARY KEY REFERENCES knowledge_chunks(id) ON DELETE CASCADE, vector TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS knowledge_audit(id TEXT PRIMARY KEY, document_id TEXT NOT NULL, operation TEXT NOT NULL, ts TEXT NOT NULL);
        ''')
        self.db.commit()

    def close(self):
        self.db.close()

    @staticmethod
    def _validated(document):
        required = ('tenant', 'owner', 'rights', 'source', 'namespace', 'sensitivity', 'evidence_class', 'persona', 'expiry')
        if not isinstance(document, dict) or any(k not in document for k in required):
            raise ValueError('Missing required knowledge metadata')
        if any(not isinstance(document[k], str) or not document[k].strip() for k in required if k != 'expiry'):
            raise ValueError('Knowledge metadata must be nonempty strings')
        if document['sensitivity'] not in ('public', 'private', 'restricted'):
            raise ValueError('Invalid sensitivity')
        if document['evidence_class'] not in ('fictional canon', 'fictional_canon', 'observed', 'inferred', 'hypothesis'):
            raise ValueError('Invalid evidence class')
        if document['expiry'] is not None:
            KnowledgeStore._date(document['expiry'])
        text = document.get('text', document.get('content'))
        if isinstance(text, (dict, list)):
            text = json.dumps(text, sort_keys=True, ensure_ascii=False)
        if not isinstance(text, str) or not text.strip():
            raise ValueError('Document requires text or JSON content')
        metadata = {k: v for k, v in document.items() if k not in ('text', 'content')}
        return metadata, text

    @staticmethod
    def _date(value):
        try:
            date = datetime.fromisoformat(value.replace('Z', '+00:00'))
            if date.tzinfo is None:
                raise ValueError('Timezone required')
            return date
        except (AttributeError, TypeError, ValueError) as exc:
            raise ValueError('Expected timezone-aware ISO timestamp') from exc

    @staticmethod
    def _chunks(text):
        heading, lines = '', []
        def bounded():
            words = '\n'.join(lines).split()
            return [(heading, ' '.join(words[i:i + 512])) for i in range(0, len(words), 512)]
        result = []
        for line in text.splitlines():
            if re.match(r'^#{1,6}\s', line):
                result.extend(bounded())
                heading, lines = line.lstrip('#').strip(), [line]
            else:
                lines.append(line)
        result.extend(bounded())
        return result

    @staticmethod
    def _vector(value):
        if not isinstance(value, (list, tuple)) or not value:
            raise ValueError('Embedding must be a nonempty vector')
        vector = [float(v) for v in value]
        if not all(math.isfinite(v) for v in vector) or not any(vector):
            raise ValueError('Embedding must be finite and nonzero')
        return vector

    def _audit(self, did, operation):
        self.db.execute('INSERT INTO knowledge_audit VALUES(?,?,?,?)',
                        (str(uuid.uuid4()), did, operation, datetime.now(timezone.utc).isoformat()))

    def _revision(self, did, document):
        metadata, text = self._validated(document)
        chunks = self._chunks(text)
        vectors = [self._vector(self.embedder(t)) for _, t in chunks] if self.embedder else []
        rid = str(uuid.uuid4())
        self.db.execute('INSERT INTO knowledge_revisions VALUES(?,?,?,?,?,?)',
                        (rid, did, json.dumps(metadata), text, datetime.now(timezone.utc).isoformat(), hashlib.sha256(text.encode()).hexdigest()))
        for i, (heading, chunk) in enumerate(chunks):
            cid = str(uuid.uuid4())
            self.db.execute('INSERT INTO knowledge_chunks VALUES(?,?,?,?)', (cid, rid, heading, chunk))
            self.db.execute('INSERT INTO knowledge_fts VALUES(?,?)', (cid, chunk))
            if vectors:
                self.db.execute('INSERT INTO knowledge_vectors VALUES(?,?)', (cid, json.dumps(vectors[i])))
        self.db.execute('UPDATE knowledge_documents SET current_revision=?, archived=0 WHERE id=?', (rid, did))
        return rid

    def add(self, document: dict) -> str:
        did = str(uuid.uuid4())
        with self.db:
            self.db.execute('INSERT INTO knowledge_documents(id) VALUES(?)', (did,))
            self._revision(did, document)
            self._audit(did, 'add')
        return did

    def _existing(self, did):
        if self.db.execute('SELECT 1 FROM knowledge_documents WHERE id=?', (did,)).fetchone() is None:
            raise ValueError('Unknown document')

    def revise(self, document_id: str, document: dict) -> str:
        self._existing(document_id)
        with self.db:
            rid = self._revision(document_id, document)
            self._audit(document_id, 'revise')
        return rid

    def archive(self, document_id: str) -> None:
        self._existing(document_id)
        with self.db:
            self.db.execute('UPDATE knowledge_documents SET archived=1 WHERE id=?', (document_id,))
            self._audit(document_id, 'archive')

    def delete(self, document_id: str) -> None:
        self._existing(document_id)
        with self.db:
            self.db.execute('DELETE FROM knowledge_fts WHERE chunk_id IN (SELECT c.id FROM knowledge_chunks c JOIN knowledge_revisions r ON r.id=c.revision_id WHERE r.document_id=?)', (document_id,))
            self.db.execute('DELETE FROM knowledge_documents WHERE id=?', (document_id,))
            self._audit(document_id, 'delete')
            # Purge deleted text from FTS segment history as well as live search rows.
            self.db.execute("INSERT INTO knowledge_fts(knowledge_fts) VALUES('rebuild')")

    def search(self, query: str, scope: dict, limit: int = 8) -> list[dict]:
        if not isinstance(limit, int) or limit < 1:
            raise ValueError('Limit must be positive')
        if not all(scope.get(k) for k in ('tenant', 'persona', 'owner')):
            return []
        now = datetime.now(timezone.utc)
        # Construct the permitted candidate set before lexical/vector scoring.
        candidates = []
        rows = self.db.execute('''SELECT d.id document_id, r.id revision_id, r.metadata, r.content_hash, c.id chunk_id, c.heading, c.text
            FROM knowledge_documents d JOIN knowledge_revisions r ON r.id=d.current_revision
            JOIN knowledge_chunks c ON c.revision_id=r.id WHERE d.archived=0''')
        for row in rows:
            m = json.loads(row['metadata'])
            if m['tenant'] != scope['tenant'] or m['persona'] != scope['persona']:
                continue
            private = m['sensitivity'] != 'public' or m['namespace'] in ('private_conversation_memory', 'private conversation memory')
            if private and m['owner'] != scope['owner']:
                continue
            if scope.get('namespaces') is not None and m['namespace'] not in scope['namespaces']:
                continue
            if m['expiry'] is not None and self._date(m['expiry']) <= now:
                continue
            candidates.append((dict(row), m))
        terms = re.findall(r'\w+', query, re.UNICODE)
        match = ' OR '.join('"' + term + '"' for term in terms)
        qvector = self._vector(self.embedder(query)) if self.embedder and candidates else None
        results = []
        for row, metadata in candidates:
            lexical = self.db.execute('SELECT count(*) FROM knowledge_fts WHERE chunk_id=? AND knowledge_fts MATCH ?', (row['chunk_id'], match)).fetchone()[0] if match else 0
            if lexical:
                words = re.findall(r'\w+', row['text'].lower())
                lexical = sum(words.count(term.lower()) for term in terms) / max(1, len(words))
            vector_score = None
            if qvector:
                stored = self.db.execute('SELECT vector FROM knowledge_vectors WHERE chunk_id=?', (row['chunk_id'],)).fetchone()
                if stored:
                    vector = json.loads(stored[0])
                    if len(vector) != len(qvector):
                        raise ValueError('Embedding dimension mismatch')
                    vector_score = sum(a*b for a,b in zip(vector, qvector)) / (math.sqrt(sum(a*a for a in vector))*math.sqrt(sum(a*a for a in qvector)))
            if not lexical and vector_score is None:
                continue
            row.pop('metadata')
            row.update(metadata=metadata, score=lexical + (vector_score or 0), mode=self.mode,
                       citation_id=f"{row['document_id']}:{row['revision_id']}:{row['chunk_id']}", untrusted=True)
            results.append(row)
        return sorted(results, key=lambda r: (-r['score'], r['chunk_id']))[:limit]
