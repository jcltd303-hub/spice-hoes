"""Mixture-of-Agents deliberation tuned for heterogeneous OpenRouter free models."""

from __future__ import annotations

import concurrent.futures
import json
import os
from dataclasses import dataclass

from .memory import KnowledgeBase
from .providers import ProviderError


@dataclass(frozen=True)
class Expert:
    name: str
    instruction: str
    model: str
    temperature: float = 0.35
    supports_response_format: bool = False
    max_tokens: int = 1200


DEFAULT_EXPERTS = (
    Expert(
        "revenue",
        "Evaluate attributable net revenue, conversion, repeat purchase, retention, and cost.",
        "nvidia/nemotron-3-super-120b-a12b:free",
        supports_response_format=True,
    ),
    Expert(
        "creative",
        "Propose distinctive content hypotheses that preserve fictional-persona identity consistency.",
        "qwen/qwen3.8-27b:free",
        supports_response_format=True,
    ),
    Expert(
        "growth",
        "Evaluate channel fit, hooks, distribution, funnel steps, and measurable growth experiments.",
        "inclusionai/ling-3.0-flash-vl:free",
        supports_response_format=False,
    ),
    Expert(
        "risk",
        "Identify platform, disclosure, consent, privacy, likeness, and operational constraints.",
        "google/gemma-4-31b-it:free",
        supports_response_format=True,
    ),
)

DEFAULT_AGGREGATOR_MODEL = "nvidia/nemotron-3-ultra-550b-a55b:free"
DEFAULT_FALLBACK_MODELS = (
    "nvidia/nemotron-3-super-120b-a12b:free",
    "qwen/qwen3.8-27b:free",
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

    def _fallback_models(self, role: str) -> tuple[str, ...]:
        role_key = f"MOA_{role.upper()}_FALLBACK_MODELS"
        raw = os.getenv(role_key, os.getenv("MOA_FALLBACK_MODELS", ""))
        if raw.strip():
            return tuple(item.strip() for item in raw.split(",") if item.strip())
        return DEFAULT_FALLBACK_MODELS

    def _role_model(self, role: str, default: str) -> str:
        return os.getenv(f"MOA_MODEL_{role.upper()}", default).strip() or default

    def _chat_json(self, system: str, user: str, temperature: float,
                   max_tokens: int, model: str, fallbacks: tuple[str, ...],
                   supports_response_format: bool) -> tuple[dict, bool, dict]:
        """Call one pinned role model with explicit fallbacks and return response metadata."""
        kwargs = {
            "temperature": temperature,
            "max_tokens": max_tokens,
            "model": model,
            "models": list(fallbacks),
            "reasoning_enabled": os.getenv("MOA_REASONING_ENABLED", "false").lower() in ("1", "true", "yes"),
        }
        if supports_response_format:
            kwargs["response_format"] = {"type": "json_object"}

        try:
            if hasattr(self.provider, "chat_detailed"):
                detail = self.provider.chat_detailed(system, user, **kwargs)
                answer = detail["content"]
            else:
                try:
                    answer = self.provider.chat(system, user, **kwargs)
                except TypeError:
                    # Compatibility path for simple test/fake providers.
                    answer = self.provider.chat(system, user, temperature=temperature)
                detail = {
                    "content": answer,
                    "model": getattr(self.provider, "model_name", model),
                    "requested_model": model,
                    "usage": {},
                }
        except ProviderError:
            if not supports_response_format:
                raise
            # A model/provider may reject response_format despite catalog metadata.
            kwargs.pop("response_format", None)
            if hasattr(self.provider, "chat_detailed"):
                detail = self.provider.chat_detailed(system, user, **kwargs)
                answer = detail["content"]
            else:
                answer = self.provider.chat(system, user, temperature=temperature)
                detail = {
                    "content": answer,
                    "model": getattr(self.provider, "model_name", model),
                    "requested_model": model,
                    "usage": {},
                }

        parsed = _decode_json(answer)
        valid = parsed.get("format_valid") is not False
        meta = {
            "requested_model": detail.get("requested_model", model),
            "actual_model": detail.get("model", model),
            "usage": detail.get("usage", {}),
        }
        return parsed, valid, meta

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
                requested_model = self._role_model(expert.name, expert.model)
                response, valid, meta = self._chat_json(
                    system,
                    shared,
                    expert.temperature,
                    expert.max_tokens,
                    requested_model,
                    self._fallback_models(expert.name),
                    expert.supports_response_format,
                )
                if not valid:
                    return {
                        "expert": expert.name,
                        "ok": False,
                        "structured": False,
                        "requested_model": meta["requested_model"],
                        "actual_model": meta["actual_model"],
                        "usage": meta["usage"],
                        "error": "invalid JSON response",
                        "response": response,
                    }
                return {
                    "expert": expert.name,
                    "ok": True,
                    "structured": True,
                    "requested_model": meta["requested_model"],
                    "actual_model": meta["actual_model"],
                    "usage": meta["usage"],
                    "response": response,
                }
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
        aggregator_model = self._role_model("aggregator", DEFAULT_AGGREGATOR_MODEL)
        synthesis, synthesis_valid, synthesis_meta = self._chat_json(
            "You are the final decision aggregator. Resolve disagreement and stay strictly on the objective.",
            synthesis_prompt,
            0.15,
            int(os.getenv("MOA_AGGREGATOR_MAX_TOKENS", "1800")),
            aggregator_model,
            self._fallback_models("aggregator"),
            False,
        )
        if not synthesis_valid:
            raise ProviderError("MoA aggregator returned invalid JSON")

        result = {
            "architecture": "moa-v3-heterogeneous-openrouter",
            "provider": getattr(self.provider, "model_name", type(self.provider).__name__),
            "objective": objective,
            "persona_id": (persona or {}).get("id"),
            "retrieval": citations,
            "experts": opinions,
            "successful_experts": len(successful),
            "synthesis_structured": synthesis_valid,
            "aggregator": {
                "requested_model": synthesis_meta["requested_model"],
                "actual_model": synthesis_meta["actual_model"],
                "usage": synthesis_meta["usage"],
            },
            "synthesis": synthesis,
        }
        self.store.record_event("moa_deliberation", result)
        return result
