import hashlib
import io
import os
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from spicecore.media_delivery import MediaDelivery, PublicDirectoryMediaDelivery, make_media_handler


class _Response(io.BytesIO):
    def __init__(self, payload):
        super().__init__(payload)
        self.status = 200
        self.headers = {'Content-Type': 'image/jpeg'}


class MediaDeliveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / 'private-persona.png'
        Image.new('RGBA', (32, 48), (12, 70, 150, 180)).save(self.path)
        self.public = self.root / 'public'
        self.adapter = PublicDirectoryMediaDelivery(self.public, 'https://media.example.com')

    def prepare(self, candidate):
        def fetch(request, **kwargs):
            return _Response((self.public / request.full_url.rsplit('/', 1)[1]).read_bytes())
        with patch('spicecore.media_delivery.urllib.request.urlopen', side_effect=fetch):
            return self.adapter.prepare(candidate)

    def test_from_env_names_only_required_host_configuration(self):
        with patch.dict(os.environ, {}, clear=True), self.assertRaises(ValueError) as raised:
            MediaDelivery.from_env()
        self.assertIn('SPICE_MEDIA_PUBLIC_BASE_URL', str(raised.exception))

    def test_sanitizes_image_and_returns_content_addressed_public_url(self):
        uri = self.prepare({'asset_uri': str(self.path)})
        payload = (self.public / uri.rsplit('/', 1)[1]).read_bytes()
        self.assertEqual(uri, 'https://media.example.com/' + hashlib.sha256(payload).hexdigest() + '.jpg')
        with Image.open(io.BytesIO(payload)) as result:
            self.assertEqual(result.format, 'JPEG')
            self.assertEqual(result.mode, 'RGB')
            self.assertEqual(result.size, (32, 48))
            self.assertFalse(result.getexif())
        self.assertNotIn('persona', uri)
        self.assertTrue(self.adapter.readiness()['ready'])

    def test_reuses_identical_bytes_across_personas(self):
        first = self.prepare({'id': 'first', 'asset_uri': str(self.path)})
        copy = self.root / 'another.png'
        copy.write_bytes(self.path.read_bytes())
        second = self.prepare({'id': 'second', 'asset_uri': str(copy)})
        self.assertEqual(first, second)
        self.assertEqual(len(list(self.public.glob('*.jpg'))), 1)

    def test_explicit_public_uri_is_unchanged(self):
        uri = 'https://cdn.example.com/photo.jpg?version=2'
        self.assertEqual(self.adapter.prepare({'media_uri': uri, 'asset_uri': 'missing'}), uri)

    def test_invalid_base_urls_and_remote_uris_are_rejected(self):
        for uri in ['http://cloud.example/', 'https://user:secret@cloud.example/',
                    'https://cloud.example/?token=secret', 'https://cloud.example/#fragment']:
            with self.subTest(uri=uri), self.assertRaises(ValueError):
                PublicDirectoryMediaDelivery(self.public, uri)
        for uri in ['http://cdn.example/photo.jpg', 'data:image/png;base64,abc',
                    'https://user:secret@cdn.example/photo.jpg']:
            with self.subTest(uri=uri), self.assertRaises(ValueError):
                self.adapter.prepare({'asset_uri': uri})

    def test_public_url_must_return_the_actual_saved_bytes(self):
        with patch('spicecore.media_delivery.urllib.request.urlopen', return_value=_Response(b'wrong bytes')):
            with self.assertRaisesRegex(RuntimeError, 'verification'):
                self.adapter.prepare({'asset_uri': str(self.path)})

    def test_verification_errors_do_not_leak_signed_urls(self):
        with patch('spicecore.media_delivery.urllib.request.urlopen', side_effect=OSError('secret URL')):
            with self.assertRaises(RuntimeError) as error:
                self.adapter.prepare({'asset_uri': str(self.path)})
        self.assertNotIn('secret', str(error.exception))

    def test_existing_corrupt_file_is_rejected(self):
        uri = self.prepare({'asset_uri': str(self.path)})
        (self.public / uri.rsplit('/', 1)[1]).write_bytes(b'corrupt')
        with self.assertRaisesRegex(RuntimeError, 'content'):
            self.prepare({'asset_uri': str(self.path)})

    def test_missing_and_nonimage_files_fail_before_serving(self):
        bad = self.root / 'fake.png'
        bad.write_bytes(b'not image bytes')
        for source in [str(bad), str(bad) + '.missing']:
            with self.subTest(source=source), self.assertRaises(ValueError):
                self.adapter.prepare({'asset_uri': source})

    def test_server_exposes_only_regular_content_addressed_jpegs(self):
        uri = self.prepare({'asset_uri': str(self.path)})
        self.public.joinpath('private.txt').write_text('secret')
        self.public.joinpath('a' * 64 + '.jpg').symlink_to(self.path)
        server = ThreadingHTTPServer(('127.0.0.1', 0), make_media_handler(self.public))
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            base = f'http://127.0.0.1:{server.server_port}'
            with urllib.request.urlopen(base + '/' + uri.rsplit('/', 1)[1]) as response:
                self.assertEqual(response.headers['Content-Type'], 'image/jpeg')
                self.assertTrue(response.read().startswith(b'\xff\xd8'))
            for path in ['/', '/private.txt', '/../private-persona.png', '/%2e%2e/private-persona.png',
                         '/' + 'a' * 64 + '.jpg']:
                with self.subTest(path=path), self.assertRaises(urllib.error.HTTPError):
                    urllib.request.urlopen(base + path)
        finally:
            server.shutdown()
            server.server_close()
            worker.join()
