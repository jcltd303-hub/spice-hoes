"""Auditable hybrid lexical + semantic RAG over approved project knowledge."""

from __future__ import annotations

import json
import math
import re
import uuid
from datetime import datetime, timezone


_TOKEN = re.compile(r"[a-z0-9][a-z0-9_-]{1,}")


def _tokens(text: str) -> set[str]:
    return set(_TOKEN.findall(text.lower()))


def _cosine(a: list[float], b: list[float]) -> float:
    if len(a) != len(b) or not a:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


class KnowledgeBase:
    def __init__(self, store, embedder=None, *, verified_experiments_only: bool = False):
        self.store = store
        self.embedder = embedder
        self.verified_experiments_only = verified_experiments_only
        self.store.db.executescript(
            """
            CREATE TABLE IF NOT EXISTS knowledge (
                id TEXT PRIMARY KEY,
                ts TEXT NOT NULL,
                source TEXT NOT NULL,
                title TEXT NOT NULL,
                body TEXT NOT NULL,
                tags TEXT NOT NULL,
                approved INTEGER NOT NULL DEFAULT 1,
                embedding_json TEXT,
                embedding_model TEXT
            );
            """
        )
        self._ensure_embedding_columns()
        self.store.db.commit()

    def _ensure_embedding_columns(self):
        cols = {
            row["name"] for row in self.store.db.execute("PRAGMA table_info(knowledge)")
        }
        if "embedding_json" not in cols:
            self.store.db.execute("ALTER TABLE knowledge ADD COLUMN embedding_json TEXT")
        if "embedding_model" not in cols:
            self.store.db.execute("ALTER TABLE knowledge ADD COLUMN embedding_model TEXT")

    def _embed_text(self, title: str, body: str, tags: list[str]) -> tuple[list[float] | None, str | None]:
        if self.embedder is None:
            return None, None
        vector = self.embedder.embed(
            f"{title}\n\n{body}\n\nTags: {', '.join(tags)}"
        )
        if not isinstance(vector, list) or not vector:
            raise ValueError("embedding provider returned no vector")
        values = [float(x) for x in vector]
        model = getattr(self.embedder, "model_name", self.embedder.__class__.__name__)
        return values, str(model)

    def add(self, source: str, title: str, body: str, tags: list[str] | None = None,
            approved: bool = True) -> dict:
        if not source.strip() or not title.strip() or not body.strip():
            raise ValueError("source, title and body are required")
        clean_tags = sorted(set(tags or []))
        vector, embedding_model = self._embed_text(title.strip(), body.strip(), clean_tags)
        item = {
            "id": str(uuid.uuid4()),
            "ts": datetime.now(timezone.utc).isoformat(),
            "source": source.strip(),
            "title": title.strip(),
            "body": body.strip(),
            "tags": clean_tags,
            "approved": bool(approved),
            "embedding_model": embedding_model,
        }
        with self.store.db:
            self.store.db.execute(
                """INSERT INTO knowledge
                   (id,ts,source,title,body,tags,approved,embedding_json,embedding_model)
                   VALUES(?,?,?,?,?,?,?,?,?)""",
                (
                    item["id"], item["ts"], item["source"], item["title"], item["body"],
                    json.dumps(item["tags"]), 1 if item["approved"] else 0,
                    json.dumps(vector) if vector is not None else None,
                    embedding_model,
                ),
            )
            self.store._event("knowledge_added", {
                "knowledge_id": item["id"],
                "source": item["source"],
                "title": item["title"],
                "tags": item["tags"],
                "approved": item["approved"],
                "embedding_model": embedding_model,
            })
        return item

    def backfill_embeddings(self, limit: int | None = None) -> dict:
        if self.embedder is None:
            return {"embedded": 0, "reason": "no_embedder"}
        sql = "SELECT * FROM knowledge WHERE embedding_json IS NULL ORDER BY ts,id"
        params = ()
        if limit is not None:
            if limit < 1:
                raise ValueError("limit must be positive")
            sql += " LIMIT ?"
            params = (limit,)
        rows = self.store.db.execute(sql, params).fetchall()
        updated = 0
        with self.store.db:
            for row in rows:
                tags = json.loads(row["tags"])
                vector, model = self._embed_text(row["title"], row["body"], tags)
                self.store.db.execute(
                    "UPDATE knowledge SET embedding_json=?,embedding_model=? WHERE id=?",
                    (json.dumps(vector), model, row["id"]),
                )
                updated += 1
            if updated:
                self.store._event("knowledge_embeddings_backfilled", {
                    "embedded": updated,
                    "embedding_model": getattr(
                        self.embedder, "model_name", self.embedder.__class__.__name__
                    ),
                })
        return {"embedded": updated}

    @staticmethod
    def _lexical_score(query_tokens: set[str], row) -> float:
        title_tokens = _tokens(row["title"])
        body_tokens = _tokens(row["body"])
        tag_tokens = _tokens(" ".join(json.loads(row["tags"])))
        return (
            len(query_tokens & body_tokens)
            + 2 * len(query_tokens & title_tokens)
            + 1.5 * len(query_tokens & tag_tokens)
        )

    def search(self, query: str, limit: int = 6, approved_only: bool = True) -> list[dict]:
        query_tokens = _tokens(query)
        if not query_tokens and self.embedder is None:
            return []

        query_vector = None
        if self.embedder is not None and query.strip():
            query_vector = [float(x) for x in self.embedder.embed(query)]

        sql = "SELECT * FROM knowledge"
        if approved_only:
            sql += " WHERE approved=1"
        rows = self.store.db.execute(sql).fetchall()

        scored = []
        for row in rows:
            if self.verified_experiments_only and row["source"].startswith("experiment:"):
                try:
                    summary = json.loads(row["body"])
                except (ValueError, TypeError):
                    continue
                if not isinstance(summary, dict) or summary.get("verified_revenue_only") is not True:
                    continue
                tables = {r[0] for r in self.store.db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
                if not {"learning_closure", "rl_verified_experience"}.issubset(tables):
                    continue
                if self.store.db.execute(
                    """SELECT 1 FROM learning_closure c JOIN rl_verified_experience v
                       ON v.experience_id=c.experience_id WHERE c.knowledge_id=? AND c.plan_id=?""",
                    (row["id"], row["source"][len("experiment:"):]),
                ).fetchone() is None:
                    continue
            lexical = self._lexical_score(query_tokens, row)
            semantic = 0.0
            if query_vector is not None and row["embedding_json"]:
                semantic = _cosine(query_vector, json.loads(row["embedding_json"]))

            if query_vector is None:
                score = lexical
                method = "lexical"
            else:
                lexical_norm = lexical / (lexical + 4.0) if lexical > 0 else 0.0
                semantic_norm = max(0.0, min(1.0, (semantic + 1.0) / 2.0))
                score = 0.4 * lexical_norm + 0.6 * semantic_norm
                method = "hybrid"

            if score > 0:
                scored.append((score, lexical, semantic, method, row))

        scored.sort(key=lambda x: (-x[0], x[4]["ts"], x[4]["id"]))
        result = []
        for score, lexical, semantic, method, row in scored[:max(1, limit)]:
            result.append({
                "id": row["id"],
                "source": row["source"],
                "title": row["title"],
                "body": row["body"],
                "tags": json.loads(row["tags"]),
                "score": round(float(score), 6),
                "lexical_score": round(float(lexical), 6),
                "semantic_score": round(float(semantic), 6),
                "retrieval_method": method,
                "embedding_model": row["embedding_model"],
            })
        return result

    def context(self, query: str, limit: int = 6, max_chars: int = 8000) -> tuple[str, list[dict]]:
        hits = self.search(query, limit=limit)
        parts, used, remaining = [], [], max_chars
        for hit in hits:
            block = f"[{hit['id']}] {hit['title']}\nSource: {hit['source']}\n{hit['body']}"
            if len(block) > remaining:
                block = block[:remaining]
            if not block:
                break
            parts.append(block)
            used.append({
                k: hit[k]
                for k in (
                    "id", "source", "title", "score",
                    "retrieval_method", "embedding_model"
                )
            })
            remaining -= len(block)
            if remaining <= 0:
                break
        return "\n\n".join(parts), used
