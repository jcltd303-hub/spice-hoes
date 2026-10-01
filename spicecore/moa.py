"""Mixture-of-Agents deliberation tuned for heterogeneous OpenRouter free models."""

from __future__ import annotations

import concurrent.futures
import json
from dataclasses import dataclass

from .memory import KnowledgeBase
from .providers import ProviderError


@dataclass(frozen=True)
class Expert:
    name: str
    instruction: str
    temperature: float = 0.35


DEFAULT_EXPERTS = (
    Expert("revenue", "Evaluate attributable net revenue, conversion, repeat purchase, retention, and cost."),
    Expert("creative", "Propose distinctive content hypotheses that preserve fictional-persona identity consistency."),
    Expert("growth", "Evaluate channel fit, hooks, distribution, funnel steps, and measurable growth experiments."),
    Expert("risk", "Identify platform, disclosure, consent, privacy, likeness, and operational constraints."),
)


def _decode_json(text: str) -> dict:
    """Accept clean JSON or a fenced JSON object from inconsistent free models."""
    value = (text or "").strip()
    if value.startswith("```"):
        lines = value.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        value = "\n".join(lines).strip()
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, dict) else {"result": parsed}
    except json.JSONDecodeError:
        start = value.find("{")
        end = value.rfind("}")
        if start >= 0 and end > start:
            try:
                parsed = json.loads(value[start:end + 1])
                return parsed if isinstance(parsed, dict) else {"result": parsed}
            except json.JSONDecodeError:
                pass
    return {"raw": value, "format_valid": False}


class MixtureOfAgents:
    def __init__(self, provider, store, experts=DEFAULT_EXPERTS, embedder=None):
        self.provider = provider
        self.store = store
        self.knowledge = KnowledgeBase(store, embedder=embedder)
        self.experts = tuple(experts)
        if len(self.experts) < 2:
            raise ValueError("MoA requires at least two experts")

    def _chat_json(self, system: str, user: str, temperature: float,
                   max_tokens: int) -> tuple[dict, bool]:
        """Prefer structured output; fall back once for generic/fake providers."""
        try:
            answer = self.provider.chat(
                system,
                user,
                temperature=temperature,
                response_format={"type": "json_object"},
                max_tokens=max_tokens,
            )
        except TypeError:
            answer = self.provider.chat(system, user, temperature=temperature)
        except ProviderError:
            # Some routed free models can transiently reject structured-output
            # parameters. One plain retry preserves the cycle without a retry loop.
            answer = self.provider.chat(system, user, temperature=temperature)
        parsed = _decode_json(answer)
        return parsed, parsed.get("format_valid") is not False

    def deliberate(self, objective: str, persona: dict | None = None,
                   max_workers: int = 4) -> dict:
        objective = objective.strip()
        if not objective:
            raise ValueError("objective is required")

        query = objective + (" " + json.dumps(persona, sort_keys=True) if persona else "")
        context, citations = self.knowledge.context(query)
        project_context = context or "(none)"
        persona_json = json.dumps(persona or {}, sort_keys=True)

        shared = (
            "OBJECTIVE:\n" + objective +
            "\n\nPERSONA:\n" + persona_json +
            "\n\nAPPROVED PROJECT CONTEXT:\n" + project_context +
            "\n\nReturn a compact JSON object with exactly these keys: "
            "assessment, hypotheses, action, metric, risk. "
            "Use supplied context for project-specific facts. "
            "If evidence is absent, label the item as a hypothesis. "
            "Do not discuss the MoA architecture itself unless the objective explicitly asks about it."
        )

        def ask(expert: Expert) -> dict:
            system = (
                f"You are the {expert.name} specialist. {expert.instruction} "
                "Stay on the user's business objective. Do not invent products, benchmarks, latency targets, "
                "or project facts that are not supplied."
            )
            try:
                response, valid = self._chat_json(system, shared, expert.temperature, 650)
                return {"expert": expert.name, "ok": True, "structured": valid, "response": response}
            except Exception as exc:
                return {
                    "expert": expert.name,
                    "ok": False,
                    "structured": False,
                    "error": f"{type(exc).__name__}: {exc}",
                }

        workers = max(1, min(max_workers, len(self.experts)))
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
            opinions = list(pool.map(ask, self.experts))

        successful = [item for item in opinions if item.get("ok")]
        if len(successful) < 2:
            raise ProviderError(
                f"MoA requires at least two successful experts; got {len(successful)}/{len(opinions)}"
            )

        synthesis_input = json.dumps(successful, ensure_ascii=False, separators=(",", ":"))
        synthesis_prompt = (
            "OBJECTIVE:\n" + objective +
            "\n\nEXPERT OUTPUTS:\n" + synthesis_input +
            "\n\nReturn one JSON object with exactly these keys: "
            "proposed_action, monetization_mechanism, evidence, test_design, "
            "success_metrics, constraints, reversal_condition. "
            "Synthesize only the supplied expert outputs and approved context. "
            "Do not invent numerical thresholds, products, technologies, or evidence. "
            "Where support is weak, explicitly say hypothesis."
        )
        synthesis, synthesis_valid = self._chat_json(
            "You are the final decision aggregator. Resolve disagreement and stay strictly on the objective.",
            synthesis_prompt,
            0.15,
            900,
        )

        result = {
            "architecture": "moa-v2-openrouter",
            "provider": getattr(self.provider, "model_name", type(self.provider).__name__),
            "objective": objective,
            "persona_id": (persona or {}).get("id"),
            "retrieval": citations,
            "experts": opinions,
            "successful_experts": len(successful),
            "synthesis_structured": synthesis_valid,
            "synthesis": synthesis,
        }
        self.store.record_event("moa_deliberation", result)
        return result
