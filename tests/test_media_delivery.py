import base64
import hashlib
import io
import os
import tempfile
import unittest
import urllib.error
import urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from PIL import Image

from spicecore.media_delivery import AzureMediaDelivery, MediaDelivery


class _Response:
    def __init__(self, status, headers=None):
        self.status = status
        self.headers = headers or {}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class MediaDeliveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "private-persona.png"
        Image.new("RGBA", (32, 48), (12, 70, 150, 180)).save(self.path)
        self.now = datetime.now(timezone.utc)
        self.upload = self.sas("cw", "upload-secret")
        self.read = self.sas("r", "read-secret")
        self.opener = mock.Mock()
        self.opener_patch = mock.patch(
            "spicecore.media_delivery.urllib.request.build_opener",
            return_value=self.opener,
        )
        self.opener_patch.start()
        self.addCleanup(self.opener_patch.stop)

    def sas(self, permissions, signature, **overrides):
        fields = {
            "sv": "2023-11-03",
            "sr": "c",
            "sp": permissions,
            "se": (self.now + timedelta(days=1)).isoformat(),
            "spr": "https",
            "sig": signature,
        }
        fields.update(overrides)
        return "https://spicemedia.blob.core.windows.net/media?" + urllib.parse.urlencode(fields)

    def adapter(self):
        return AzureMediaDelivery(self.upload, self.read)

    def successful_requests(self):
        def respond(request, *, timeout):
            if request.get_method() == "PUT":
                self.payload = request.data
                return _Response(201)
            return _Response(200, {
                "Content-Type": "image/jpeg",
                "Content-Length": str(len(self.payload)),
                "Content-MD5": base64.b64encode(
                    hashlib.md5(self.payload, usedforsecurity=False).digest()
                ).decode("ascii"),
            })

        self.opener.open.side_effect = respond

    def test_from_env_names_missing_credentials_without_exposing_values(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ValueError) as raised:
                AzureMediaDelivery.from_env()
        self.assertIn("AZURE_MEDIA_UPLOAD_CONTAINER_SAS_URL", str(raised.exception))
        self.assertIn("AZURE_MEDIA_READ_CONTAINER_SAS_URL", str(raised.exception))
        self.opener.open.assert_not_called()

    def test_from_env_and_alias_share_the_contract(self):
        with mock.patch.dict(os.environ, {
            "AZURE_MEDIA_UPLOAD_CONTAINER_SAS_URL": self.upload,
            "AZURE_MEDIA_READ_CONTAINER_SAS_URL": self.read,
        }, clear=True):
            adapter = MediaDelivery.from_env()
        self.assertIsInstance(adapter, AzureMediaDelivery)
        self.assertTrue(adapter.readiness()["ready"])
        self.assertNotIn("secret", str(adapter.readiness()))
        self.opener.open.assert_not_called()

    def test_uploads_real_jpeg_then_verifies_the_separate_read_url(self):
        self.successful_requests()
        uri = self.adapter().prepare({"asset_uri": str(self.path), "channel": "instagram"})
        calls = self.opener.open.call_args_list
        self.assertEqual(len(calls), 2)
        upload_request, read_request = [call.args[0] for call in calls]
        self.assertEqual(upload_request.get_method(), "PUT")
        self.assertEqual(read_request.get_method(), "HEAD")
        self.assertEqual(upload_request.get_header("X-ms-blob-type"), "BlockBlob")
        self.assertEqual(upload_request.get_header("Content-type"), "image/jpeg")
        self.assertEqual(int(upload_request.get_header("Content-length")), len(self.payload))
        self.assertEqual(upload_request.get_header("If-none-match"), "*")
        self.assertTrue(all(0 < call.kwargs["timeout"] <= 60 for call in calls))
        with Image.open(io.BytesIO(self.payload)) as converted:
            self.assertEqual(converted.format, "JPEG")
            self.assertEqual(converted.mode, "RGB")
            self.assertEqual(converted.size, (32, 48))
        expected_key = "/media/media/" + hashlib.sha256(self.payload).hexdigest() + ".jpg"
        self.assertEqual(urllib.parse.urlsplit(uri).path, expected_key)
        upload_fields = urllib.parse.parse_qs(urllib.parse.urlsplit(upload_request.full_url).query)
        read_fields = urllib.parse.parse_qs(urllib.parse.urlsplit(uri).query)
        self.assertEqual(upload_fields["sig"], ["upload-secret"])
        self.assertEqual(read_fields["sp"], ["r"])
        self.assertEqual(read_fields["sig"], ["read-secret"])
        self.assertNotIn("upload-secret", uri)
        self.assertEqual(read_request.full_url, uri)

    def test_object_key_depends_on_bytes_instead_of_persona_or_path(self):
        self.successful_requests()
        adapter = self.adapter()
        first = adapter.prepare({"id": "first-private-persona", "asset_uri": str(self.path)})
        other = Path(self.temp.name) / "other.png"
        other.write_bytes(self.path.read_bytes())
        second = adapter.prepare({"id": "second-private-persona", "asset_uri": str(other)})
        self.assertEqual(first, second)
        self.assertNotIn("persona", urllib.parse.urlsplit(first).path)

    def test_explicit_public_https_uri_is_unchanged(self):
        uri = "https://cdn.example.com/approved-media/photo.jpg?version=2"
        self.assertEqual(self.adapter().prepare({"asset_uri": uri}), uri)
        self.assertEqual(self.adapter().prepare({"media_uri": uri, "asset_uri": "missing"}), uri)
        self.opener.open.assert_not_called()

    def test_explicit_azure_uri_cannot_forward_writable_or_expired_sas(self):
        for sas in (
            self.upload,
            self.sas("r", "read-secret", se=(self.now - timedelta(seconds=1)).isoformat()),
            self.sas("r", "read-secret", si="unverified-policy"),
        ):
            uri = sas.replace("/media?", "/media/ready.jpg?")
            with self.subTest(uri=uri.split("?")[0]):
                with self.assertRaises(ValueError) as raised:
                    self.adapter().prepare({"media_uri": uri})
                self.assertNotIn("secret", str(raised.exception))
        valid = self.read.replace("/media?", "/media/ready.jpg?")
        self.assertEqual(self.adapter().prepare({"media_uri": valid}), valid)
        self.opener.open.assert_not_called()

    def test_rejects_invalid_sas_scopes_permissions_and_expiry_without_network(self):
        bad_pairs = [
            (self.upload.replace("https://", "http://"), self.read),
            (self.upload, self.read.replace("spicemedia.", "different.")),
            (self.upload, self.read.replace("/media?", "/other?")),
            (self.upload, self.read.replace("/media?", "/media/blob?")),
            (self.upload, self.read.replace("blob.core.windows.net", "blob.core.windows.net.evil.test")),
            (self.upload, self.read.replace("https://", "https://user:password@")),
            (self.sas("r", "upload-secret"), self.read),
            (self.upload, self.sas("rw", "read-secret")),
            (self.upload, self.sas("rl", "read-secret")),
            (self.upload, self.sas("r", "read-secret", sr="b")),
            (self.upload, self.sas("r", "read-secret", si="unknown-policy")),
            (self.upload, self.sas("r", "read-secret", sig="")),
            (self.upload, self.sas("r", "read-secret", se="not-a-date")),
            (self.upload, self.sas("r", "read-secret", se=(self.now - timedelta(seconds=1)).isoformat())),
            (self.upload, self.sas("r", "read-secret", st=(self.now + timedelta(hours=1)).isoformat())),
            (self.upload, self.read + "&sp=rw"),
        ]
        for upload, read in bad_pairs:
            with self.subTest(upload=upload.split("?")[0], read=read.split("?")[0]):
                with self.assertRaises(ValueError) as raised:
                    AzureMediaDelivery(upload, read)
                self.assertNotIn("secret", str(raised.exception))
        self.opener.open.assert_not_called()

    def test_create_only_upload_permission_is_supported(self):
        self.successful_requests()
        uri = AzureMediaDelivery(self.sas("c", "upload-secret"), self.read).prepare(
            {"asset_uri": str(self.path)}
        )
        self.assertTrue(uri.startswith("https://spicemedia.blob.core.windows.net/"))

    def test_rechecks_read_expiry_before_upload_and_reports_safe_readiness(self):
        adapter = self.adapter()
        with mock.patch("spicecore.media_delivery._utcnow", return_value=self.now + timedelta(days=2)):
            self.assertFalse(adapter.readiness()["ready"])
            with self.assertRaisesRegex(ValueError, "expired"):
                adapter.prepare({"asset_uri": str(self.path)})
        self.opener.open.assert_not_called()

    def test_rejects_missing_and_nonimage_local_files_before_upload(self):
        invalid = Path(self.temp.name) / "fake.png"
        invalid.write_bytes(b"not image bytes")
        for source in (str(invalid), str(invalid) + ".missing", "http://cdn.example.com/a.jpg", "data:image/png;base64,abc"):
            with self.subTest(source=source):
                with self.assertRaises(ValueError):
                    self.adapter().prepare({"asset_uri": source})
        self.opener.open.assert_not_called()

    def test_never_returns_an_unreadable_blob(self):
        self.opener.open.side_effect = [
            _Response(201),
            urllib.error.HTTPError(self.read, 403, "read-secret", {}, None),
        ]
        with self.assertRaisesRegex(RuntimeError, "403") as raised:
            self.adapter().prepare({"asset_uri": str(self.path)})
        self.assertNotIn("secret", str(raised.exception))

    def test_rejects_read_response_with_wrong_content(self):
        self.opener.open.side_effect = [
            _Response(201),
            _Response(200, {"Content-Type": "text/plain", "Content-Length": "1"}),
        ]
        with self.assertRaises(RuntimeError):
            self.adapter().prepare({"asset_uri": str(self.path)})

    def test_existing_blob_must_match_the_uploaded_digest(self):
        def respond(request, *, timeout):
            if request.get_method() == "PUT":
                self.payload = request.data
                return _Response(201)
            return _Response(200, {
                "Content-Type": "image/jpeg",
                "Content-Length": str(len(self.payload)),
                "Content-MD5": "wrong-digest",
            })
        self.opener.open.side_effect = respond
        with self.assertRaisesRegex(RuntimeError, "did not match"):
            self.adapter().prepare({"asset_uri": str(self.path)})

    def test_signed_requests_have_redirects_disabled(self):
        from spicecore.media_delivery import _RejectRedirects

        self.assertIsNone(_RejectRedirects().redirect_request(
            mock.Mock(), None, 307, "redirect", {}, "https://other.example.com/"
        ))

    def test_existing_immutable_blob_is_verified_on_retry(self):
        def respond(request, *, timeout):
            if request.get_method() == "PUT":
                self.payload = request.data
                raise urllib.error.HTTPError(request.full_url, 412, "upload-secret", {}, None)
            return _Response(200, {
                "Content-Type": "image/jpeg",
                "Content-Length": str(len(self.payload)),
                "Content-MD5": base64.b64encode(
                    hashlib.md5(self.payload, usedforsecurity=False).digest()
                ).decode("ascii"),
            })
        self.opener.open.side_effect = respond
        self.assertIn(".jpg?", self.adapter().prepare({"asset_uri": str(self.path)}))

    def test_network_exception_text_and_urls_are_not_exposed(self):
        self.opener.open.side_effect = urllib.error.URLError(self.upload + " read-secret")
        with self.assertRaises(RuntimeError) as raised:
            self.adapter().prepare({"asset_uri": str(self.path)})
        self.assertNotIn("secret", str(raised.exception))
        self.assertNotIn("https://", str(raised.exception))
        self.assertTrue(raised.exception.__suppress_context__)


if __name__ == "__main__":
    unittest.main()
