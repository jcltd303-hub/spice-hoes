"""Structured, auditable experiment planning and execution."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone


class ExperimentPlanError(ValueError):
    pass


def _decode_json(value: str) -> dict:
    """Decode strict JSON plus common fenced/free-model variants."""
    text = (value or "").strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass
    start, end = text.find("{"), text.rfind("}")
    if start >= 0 and end > start:
        try:
            parsed = json.loads(text[start:end + 1])
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass
    raise ExperimentPlanError("planner returned invalid JSON")


class ExperimentPlanner:
    def __init__(self, provider, store):
        self.provider = provider
        self.store = store
        self._ensure_schema()

    def _ensure_schema(self):
        self.store.db.executescript(
            """
            CREATE TABLE IF NOT EXISTS experiment_plan (
                id TEXT PRIMARY KEY,
                ts TEXT NOT NULL,
                objective TEXT NOT NULL,
                persona_id TEXT NOT NULL,
                persona_version TEXT NOT NULL,
                channel TEXT NOT NULL,
                offer TEXT NOT NULL,
                hypothesis TEXT NOT NULL,
                primary_metric TEXT NOT NULL,
                reversal_condition TEXT NOT NULL,
                variant_count INTEGER NOT NULL,
                plan_json TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS experiment_variant (
                plan_id TEXT NOT NULL,
                variant_id TEXT NOT NULL,
                candidate_id TEXT,
                PRIMARY KEY(plan_id, variant_id)
            );
            """
        )
        self.store.db.commit()

    @staticmethod
    def _validate_plan(plan: dict, variant_count: int) -> dict:
        if not isinstance(plan, dict):
            raise ExperimentPlanError("planner must return an object")
        required = ("hypothesis", "primary_metric", "reversal_condition", "variants")
        if not all(plan.get(key) for key in required):
            raise ExperimentPlanError("planner response missing required fields")
        variants = plan["variants"]
        if not isinstance(variants, list) or len(variants) != variant_count:
            raise ExperimentPlanError(f"expected exactly {variant_count} variants")

        seen = set()
        normalized = []
        for index, variant in enumerate(variants):
            if not isinstance(variant, dict):
                raise ExperimentPlanError("variant must be an object")
            variant_id = str(variant.get("id") or f"v{index + 1}")
            if variant_id in seen:
                raise ExperimentPlanError("variant ids must be unique")
            seen.add(variant_id)
            theme = str(variant.get("theme", "")).strip()
            scene = str(variant.get("scene", "")).strip()
            angle = str(variant.get("creative_angle", "")).strip()
            if not theme or not angle:
                raise ExperimentPlanError("each variant requires theme and creative_angle")
            normalized.append({
                "id": variant_id,
                "theme": theme,
                "scene": scene,
                "creative_angle": angle,
                "caption_direction": str(variant.get("caption_direction", "")).strip(),
                "cta": str(variant.get("cta", "")).strip(),
            })

        return {
            "hypothesis": str(plan["hypothesis"]).strip(),
            "primary_metric": str(plan["primary_metric"]).strip(),
            "secondary_metrics": [
                str(x).strip() for x in plan.get("secondary_metrics", []) if str(x).strip()
            ],
            "reversal_condition": str(plan["reversal_condition"]).strip(),
            "variants": normalized,
        }

    def plan(self, objective: str, persona: dict, channel: str, offer: str,
             deliberation: dict | None = None, variant_count: int = 3) -> dict:
        if not objective.strip() or not channel.strip() or not offer.strip():
            raise ExperimentPlanError("objective, channel and offer are required")
        if variant_count < 2 or variant_count > 6:
            raise ExperimentPlanError("variant_count must be 2..6")

        prompt = {
            "objective": objective,
            "persona": {
                "id": persona["id"],
                "name": persona["name"],
                "age": persona["age"],
                "visual": persona.get("visual", ""),
                "hobbies": persona.get("hobbies", []),
                "voice": persona.get("voice", ""),
            },
            "channel": channel,
            "offer": offer,
            "deliberation": deliberation or {},
            "variant_count": variant_count,
            "schema": {
                "hypothesis": "single falsifiable statement",
                "primary_metric": "one measurable metric",
                "secondary_metrics": ["optional metrics"],
                "reversal_condition": "what result invalidates the hypothesis",
                "variants": [{
                    "id": "v1",
                    "theme": "short content theme",
                    "scene": "visual scene description",
                    "creative_angle": "what differs in this arm",
                    "caption_direction": "caption guidance",
                    "cta": "call to action",
                }],
            },
        }
        system = (
            "You convert strategy into controlled experiments. Return one JSON object only. "
            "Keep variants identical except the intended creative variable where practical. "
            "Do not invent observed performance data. Match the requested schema exactly."
        )
        try:
            raw = self.provider.chat(
                system,
                json.dumps(prompt, ensure_ascii=False, sort_keys=True),
                temperature=0.15,
                response_format={"type": "json_object"},
                max_tokens=1400,
            )
        except TypeError:
            raw = self.provider.chat(
                system,
                json.dumps(prompt, ensure_ascii=False, sort_keys=True),
                temperature=0.15,
            )
        parsed = _decode_json(raw)
        normalized = self._validate_plan(parsed, variant_count)

        plan_id = str(uuid.uuid4())
        ts = datetime.now(timezone.utc).isoformat()
        record = {
            "plan_id": plan_id,
            "objective": objective,
            "persona_id": persona["id"],
            "persona_version": persona["version"],
            "channel": channel,
            "offer": offer,
            **normalized,
        }
        with self.store.db:
            self.store.db.execute(
                """INSERT INTO experiment_plan
                   (id,ts,objective,persona_id,persona_version,channel,offer,hypothesis,
                    primary_metric,reversal_condition,variant_count,plan_json)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    plan_id, ts, objective, persona["id"], persona["version"], channel, offer,
                    normalized["hypothesis"], normalized["primary_metric"],
                    normalized["reversal_condition"], len(normalized["variants"]),
                    json.dumps(record, sort_keys=True),
                ),
            )
            for variant in normalized["variants"]:
                self.store.db.execute(
                    "INSERT INTO experiment_variant(plan_id,variant_id) VALUES(?,?)",
                    (plan_id, variant["id"]),
                )
            self.store._event("experiment_plan_created", {
                "plan_id": plan_id,
                "persona_id": persona["id"],
                "channel": channel,
                "offer": offer,
                "variant_count": len(normalized["variants"]),
                "primary_metric": normalized["primary_metric"],
            })
        return record

    def execute(self, plan: dict, persona: dict, generator,
                base_seed: int | None = None, cost_cents_per_asset: int = 0,
                progress=None) -> list[dict]:
        if plan["persona_id"] != persona["id"]:
            raise ExperimentPlanError("plan/persona mismatch")
        outputs = []
        for index, variant in enumerate(plan["variants"]):
            if progress:
                progress(index, len(plan["variants"]), "Generating " + variant["id"])
            seed = None if base_seed is None else base_seed + index
            result = generator.generate(
                persona=persona,
                theme=variant["theme"],
                channel=plan["channel"],
                offer=plan["offer"],
                scene=variant["scene"],
                seed=seed,
                cost_cents=cost_cents_per_asset,
            )
            with self.store.db:
                self.store.db.execute(
                    """UPDATE experiment_variant SET candidate_id=?
                       WHERE plan_id=? AND variant_id=?""",
                    (result["candidate_id"], plan["plan_id"], variant["id"]),
                )
                self.store._event("experiment_variant_generated", {
                    "plan_id": plan["plan_id"],
                    "variant_id": variant["id"],
                    "candidate_id": result["candidate_id"],
                    "persona_id": persona["id"],
                    "seed": seed,
                })
            outputs.append({
                "plan_id": plan["plan_id"],
                "variant_id": variant["id"],
                "candidate_id": result["candidate_id"],
                "asset": result,
            })
            if progress:
                progress(index + 1, len(plan["variants"]), "Generated " + variant["id"])
        return outputs


    def results(self, plan_id: str) -> dict:
        plan = self.get(plan_id)
        variants = []
        for variant in plan["variants"]:
            candidate_id = variant.get("candidate_id")
            metrics = {
                "impressions": 0,
                "clicks": 0,
                "revenue_cents": 0,
                "refund_cents": 0,
                "distribution_cost_cents": 0,
                "commerce_cost_cents": 0,
                "generation_cost_cents": 0,
                "net_cents": 0,
            }
            status = "not_generated"
            if candidate_id:
                candidate = self.store.candidate(candidate_id)
                status = candidate["status"]
                metrics["generation_cost_cents"] = int(candidate["cost_cents"])
                rows = self.store.db.execute(
                    """SELECT kind,payload FROM events
                       WHERE kind IN ('impression','click','purchase','refund','distribution_cost','commerce_cost')"""
                ).fetchall()
                for row in rows:
                    payload = json.loads(row["payload"])
                    if payload.get("candidate_id") != candidate_id:
                        continue
                    kind = row["kind"]
                    amount = int(payload.get("amount_cents", 0))
                    if kind == "impression":
                        metrics["impressions"] += 1
                    elif kind == "click":
                        metrics["clicks"] += 1
                    elif kind == "purchase":
                        metrics["revenue_cents"] += amount
                    elif kind == "refund":
                        metrics["refund_cents"] += amount
                    elif kind == "distribution_cost":
                        metrics["distribution_cost_cents"] += amount
                    elif kind == "commerce_cost":
                        metrics["commerce_cost_cents"] += amount
                metrics["net_cents"] = (
                    metrics["revenue_cents"]
                    - metrics["refund_cents"]
                    - metrics["distribution_cost_cents"]
                    - metrics["commerce_cost_cents"]
                    - metrics["generation_cost_cents"]
                )

            impressions = metrics["impressions"]
            metrics["click_rate"] = (
                round(metrics["clicks"] / impressions, 6) if impressions else None
            )
            variants.append({
                "variant_id": variant["id"],
                "candidate_id": candidate_id,
                "status": status,
                **metrics,
            })

        observed = [v for v in variants if v["candidate_id"] and v["impressions"] > 0]
        leader = None
        if observed:
            leader = max(
                observed,
                key=lambda v: (v["net_cents"], v["clicks"], v["variant_id"]),
            )["variant_id"]
        return {
            "plan_id": plan_id,
            "persona_id": plan["persona_id"],
            "primary_metric": plan["primary_metric"],
            "reversal_condition": plan["reversal_condition"],
            "variants": variants,
            "observed_leader_by_net_cents": leader,
            "interpretation": (
                "Descriptive observed results only; do not treat as causal until exposure is sufficient."
            ),
        }

    def get(self, plan_id: str) -> dict:
        row = self.store.db.execute(
            "SELECT plan_json FROM experiment_plan WHERE id=?", (plan_id,)
        ).fetchone()
        if row is None:
            raise ExperimentPlanError("unknown experiment plan")
        plan = json.loads(row["plan_json"])
        links = {
            r["variant_id"]: r["candidate_id"]
            for r in self.store.db.execute(
                "SELECT variant_id,candidate_id FROM experiment_variant WHERE plan_id=?",
                (plan_id,),
            )
        }
        for variant in plan["variants"]:
            variant["candidate_id"] = links.get(variant["id"])
        return plan
