"""Small Stripe webhook receiver; the signing secret is the endpoint credential."""

import json
from http.server import BaseHTTPRequestHandler

from .commerce import StripeCommerce
from .core import Store


MAX_WEBHOOK_BODY_BYTES = 1024 * 1024


def make_commerce_handler(db_path, signing_secret: str, live_mode: bool = True):
    if not isinstance(signing_secret, str) or not signing_secret.strip():
        raise ValueError("Stripe webhook signing secret is required")
    if type(live_mode) is not bool:
        raise ValueError("live_mode must be boolean")

    class Handler(BaseHTTPRequestHandler):
        def _respond(self, status, payload):
            body = json.dumps(payload, sort_keys=True).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.write(body)
            self.close_connection = True

        def do_POST(self):
            if self.path != "/webhooks/stripe":
                self._respond(404, {"error": "not_found"})
                return
            sizes = self.headers.get_all("Content-Length") or []
            signatures = self.headers.get_all("Stripe-Signature") or []
            if (self.headers.get("Transfer-Encoding") or len(sizes) != 1
                    or not sizes[0].isascii() or not sizes[0].isdigit()):
                self._respond(400, {"error": "invalid_request"})
                return
            if len(sizes[0]) > 10:
                self._respond(413, {"error": "body_too_large"})
                return
            size = int(sizes[0])
            if size > MAX_WEBHOOK_BODY_BYTES:
                self._respond(413, {"error": "body_too_large"})
                return
            if size == 0 or len(signatures) != 1:
                self._respond(400, {"error": "invalid_request"})
                return
            store = None
            try:
                self.connection.settimeout(10)
                body = self.rfile.read(size)
                if len(body) != size:
                    self._respond(400, {"error": "invalid_request"})
                    return
                store = Store(db_path)
                commerce = StripeCommerce(store, signing_secret, live_mode)
                result = commerce.ingest(body, signatures[0])
            except (PermissionError, ValueError, UnicodeError):
                self._respond(400, {"error": "invalid_webhook"})
                return
            except Exception:
                self._respond(503, {"error": "temporarily_unavailable"})
                return
            finally:
                if store is not None:
                    store.close()
            self._respond(200, result)

        def do_GET(self):
            self._respond(405, {"error": "method_not_allowed"})

        do_PUT = do_DELETE = do_PATCH = do_HEAD = do_GET

        def log_message(self, format, *args):
            # BaseHTTPRequestHandler otherwise logs the raw request path.
            pass

    return Handler
