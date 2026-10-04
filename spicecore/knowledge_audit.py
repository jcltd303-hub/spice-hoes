"""RAG content audit for the spicecore knowledge base.

Checks the live `knowledge` table and reports:

- inventory: item counts by source, approval state, and embedding model
- provenance: `knowledge_added` events cross-checked against rows (orphans either way)
- approval gate: unapproved items are excluded from retrieval — flag them for review
- prompt-injection scan: bodies are concatenated verbatim into MoA expert prompts,
  so instruction-like text in a body is a live injection risk
- staleness: items older than `stale_days`
- near-duplicates: normalized token overlap above threshold (contradiction risk)
- truncation risk: bodies longer than the `context()` character budget
- retrieval probes: top hit per probe query, with score and method

Findings carry a severity: high (act now), medium (review soon), low (hygiene),
info (context only). The audit is read-only; it never modifies the ledger.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from .memory import KnowledgeBase

# Instruction-like patterns that have no business inside retrieved context.
# Bodies are injected verbatim into expert prompts, so these are live risks.
_INJECTION_PATTERNS = [
    (re.compile(r"ignore\s+(all\s+|any\s+)?previous\s+instructions", re.I),
     "ignore-previous-instructions"),
    (re.compile(r"disregard\s+(all\s+|the\s+|above\s+)?(instructions|constraints|rules)", re.I),
     "disregard-instructions"),
    (re.compile(r"\b(system|developer)\s*:\s*\S", re.I),
     "fake system/developer role"),
    (re.compile(r"you\s+are\s+(now|actually)\s+", re.I),
     "identity override ('you are now')"),
    (re.compile(r"new\s+instructions\s*:", re.I),
     "new-instructions block"),
    (re.compile(r"override\s+(all\s+|the\s+)?(prior|previous|safety|system)\s+", re.I),
     "override prior/safety"),
    (re.compile(r"\bjailbreak\b", re.I),
     "jailbreak mention"),
]

_DUP_JACCARD_THRESHOLD = 0.8
_DUP_PAIR_CAP = 2000  # O(n^2) guard


def _normalize(text: str) -> set:
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def _jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _parse_ts(ts: str) -> Optional[datetime]:
    try:
        dt = datetime.fromisoformat(ts)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None


def _finding(severity: str, code: str, detail: str, ids: Optional[List[str]] = None) -> Dict[str, Any]:
    return {"severity": severity, "code": code, "detail": detail, "ids": ids or []}


def audit_knowledge(
    store,
    probe_queries: Optional[List[str]] = None,
    stale_days: int = 180,
    max_probes: int = 5,
    max_context_chars: int = 8000,
    embedder=None,
) -> Dict[str, Any]:
    """Run the full RAG audit against the live knowledge table. Read-only."""
    kb = KnowledgeBase(store, embedder=embedder)
    rows = [dict(r) for r in store.db.execute("SELECT * FROM knowledge ORDER BY ts").fetchall()]
    findings: List[Dict[str, Any]] = []

    # -- inventory ------------------------------------------------------
    by_source: Dict[str, int] = {}
    by_model: Dict[str, int] = {}
    approved = unapproved = with_embeddings = 0
    for r in rows:
        by_source[r["source"]] = by_source.get(r["source"], 0) + 1
        model = r["embedding_model"] or "(none)"
        by_model[model] = by_model.get(model, 0) + 1
        if r["approved"]:
            approved += 1
        else:
            unapproved += 1
        if r["embedding_json"]:
            with_embeddings += 1
    summary = {
        "items": len(rows),
        "by_source": by_source,
        "approved": approved,
        "unapproved": unapproved,
        "by_embedding_model": by_model,
        "with_embeddings": with_embeddings,
    }
    if unapproved:
        findings.append(_finding(
            "info", "unapproved_items",
            f"{unapproved} item(s) are unapproved and excluded from retrieval; "
            "review or purge them.",
            [r["id"] for r in rows if not r["approved"]],
        ))
    if len([m for m in by_model if m != "(none)"]) > 1:
        findings.append(_finding(
            "medium", "mixed_embedding_models",
            "Multiple embedding models in use — vectors are not comparable in hybrid "
            "retrieval. Run knowledge-backfill to re-embed with one model.",
        ))
    if rows and with_embeddings < len(rows):
        findings.append(_finding(
            "low", "missing_embeddings",
            f"{len(rows) - with_embeddings} item(s) have no embedding and fall back to "
            "lexical-only scoring in hybrid mode.",
        ))

    # -- provenance -----------------------------------------------------
    event_ids = set()
    for ev in store.db.execute("SELECT payload FROM events WHERE kind='knowledge_added'").fetchall():
        try:
            event_ids.add(json.loads(ev["payload"])["knowledge_id"])
        except (KeyError, ValueError, TypeError):
            continue
    row_ids = {r["id"] for r in rows}
    orphan_rows = sorted(row_ids - event_ids)
    orphan_events = sorted(event_ids - row_ids)
    if orphan_rows:
        findings.append(_finding(
            "medium", "rows_without_events",
            "Knowledge rows with no knowledge_added event — possible hand-edited DB.",
            orphan_rows,
        ))
    if orphan_events:
        findings.append(_finding(
            "low", "events_without_rows",
            "knowledge_added events with no matching row — items were deleted after insert.",
            orphan_events,
        ))

    # -- prompt-injection scan ------------------------------------------
    for r in rows:
        text = f"{r['title']}\n{r['body']}"
        hits = sorted({label for pattern, label in _INJECTION_PATTERNS if pattern.search(text)})
        if hits:
            findings.append(_finding(
                "high", "prompt_injection_pattern",
                f"Item '{r['title']}' contains instruction-like text ({', '.join(hits)}). "
                "Bodies are injected verbatim into MoA expert prompts — remove or rewrite.",
                [r["id"]],
            ))

    # -- staleness -------------------------------------------------------
    cutoff = datetime.now(timezone.utc) - timedelta(days=stale_days)
    stale = [r for r in rows if (_parse_ts(r["ts"]) or cutoff) < cutoff]
    if stale:
        findings.append(_finding(
            "low", "stale_items",
            f"{len(stale)} item(s) older than {stale_days} days — verify claims are still true.",
            [r["id"] for r in stale],
        ))

    # -- near-duplicates -------------------------------------------------
    dup_pairs = []
    token_sets = [(r["id"], r["title"], _normalize(r["title"] + "\n" + r["body"])) for r in rows]
    for i in range(min(len(token_sets), _DUP_PAIR_CAP)):
        for j in range(i + 1, min(len(token_sets), _DUP_PAIR_CAP)):
            score = _jaccard(token_sets[i][2], token_sets[j][2])
            if score >= _DUP_JACCARD_THRESHOLD:
                dup_pairs.append((token_sets[i][1], token_sets[j][1], round(score, 3)))
    if dup_pairs:
        findings.append(_finding(
            "medium", "near_duplicates",
            f"{len(dup_pairs)} near-duplicate pair(s) (Jaccard >= {_DUP_JACCARD_THRESHOLD}) — "
            "duplicates dilute retrieval and can surface contradictory guidance: "
            + "; ".join(f"'{a}' ~ '{b}' ({s})" for a, b, s in dup_pairs[:5]),
        ))

    # -- truncation risk -------------------------------------------------
    long_items = [r for r in rows if len(r["body"]) > max_context_chars]
    if long_items:
        findings.append(_finding(
            "low", "truncation_risk",
            f"{len(long_items)} item(s) exceed the {max_context_chars}-char context budget and "
            "will be cut mid-body before experts see them.",
            [r["id"] for r in long_items],
        ))

    # -- retrieval probes ------------------------------------------------
    if probe_queries is None:
        tag_counts: Dict[str, int] = {}
        for r in rows:
            try:
                tags = json.loads(r["tags"])
            except (ValueError, TypeError):
                tags = []
            for t in tags:
                tag_counts[t] = tag_counts.get(t, 0) + 1
        probe_queries = [t for t, _ in sorted(tag_counts.items(), key=lambda kv: -kv[1])[:max_probes]]
    probes = []
    for q in probe_queries[:max_probes]:
        hits = kb.search(q, limit=3)
        probes.append({
            "query": q,
            "top_hit": (
                {"id": hits[0]["id"], "title": hits[0]["title"], "score": hits[0]["score"],
                 "method": hits[0]["retrieval_method"], "source": hits[0]["source"]}
                if hits else None
            ),
            "hit_count": len(hits),
        })
    if probes and all(p["top_hit"] is None for p in probes):
        findings.append(_finding(
            "medium", "retrieval_no_hits",
            "Probe queries returned no hits — the knowledge base may be empty or "
            "queries/tags may be misaligned.",
        ))

    severity_rank = {"high": 0, "medium": 1, "low": 2, "info": 3}
    findings.sort(key=lambda f: (severity_rank[f["severity"]], f["code"]))

    return {
        "summary": summary,
        "findings": findings,
        "retrieval_probes": probes,
        "counts": {
            "high": sum(1 for f in findings if f["severity"] == "high"),
            "medium": sum(1 for f in findings if f["severity"] == "medium"),
            "low": sum(1 for f in findings if f["severity"] == "low"),
            "info": sum(1 for f in findings if f["severity"] == "info"),
        },
    }
