import json
import tempfile
import unittest
from pathlib import Path

from spicecore.core import Store
from spicecore.campaign_moa import build_campaign_objective, engineer_campaign


PERSONA = {
    "id": "zara_voss",
    "version": 3,
    "name": "Zara Voss",
    "disclosure": "Fictional AI persona",
}

EXPERT_JSON = (
    '{"assessment":"ok","hypotheses":[],"action":"lead with the story variant",'
    '"metric":"donation link clicks","risk":"low"}'
)

CLEAN_COPY = (
    "Maplewood community fridge \u2014 help restock the shelves\n"
    "\n"
    "Neighbors, the Maple Street community fridge is running low ahead of the weekend. "
    "If you have a little extra, the official page is here: https://example.org/fridge-fund. "
    "No pressure either way.\n"
    "\n"
    "\u2014 Zara Voss \u00b7 Fictional AI persona \u00b7 Drafted with AI assistance; "
    "a human reviewed this before posting."
)

DIRTY_COPY = (
    "ACT NOW neighbors, I'm your neighbor and this is guaranteed to make you money!!! "
    "Send me money via your bank account routing number today, last chance!!! "
    "Fictional AI persona"
)


def aggregator_json(recommended_copy):
    return json.dumps({
        "proposed_action": "Run the story variant first, then the offer variant.",
        "monetization_mechanism": "donation link",
        "evidence": [],
        "test_design": "Post story variant, then offer variant 48h later; compare link clicks.",
        "success_metrics": ["link_clicks", "donations"],
        "constraints": ["manual posting only", "human review required"],
        "reversal_condition": "zero engagement after both variants",
        "variant_ranking": ["nd_story_42_0", "nd_offer_42_1", "nd_event_42_2"],
        "recommended_copy": recommended_copy,
        "refinements": ["Tighten the story hook."],
    })


class FakeProvider:
    model_name = "fake:test"

    def __init__(self, recommended_copy=""):
        self.calls = []
        self.recommended_copy = recommended_copy

    def chat(self, system, user, temperature=0.4):
        self.calls.append((system, user, temperature))
        if len(self.calls) <= 4:
            return EXPERT_JSON
        return aggregator_json(self.recommended_copy)


def _engineer(recommended_copy, **overrides):
    tmp = tempfile.TemporaryDirectory()
    store = Store(Path(tmp.name) / "campaign_moa.sqlite")
    kw = dict(
        store=store,
        provider=FakeProvider(recommended_copy),
        persona=PERSONA,
        goal="raise funds for the community fridge",
        cause="the Maple Street community fridge",
        neighborhood="Maplewood",
        offer="https://example.org/fridge-fund",
        seed=42,
        count=3,
    )
    kw.update(overrides)
    try:
        plan = engineer_campaign(**kw)
        candidates = store.db.execute("SELECT COUNT(*) FROM candidates").fetchone()[0]
        kinds = [e["kind"] for e in store.events()]
        return plan, candidates, kinds
    finally:
        store.close()
        tmp.cleanup()


class CampaignMoATests(unittest.TestCase):
    def test_objective_carries_constraints_and_variants(self):
        objective = build_campaign_objective(
            PERSONA, "raise funds", "the fridge", "Maplewood",
            "https://example.org/x",
            [{"variant_id": "nd_story_42_0", "kind": "story", "title": "T", "body": "B"}],
        )
        self.assertIn("Do not promise or guarantee", objective)
        self.assertIn("NEVER claim to be a real human", objective)
        self.assertIn("Fictional AI persona", objective)
        self.assertIn("nd_story_42_0", objective)
        self.assertIn("recommended_copy", objective)

    def test_clean_moa_copy_is_proposed(self):
        plan, candidates, kinds = _engineer(CLEAN_COPY)
        self.assertEqual(candidates, 4)  # 3 base variants + 1 MoA-engineered
        self.assertTrue(plan["recommended_proposed"])
        self.assertIsNotNone(plan["recommended_candidate_id"])
        self.assertEqual(plan["recommended_violations"], [])
        self.assertEqual(
            plan["variant_ranking"],
            ["nd_story_42_0", "nd_offer_42_1", "nd_event_42_2"],
        )
        self.assertEqual(kinds[-1], "campaign_engineered")
        self.assertIn("moa_deliberation", kinds)
        self.assertEqual(
            plan["measurement"]["success_metrics"], ["link_clicks", "donations"]
        )

    def test_dirty_moa_copy_is_rejected_not_proposed(self):
        plan, candidates, kinds = _engineer(DIRTY_COPY)
        self.assertEqual(candidates, 3)  # base variants only
        self.assertFalse(plan["recommended_proposed"])
        self.assertIsNone(plan["recommended_candidate_id"])
        self.assertTrue(plan["recommended_violations"])
        self.assertEqual(kinds[-1], "campaign_engineered")

    def test_missing_recommended_copy_is_fine(self):
        plan, candidates, kinds = _engineer("")
        self.assertEqual(candidates, 3)
        self.assertFalse(plan["recommended_proposed"])
        self.assertEqual(plan["recommended_violations"], ["no recommended copy supplied by MoA"])

    def test_requires_persona_with_disclosure(self):
        tmp = tempfile.TemporaryDirectory()
        store = Store(Path(tmp.name) / "x.sqlite")
        try:
            with self.assertRaises(ValueError):
                engineer_campaign(
                    store, FakeProvider(), {"id": "x"},
                    "goal", "cause", "hood",
                )
        finally:
            store.close()
            tmp.cleanup()


if __name__ == "__main__":
    unittest.main()
