import json
import unittest

from spicecore.local_compute import LocalChatProvider
from spicecore.learning import LearningController
from spicecore.memory import KnowledgeBase
from spicecore.moa import MixtureOfAgents
from tests import test_learning


class ProductionMemoryTests(unittest.TestCase):
    def setUp(self):
        self.fixture = test_learning.LearningClosureTests()
        self.fixture.setUp()
        self.store = self.fixture.store
        self.run = self.fixture.create_run()
        for output in self.run["outputs"]:
            cid = output["candidate_id"]
            self.store.review(cid, "approved", "owner")
            self.store.publish(cid, "https://www.instagram.com/p/receipt/")
            self.store.record_event("impression", {"candidate_id": cid, "count": 100,
                                   "persona_id": self.store.candidate(cid)["persona_id"]})
        self.provider = LocalChatProvider(model="strategy")

    def tearDown(self):
        self.fixture.tearDown()

    def test_legacy_manual_profit_cannot_enter_production_moa_context(self):
        for output in self.run["outputs"]:
            self.store.record_outcome(output["candidate_id"], "purchase", 500000)
        legacy = self.fixture.learning.settle_autopilot_run(self.run["run_id"])
        fact = self.fixture.knowledge.add("project:offer", "Approved conversion product facts",
                                         "The product is a PDF style guide.")
        context, citations = MixtureOfAgents(self.provider, self.store).knowledge.context(
            "Improve affiliate conversion observed experiment product")
        self.assertNotIn(legacy["knowledge_id"], [c["id"] for c in citations])
        self.assertNotIn('"reward_cents": 999950', context)
        self.assertIn(fact["id"], [c["id"] for c in citations])
        self.assertIn(legacy["knowledge_id"], [c["id"] for c in self.fixture.knowledge.search("observed experiment")])

    def test_current_verified_closure_is_retrieved(self):
        learning = LearningController(self.store, self.fixture.people, self.fixture.planner,
                                      self.fixture.knowledge, verified_revenue_only=True)
        result = learning.settle_autopilot_run(self.run["run_id"])
        _, citations = MixtureOfAgents(self.provider, self.store).knowledge.context("observed experiment conversion")
        self.assertIn(result["knowledge_id"], [c["id"] for c in citations])

    def test_unlinked_claim_of_verification_is_not_experiment_evidence(self):
        claimed = self.fixture.knowledge.add("experiment:invented", "Observed experiment conversion",
                                             json.dumps({"verified_revenue_only": True, "reward_cents": 999999}))
        _, citations = MixtureOfAgents(self.provider, self.store).knowledge.context("observed experiment conversion")
        self.assertNotIn(claimed["id"], [c["id"] for c in citations])
