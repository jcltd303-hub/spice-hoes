import os
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import Mock, patch

from spicecore.core import Store
from spicecore.distribution.base import PublishResult
from spicecore.distribution.mock import MockPublisher
from spicecore.distribution.scheduler import ConcurrentPostUpdate, Scheduler, ScheduleStatus
from spicecore.distribution.worker import OutboxWorker
from spicecore.media.models import MediaJob, RenderState


class TestPersistentPublicationQueue(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp.name, "ledger.sqlite")
        self.asset = os.path.join(self.temp.name, "asset.png")
        with open(self.asset, "wb") as asset:
            asset.write(b"actual generated asset bytes")
        self.store = Store(self.db_path)
        self.scheduler = Scheduler(self.store)
        self.persona = {"id": "lila_hart", "version": "test", "name": "Lila"}
        self.cid = self.store.propose(
            self.persona, "ceramics", "still", "mock_social", "guide",
            asset_uri=self.asset,
        )
        self.store.review(self.cid, "approved", "policy:v1")
        self.publisher = MockPublisher("mock_social")
        self.worker = OutboxWorker(self.scheduler, {"mock_social": self.publisher}, self.store)

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def enqueue(self, account_id="lila"):
        return self.scheduler.schedule_candidate(
            self.cid, "mock_social", account_id, "2026-10-01T10:00:00Z",
            caption="Studio ceramics.", disclosure="Fictional AI character",
        )

    def test_legacy_media_queue_survives_a_store_restart(self):
        job = MediaJob(
            persona_id="lila_hart", candidate_id=self.cid,
            source_asset_uri=self.asset, script="Studio ceramics.",
            status=RenderState.APPROVED, output_uri=self.asset,
        )
        post = self.scheduler.schedule(job, "mock_social", "lila", "2026-10-01T10:00:00Z")
        self.store.close()
        self.store = Store(self.db_path)
        recovered = Scheduler(self.store).get_post(post.schedule_id)
        self.assertEqual(recovered.media_uri, self.asset)
        self.assertEqual(recovered.status, ScheduleStatus.SCHEDULED)

    def test_candidate_scheduling_deduplicates_across_connections(self):
        post = self.enqueue()
        other_store = Store(self.db_path)
        try:
            other = Scheduler(other_store)
            replay = other.schedule_candidate(
                self.cid, "mock_social", "lila", "2026-10-01T11:00:00Z",
                caption="Changed retry input",
            )
            self.assertEqual(replay.schedule_id, post.schedule_id)
            self.assertEqual(replay.caption, "Studio ceramics.")
            distinct_account = other.schedule_candidate(
                self.cid, "mock_social", "second_account", "2026-10-01T11:00:00Z",
            )
            self.assertNotEqual(distinct_account.schedule_id, post.schedule_id)
            self.assertEqual(len(self.scheduler.list_posts()), 2)
        finally:
            other_store.close()

    def test_candidate_scheduling_requires_approval_and_actual_asset(self):
        proposed = self.store.propose(
            self.persona, "ceramics", "still", "mock_social", "guide",
            asset_uri=self.asset,
        )
        with self.assertRaises(PermissionError):
            self.scheduler.schedule_candidate(proposed, "mock_social", "lila", "2026-10-01T10:00:00Z")
        self.store.db.execute("UPDATE candidates SET asset_uri=? WHERE id=?", ("/missing/image.png", self.cid))
        self.store.db.commit()
        with self.assertRaises(ValueError):
            self.enqueue()

    def test_due_times_compare_instants_across_timezones(self):
        post = self.scheduler.schedule_candidate(
            self.cid, "mock_social", "lila", "2026-10-01T11:00:00+02:00",
        )
        self.assertEqual(self.scheduler.get_due_posts("2026-10-01T08:59:59Z"), [])
        self.assertEqual(self.scheduler.get_due_posts("2026-10-01T09:00:00Z")[0].schedule_id, post.schedule_id)

    def test_only_one_connection_can_claim_a_post(self):
        post = self.enqueue()
        other_store = Store(self.db_path)
        try:
            other = Scheduler(other_store)
            first_claim = self.scheduler.claim_post(post.schedule_id, "2026-10-01T10:30:00Z")
            self.assertIsNotNone(first_claim)
            self.assertIsNone(other.claim_post(post.schedule_id, "2026-10-01T10:30:00Z"))
        finally:
            other_store.close()

    def test_competing_workers_read_the_same_due_row_but_only_one_claims(self):
        post = self.enqueue()
        read_barrier = Barrier(2)

        def claim():
            store = Store(self.db_path)
            try:
                scheduler = Scheduler(store)

                def eligible(current, as_of):
                    result = Scheduler._eligible(current, as_of)
                    read_barrier.wait(timeout=5)
                    return result

                scheduler._eligible = eligible
                return scheduler.claim_post(post.schedule_id, "2026-10-01T10:30:00Z") is not None
            finally:
                store.close()

        with ThreadPoolExecutor(max_workers=2) as pool:
            claims = list(pool.map(lambda _: claim(), range(2)))
        self.assertEqual(sorted(claims), [False, True])

    def test_stale_saved_state_cannot_overwrite_a_confirmed_receipt(self):
        post = self.enqueue()
        other_store = Store(self.db_path)
        try:
            other = Scheduler(other_store)
            stale = other.get_post(post.schedule_id)
            self.assertTrue(self.worker.process_due("2026-10-01T10:30:00Z")[0].success)
            stale.status = ScheduleStatus.SCHEDULED
            with self.assertRaises(ConcurrentPostUpdate):
                other.save_post(stale)
            self.assertEqual(other.get_post(post.schedule_id).status, ScheduleStatus.PUBLISHED)
        finally:
            other_store.close()

    def test_stale_post_cannot_publish_again_after_another_worker(self):
        post = self.enqueue()
        other_store = Store(self.db_path)
        try:
            other_worker = OutboxWorker(Scheduler(other_store), {"mock_social": self.publisher}, other_store)
            self.assertTrue(other_worker.process_due("2026-10-01T10:30:00Z")[0].success)
            result = self.worker.process_post(post, "2026-10-01T10:31:00Z")
            self.assertTrue(result.success)
            self.assertEqual(self.publisher.publish_call_count, 1)
            self.assertEqual(post.status, ScheduleStatus.PUBLISHED)
        finally:
            other_store.close()

    def test_approval_is_revalidated_before_remote_submission(self):
        post = self.enqueue()
        self.store.db.execute("UPDATE candidates SET status='revise' WHERE id=?", (self.cid,))
        self.store.db.commit()
        result = self.worker.process_due("2026-10-01T10:30:00Z")[0]
        self.assertFalse(result.success)
        self.assertEqual(self.publisher.publish_call_count, 0)
        self.assertEqual(Scheduler(self.store).get_post(post.schedule_id).status, ScheduleStatus.FAILED)

    def test_retry_backoff_and_attempt_count_survive_restart(self):
        post = self.enqueue()
        self.publisher.fail_next = True
        self.assertFalse(self.worker.process_due("2026-10-01T10:30:00Z")[0].success)
        reloaded = Scheduler(self.store).get_post(post.schedule_id)
        self.assertEqual(reloaded.retry_count, 1)
        self.assertIsNotNone(reloaded.next_attempt_at)
        self.assertEqual(self.worker.process_due("2026-10-01T10:30:01Z"), [])
        restarted_worker = OutboxWorker(Scheduler(self.store), {"mock_social": self.publisher}, self.store)
        self.assertTrue(restarted_worker.process_due("2026-10-01T10:35:00Z")[0].success)
        self.assertEqual(self.publisher.publish_call_count, 2)

    def test_retryable_failures_stop_at_the_persisted_attempt_limit(self):
        post = self.enqueue()
        publisher = Mock()
        publisher.publish.return_value = PublishResult(
            success=False, platform="mock_social", error_message="temporary rejection", retryable=True,
        )
        worker = OutboxWorker(self.scheduler, {"mock_social": publisher}, self.store)
        for instant in ("2026-10-01T10:30:00Z", "2026-10-01T10:35:00Z", "2026-10-01T10:40:00Z"):
            self.assertFalse(worker.process_due(instant)[0].success)
        self.assertEqual(Scheduler(self.store).get_post(post.schedule_id).status, ScheduleStatus.FAILED)
        self.assertEqual(worker.process_due("2026-10-01T11:00:00Z"), [])
        self.assertEqual(publisher.publish.call_count, 3)

    def test_pending_polling_stops_at_a_bounded_limit(self):
        post = self.enqueue()
        publisher = Mock()
        publisher.publish.return_value = PublishResult(
            success=False, platform="mock_social",
            response_metadata={"pending": True, "provider_state": {"operation_id": "op-1"}},
        )
        worker = OutboxWorker(self.scheduler, {"mock_social": publisher}, self.store, max_pending_polls=2)
        worker.process_due("2026-10-01T10:30:00Z")
        worker.process_due("2026-10-01T10:35:00Z")
        self.assertEqual(Scheduler(self.store).get_post(post.schedule_id).status.value, "needs_reconciliation")
        self.assertEqual(worker.process_due("2026-10-01T11:00:00Z"), [])
        self.assertEqual(publisher.publish.call_count, 2)

    def test_pending_operation_resumes_using_persisted_provider_state(self):
        post = self.enqueue()
        pending = PublishResult(
            success=False, platform="mock_social",
            response_metadata={"pending": True, "provider_state": {"container_id": "container-1"}},
        )
        confirmed = PublishResult(
            success=True, platform="mock_social", external_post_id="post-1",
            canonical_url="https://social.example/post-1",
        )
        publisher = Mock()
        publisher.publish.side_effect = [pending, confirmed]
        worker = OutboxWorker(self.scheduler, {"mock_social": publisher}, self.store)
        self.assertFalse(worker.process_due("2026-10-01T10:30:00Z")[0].success)
        persisted = Scheduler(self.store).get_post(post.schedule_id)
        self.assertEqual(persisted.status.value, "pending")
        self.assertEqual(persisted.provider_state, {"container_id": "container-1"})
        restarted = OutboxWorker(Scheduler(self.store), {"mock_social": publisher}, self.store)
        self.assertTrue(restarted.process_due("2026-10-01T10:35:00Z")[0].success)
        self.assertEqual(publisher.publish.call_args.kwargs["resume_metadata"], {"container_id": "container-1"})
        self.assertEqual(self.store.candidate(self.cid)["status"], "published")

    def test_confirmed_receipt_repairs_ledger_without_remote_resubmission(self):
        post = self.enqueue()
        with patch.object(self.store, "publish", side_effect=RuntimeError("ledger temporarily unavailable")):
            result = self.worker.process_due("2026-10-01T10:30:00Z")[0]
        self.assertFalse(result.success)
        receipt = Scheduler(self.store).get_post(post.schedule_id)
        self.assertEqual(receipt.status.value, "needs_reconciliation")
        self.assertTrue(receipt.external_post_id)
        self.assertTrue(receipt.canonical_url)
        repaired = OutboxWorker(Scheduler(self.store), {"mock_social": self.publisher}, self.store)
        self.assertTrue(repaired.process_due("2026-10-01T10:35:00Z")[0].success)
        self.assertEqual(self.publisher.publish_call_count, 1)
        self.assertEqual(self.store.candidate(self.cid)["status"], "published")
        events = [event for event in self.store.events() if event["kind"] == "content_published"]
        self.assertEqual(len(events), 1)

    def test_success_without_confirmed_receipt_is_not_publication(self):
        post = self.enqueue()
        publisher = Mock()
        publisher.publish.return_value = PublishResult(success=True, platform="mock_social", external_post_id="init-only")
        worker = OutboxWorker(self.scheduler, {"mock_social": publisher}, self.store)
        self.assertFalse(worker.process_due("2026-10-01T10:30:00Z")[0].success)
        self.assertEqual(self.scheduler.get_post(post.schedule_id).status.value, "needs_reconciliation")
        self.assertEqual(self.store.candidate(self.cid)["status"], "approved")
        self.assertEqual(worker.process_due("2026-10-01T11:00:00Z"), [])
        self.assertEqual(publisher.publish.call_count, 1)

    def test_abandoned_submit_is_exposed_without_automatic_resubmission(self):
        post = self.enqueue()
        self.scheduler.claim_post(post.schedule_id, "2026-10-01T10:30:00Z")
        restarted = OutboxWorker(Scheduler(self.store), {"mock_social": self.publisher}, self.store)
        self.assertEqual(restarted.process_due("2026-10-01T12:30:00Z"), [])
        self.assertEqual(restarted.scheduler.get_post(post.schedule_id).status.value, "needs_reconciliation")
        self.assertEqual(self.publisher.publish_call_count, 0)

    def test_abandoned_resume_preserves_id_for_safe_continuation(self):
        post = self.enqueue()
        post.status = ScheduleStatus.PENDING
        post.provider_state = {"container_id": "container-1"}
        self.scheduler.save_post(post)
        self.scheduler.claim_post(post.schedule_id, "2026-10-01T10:30:00Z")
        recovered = Scheduler(self.store).get_due_posts("2026-10-01T12:30:00Z")
        self.assertEqual(len(recovered), 1)
        self.assertEqual(recovered[0].status.value, "pending")
        self.assertEqual(recovered[0].provider_state, {"container_id": "container-1"})

    def test_raised_provider_error_requires_reconciliation(self):
        post = self.enqueue()
        publisher = Mock()
        publisher.publish.side_effect = TimeoutError("response lost after submission")
        worker = OutboxWorker(self.scheduler, {"mock_social": publisher}, self.store)
        self.assertFalse(worker.process_due("2026-10-01T10:30:00Z")[0].success)
        self.assertEqual(self.scheduler.get_post(post.schedule_id).status.value, "needs_reconciliation")
        self.assertEqual(worker.process_due("2026-10-01T11:00:00Z"), [])
        self.assertEqual(publisher.publish.call_count, 1)

    def test_explicit_ambiguous_result_is_never_retried_as_new_submit(self):
        post = self.enqueue()
        publisher = Mock()
        publisher.publish.return_value = PublishResult(
            success=False, platform="mock_social", retryable=True,
            error_message="provider response was ambiguous",
            response_metadata={"needs_reconciliation": True},
        )
        worker = OutboxWorker(self.scheduler, {"mock_social": publisher}, self.store)
        worker.process_due("2026-10-01T10:30:00Z")
        self.assertEqual(self.scheduler.get_post(post.schedule_id).status.value, "needs_reconciliation")
        self.assertEqual(worker.process_due("2026-10-01T11:00:00Z"), [])

    def test_cancel_and_failed_states_cannot_be_published_directly(self):
        post = self.enqueue()
        self.scheduler.cancel(post.schedule_id)
        self.assertFalse(self.worker.process_post(post, "2026-10-01T10:30:00Z").success)
        self.assertEqual(self.publisher.publish_call_count, 0)

    def test_missing_publisher_failure_is_persistent(self):
        post = self.enqueue()
        worker = OutboxWorker(self.scheduler, {}, self.store)
        self.assertFalse(worker.process_due("2026-10-01T10:30:00Z")[0].success)
        self.assertEqual(Scheduler(self.store).get_post(post.schedule_id).status, ScheduleStatus.FAILED)

    def test_publishing_to_second_account_records_both_receipts(self):
        first = self.enqueue("lila")
        second = self.enqueue("other_account")
        results = self.worker.process_due("2026-10-01T10:30:00Z")
        self.assertTrue(all(result.success for result in results))
        self.assertEqual(self.publisher.publish_call_count, 2)
        self.assertNotEqual(first.external_post_id, second.external_post_id)
        self.assertEqual(len([event for event in self.store.events() if event["kind"] == "content_published"]), 2)


if __name__ == "__main__":
    unittest.main()
