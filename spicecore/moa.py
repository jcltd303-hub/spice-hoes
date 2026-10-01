"""Mixture-of-Agents deliberation with RAG grounding and an auditable synthesis step."""

from __future__ import annotations

import concurrent.futures
import json
from dataclasses import dataclass

from .memory import KnowledgeBase


@dataclass(frozen=True)
class Expert:
    name: str
    instruction: str
    temperature: float = 0.4


DEFAULT_EXPERTS = (
    Expert("revenue", "Optimize for attributable net revenue, repeat purchase, retention and low production cost."),
    Expert("creative", "Generate distinctive content hypotheses while protecting identity consistency and novelty."),
    Expert("growth", "Focus on channel fit, distribution, conversion funnels and measurable experiments."),
    Expert("risk", "Identify platform, disclosure, consent, privacy, likeness and operational risks. Reject ineligible tactics."),
)


class MixtureOfAgents:
    def __init__(self, provider, store, experts=DEFAULT_EXPERTS):
        self.provider = provider
        self.store = store
        self.knowledge = KnowledgeBase(store)
        self.experts = tuple(experts)
        if len(self.experts) < 2:
            raise ValueError("MoA requires at least two experts")

    def deliberate(self, objective: str, persona: dict | None = None,
                   max_workers: int = 4) -> dict:
        if not objective.strip():
            raise ValueError("objective is required")
        query = objective + (" " + json.dumps(persona, sort_keys=True) if persona else "")
        context, citations = self.knowledge.context(query)
        shared = (
            "You are one expert in a mixture-of-agents system. Use only the supplied project context "
            "for project-specific facts. Clearly mark hypotheses. The persona, if supplied, is a fictional adult. "
            "Do not imitate a real person's likeness. Produce concise JSON-compatible analysis, not hidden reasoning.\n\n"
            f"OBJECTIVE:\n{objective}\n\nPERSONA:\n{json.dumps(persona or {}, sort_keys=True)}\n\n"
            f"RETRIEVED CONTEXT:\n{context or '(none)'}"
        )

        def ask(expert: Expert) -> dict:
            answer = self.provider.chat(
                f"Role: {expert.name}. {expert.instruction}",
                shared,
                temperature=expert.temperature,
            )
            return {"expert": expert.name, "response": answer}

        with concurrent.futures.ThreadPoolExecutor(max_workers=min(max_workers, len(self.experts))) as pool:
            opinions = list(pool.map(ask, self.experts))

        synthesis_prompt = (
            "Act as the aggregator in a true mixture-of-agents workflow. Compare the independent expert outputs below. "
            "Return one actionable recommendation with: proposed action, expected monetization mechanism, evidence used, "
            "test design, success metrics, cost/risk constraints, and what result would cause reversal. "
            "Do not claim evidence that is absent. Do not expose hidden chain-of-thought.\n\n"
            + json.dumps(opinions, ensure_ascii=False)
        )
        synthesis = self.provider.chat(
            "You aggregate expert proposals into an auditable decision proposal. Human approval remains required.",
            synthesis_prompt,
            temperature=0.2,
        )
        result = {
            "architecture": "moa-v1",
            "provider": getattr(self.provider, "model_name", type(self.provider).__name__),
            "objective": objective,
            "persona_id": (persona or {}).get("id"),
            "retrieval": citations,
            "experts": opinions,
            "synthesis": synthesis,
        }
        self.store.record_event("moa_deliberation", result)
        return result
