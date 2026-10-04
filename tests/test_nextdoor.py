import unittest

from spicecore.distribution import (
    NextdoorPublisher,
    generate_campaign,
    validate_copy,
)
from spicecore.distribution.nextdoor import PLATFORM


PERSONA = {
    "id": "zara_voss",
    "version": 3,
    "name": "Zara Voss",
    "disclosure": "Fictional AI persona",
}


def _campaign(**overrides):
    kw = dict(
        persona=PERSONA,
        goal="raise funds for the community fridge",
        cause="the Maple Street community fridge",
        neighborhood="Maplewood",
        offer="https://example.org/fridge-fund",
        seed=42,
        count=3,
    )
    kw.update(overrides)
    return generate_campaign(**kw)


class TestNextdoorCopyPolicy(unittest.TestCase):
    def test_rejects_fake_neighbor_identity(self):
        self.assertIn(
            "claims to be a real human/neighbor",
            validate_copy("Hi, I'm your neighbor and I live at 123 Main St, trust me!"),
        )

    def test_rejects_guaranteed_earnings(self):
        self.assertIn(
            "guaranteed-earnings claim",
            validate_copy("This is guaranteed to make you money fast!"),
        )

    def test_allows_word_guarantee_without_money_context(self):
        self.assertNotIn(
            "guaranteed-earnings claim",
            validate_copy("I guarantee I'll show up on time."),
        )

    def test_rejects_pressure_language(self):
        self.assertIn(
            "pressure/manipulation language",
            validate_copy("Act now, last chance, you must donate today!"),
        )

    def test_rejects_banking_requests(self):
        self.assertIn(
            "requests payment-card or banking details",
            validate_copy("Just send me money via your bank account routing number."),
        )

    def test_rejects_shouting_and_spam_links(self):
        self.assertIn("shouting (long all-caps run)", validate_copy("THIS IS A TOTALLY NORMAL SENTENCE HERE OK"))
        self.assertIn("excessive exclamation marks", validate_copy("Wow!!! Amazing!!!"))
        self.assertIn(
            "too many links (spam pattern)",
            validate_copy("a http://x.co/1 b http://x.co/2 c http://x.co/3"),
        )

    def test_requires_disclosure_when_asked(self):
        self.assertIn(
            "missing persona disclosure",
            validate_copy("clean copy", require_disclosure="Fictional AI persona"),
        )
        self.assertEqual(
            [],
            validate_copy("clean copy\nFictional AI persona", require_disclosure="Fictional AI persona"),
        )


class TestNextdoorCampaignGenerator(unittest.TestCase):
    def test_deterministic_with_seed(self):
        first = [v.to_dict() for v in _campaign()]
        second = [v.to_dict() for v in _campaign()]
        self.assertEqual(first, second)

    def test_different_seeds_differ(self):
        bodies_a = [v.body for v in _campaign(seed=1)]
        bodies_b = [v.body for v in _campaign(seed=2)]
        self.assertNotEqual(bodies_a, bodies_b)

    def test_variant_kinds(self):
        kinds = [v.kind for v in _campaign()]
        self.assertEqual(kinds, ["story", "offer", "event"])

    def test_generated_copy_is_policy_clean_and_disclosed(self):
        for v in _campaign():
            self.assertEqual(v.violations, [])
            self.assertIn(PERSONA["disclosure"], v.body)
            self.assertEqual(validate_copy(v.body, require_disclosure=PERSONA["disclosure"]), [])

    def test_requires_inputs(self):
        with self.assertRaises(ValueError):
            _campaign(goal="  ")
        with self.assertRaises(ValueError):
            _campaign(persona={"id": "x"})


class TestNextdoorPublisher(unittest.TestCase):
    def setUp(self):
        self.pub = NextdoorPublisher()

    def test_platform_name(self):
        self.assertEqual(self.pub.platform_name, "nextdoor")
        self.assertEqual(PLATFORM, "nextdoor")

    def test_publish_fails_closed_with_manual_handoff(self):
        res = self.pub.publish(
            media_uri="https://cdn.example.com/fridge.jpg",
            caption="Neighbors \u2014 the Maple Street community fridge needs restocking.",
            disclosure="Fictional AI persona",
            account_id="maplewood_account",
            idempotency_key="nd_key_001",
        )
        self.assertFalse(res.success)
        self.assertFalse(res.retryable)
        self.assertIn("no public posting API", res.error_message)
        staged = res.response_metadata["staged"]
        self.assertTrue(res.response_metadata["manual_handoff"])
        self.assertIn("Fictional AI persona", staged["text"])
        self.assertEqual(len(staged["manual_steps"]), 5)

    def test_publish_replays_idempotency_key(self):
        first = self.pub.publish(
            media_uri="https://cdn.example.com/fridge.jpg",
            caption="Neighbors \u2014 restocking the community fridge.",
            disclosure="Fictional AI persona",
            account_id="maplewood_account",
            idempotency_key="nd_key_002",
        )
        second = self.pub.publish(
            media_uri="https://cdn.example.com/fridge.jpg",
            caption="Neighbors \u2014 restocking the community fridge.",
            disclosure="Fictional AI persona",
            account_id="maplewood_account",
            idempotency_key="nd_key_002",
        )
        self.assertTrue(second.response_metadata["idempotent_replay"])
        self.assertEqual(first.response_metadata["staged"], second.response_metadata["staged"])

    def test_publish_rejects_policy_violations(self):
        res = self.pub.publish(
            media_uri="https://cdn.example.com/x.jpg",
            caption="I'm your neighbor, guaranteed to make you money, act now!!!",
            disclosure="Fictional AI persona",
            account_id="maplewood_account",
        )
        self.assertFalse(res.success)
        self.assertFalse(res.retryable)
        self.assertTrue(res.response_metadata["violations"])

    def test_schedule_marks_requested_time(self):
        res = self.pub.schedule(
            media_uri="https://cdn.example.com/x.jpg",
            caption="Clean neighborhood post.",
            disclosure="Fictional AI persona",
            account_id="maplewood_account",
            scheduled_at_iso="2026-10-04T18:00:00+00:00",
        )
        self.assertFalse(res.success)
        self.assertEqual(
            res.response_metadata["requested_schedule_at"], "2026-10-04T18:00:00+00:00"
        )

    def test_delete_returns_false(self):
        self.assertFalse(self.pub.delete("anything", "maplewood_account"))

    def test_fetch_metrics_raises(self):
        with self.assertRaises(RuntimeError):
            self.pub.fetch_metrics("anything", "maplewood_account")


if __name__ == "__main__":
    unittest.main()
