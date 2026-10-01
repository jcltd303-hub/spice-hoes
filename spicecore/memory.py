"""Small auditable RAG memory over approved project knowledge.

This intentionally starts with deterministic lexical retrieval so every retrieved
chunk can be inspected. An embedding adapter can replace scoring later without
changing the storage contract.
"""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone


_TOKEN = re.compile(r"[a-z0-9][a-z0-9_-]{1,}")


def _tokens(text: str) -> set[str]:
    return set(_TOKEN.findall(text.lower()))


class KnowledgeBase:
    def __init__(self, store):
        self.store = store
        self.store.db.executescript(
            """
            CREATE TABLE IF NOT EXISTS knowledge (
                id TEXT PRIMARY KEY,
                ts TEXT NOT NULL,
                source TEXT NOT NULL,
                title TEXT NOT NULL,
                body TEXT NOT NULL,
                tags TEXT NOT NULL,
                approved INTEGER NOT NULL DEFAULT 1
            );
            """
        )
        self.store.db.commit()

    def add(self, source: str, title: str, body: str, tags: list[str] | None = None,
            approved: bool = True) -> dict:
        if not source.strip() or not title.strip() or not body.strip():
            raise ValueError("source, title and body are required")
        item = {
            "id": str(uuid.uuid4()),
            "ts": datetime.now(timezone.utc).isoformat(),
            "source": source.strip(),
            "title": title.strip(),
            "body": body.strip(),
            "tags": sorted(set(tags or [])),
            "approved": bool(approved),
        }
        with self.store.db:
            self.store.db.execute(
                "INSERT INTO knowledge(id,ts,source,title,body,tags,approved) VALUES(?,?,?,?,?,?,?)",
                (item["id"], item["ts"], item["source"], item["title"], item["body"],
                 json.dumps(item["tags"]), 1 if item["approved"] else 0),
            )
            self.store._event("knowledge_added", {
                "knowledge_id": item["id"], "source": item["source"],
                "title": item["title"], "tags": item["tags"],
                "approved": item["approved"],
            })
        return item

    def search(self, query: str, limit: int = 6, approved_only: bool = True) -> list[dict]:
        q = _tokens(query)
        if not q:
            return []
        sql = "SELECT * FROM knowledge"
        params: tuple = ()
        if approved_only:
            sql += " WHERE approved=1"
        rows = self.store.db.execute(sql, params).fetchall()
        ranked = []
        for row in rows:
            title_tokens = _tokens(row["title"])
            body_tokens = _tokens(row["body"])
            tag_tokens = _tokens(" ".join(json.loads(row["tags"])))
            overlap = len(q & body_tokens)
            score = overlap + 2 * len(q & title_tokens) + 1.5 * len(q & tag_tokens)
            if score:
                ranked.append((score, row))
        ranked.sort(key=lambda x: (-x[0], x[1]["ts"], x[1]["id"]))
        return [{
            "id": row["id"], "source": row["source"], "title": row["title"],
            "body": row["body"], "tags": json.loads(row["tags"]),
            "score": score,
        } for score, row in ranked[:max(1, limit)]]

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
            used.append({k: hit[k] for k in ("id", "source", "title", "score")})
            remaining -= len(block)
            if remaining <= 0:
                break
        return "\n\n".join(parts), used
