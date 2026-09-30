"""Loopback-only review page, intentionally not a public deployment target."""

import hmac
import logging
import mimetypes
from pathlib import Path
from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlsplit

from .core import Store
from .workflow import apply_review, render_dashboard


def make_handler(store: Store, personas: list[dict], token: str):
    if not token:
        raise ValueError('A review token is required')
    db_path = store.db.execute('PRAGMA database_list').fetchone()['file']

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            parsed = urlsplit(self.path)
            supplied = parse_qs(parsed.query).get('token', [''])[0]
            if not hmac.compare_digest(supplied, token):
                self.send_error(403)
                return
            if parsed.path.startswith('/asset/'):
                cid = parsed.path[len('/asset/'):]
                db = Store(db_path)
                try:
                    row = db.candidate(cid)
                except ValueError:
                    db.close(); self.send_error(404); return
                finally:
                    if 'row' in locals(): db.close()
                uri = row.get('asset_uri')
                if not uri:
                    self.send_error(404); return
                asset = Path(uri).expanduser().resolve()
                allowed = Path('assets/generated').resolve()
                if asset != allowed and allowed not in asset.parents:
                    self.send_error(403); return
                if not asset.is_file():
                    self.send_error(404); return
                body = asset.read_bytes()
                self.send_response(200)
                self.send_header('Content-Type', mimetypes.guess_type(asset.name)[0] or 'application/octet-stream')
                self.send_header('Cache-Control', 'no-store')
                self.send_header('Content-Length', str(len(body)))
                self.end_headers(); self.wfile.write(body); return
            if parsed.path != '/':
                self.send_error(404); return
            db = Store(db_path)
            try:
                body = render_dashboard(db, personas, token).encode('utf-8')
            finally:
                db.close()
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            if self.path != '/review':
                self.send_error(404)
                return
            try:
                size = int(self.headers.get('Content-Length', '0'))
                if size < 1 or size > 8192:
                    self.send_error(413)
                    return
                fields = parse_qs(self.rfile.read(size).decode('utf-8'))
                one = lambda key: fields.get(key, [''])[0]
                db = Store(db_path)
                try:
                    apply_review(db, one('candidate_id'), one('decision'), one('reviewer'),
                                 one('note'), one('token'), token)
                finally:
                    db.close()
            except PermissionError:
                self.send_error(403)
                return
            except (ValueError, UnicodeDecodeError) as error:
                self.send_error(400, str(error))
                return
            self.send_response(303)
            self.send_header('Location', '/?token=' + token)
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()

        def log_message(self, format, *args):
            logging.info('%s %s', self.address_string(), format % args)

    return Handler
