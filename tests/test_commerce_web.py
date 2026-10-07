import hashlib
import hmac
import http.client
import json
import tempfile
import threading
import time
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from spicecore.commerce_web import MAX_WEBHOOK_BODY_BYTES, make_commerce_handler
from spicecore.core import Store


class StripeCommerceWebTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "web.sqlite"
        self.secret = "whsec_local_web_fixture"
        self.server = ThreadingHTTPServer(("127.0.0.1", 0),
                                         make_commerce_handler(self.path, self.secret))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        self.tmp.cleanup()

    def request(self, body=b"{}", headers=None, path="/webhooks/stripe", method="POST"):
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=3)
        connection.request(method, path, body=body, headers=headers or {})
        response = connection.getresponse()
        status, content = response.status, response.read()
        connection.close()
        return status, content

    def signed(self, obj):
        body = json.dumps(obj).encode()
        ts = int(time.time())
        sig = hmac.new(self.secret.encode(), str(ts).encode() + b"." + body,
                       hashlib.sha256).hexdigest()
        return body, {"Stripe-Signature": f"t={ts},v1={sig}", "Content-Type": "application/json"}

    def test_signed_test_fixture_is_acknowledged_without_income(self):
        body, headers = self.signed({"id": "evt_test_web", "type": "checkout.session.completed",
                                     "livemode": False, "data": {"object": {"id": "cs_test_web"}}})
        status, result = self.request(body, headers)
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(result)["state"], "test")
        store = Store(self.path)
        try:
            self.assertFalse([e for e in store.events() if e["kind"] == "purchase"])
        finally:
            store.close()

    def test_invalid_signature_and_bad_json_return_clean_errors(self):
        status, body = self.request(b"{\"secret\":\"private_customer\"}")
        self.assertEqual(status, 400)
        self.assertNotIn(b"private_customer", body)
        self.assertNotIn(self.secret.encode(), body)
        ts = int(time.time())
        raw = b"bad json"
        digest = hmac.new(self.secret.encode(), str(ts).encode() + b"." + raw,
                          hashlib.sha256).hexdigest()
        self.assertEqual(self.request(raw, {"Stripe-Signature": f"t={ts},v1={digest}"})[0], 400)

    def test_route_size_and_transfer_encoding_are_bounded(self):
        self.assertEqual(self.request(path="/other")[0], 404)
        self.assertEqual(self.request(method="GET")[0], 405)
        self.assertEqual(self.request(b"x", {"Content-Length": str(MAX_WEBHOOK_BODY_BYTES + 1)})[0], 413)
        self.assertEqual(self.request(b"", {"Content-Length": "-1"})[0], 400)
        self.assertEqual(self.request(b"", {"Transfer-Encoding": "chunked"})[0], 400)

    def test_internal_failure_is_retryable_and_does_not_expose_secrets(self):
        body, headers = self.signed({"id": "evt_web", "type": "ignored.event", "livemode": True,
                                     "data": {"object": {"id": "ch_web"}}})
        with patch("spicecore.commerce_web.StripeCommerce.ingest",
                   side_effect=RuntimeError(self.secret)):
            status, content = self.request(body, headers)
        self.assertEqual(status, 503)
        self.assertNotIn(self.secret.encode(), content)


if __name__ == "__main__":
    unittest.main()
