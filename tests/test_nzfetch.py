import gzip
import os
import pathlib
import sys
import unittest
import urllib.error
import urllib.request
import zlib
from unittest import mock


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "lib"))

import nzfetch  # noqa: E402


PROXY_ENV_VARS = (
    "FETCH_PROXY",
    "HTTPS_PROXY",
    "https_proxy",
    "PROXY_RETRIES",
)


class FakeResponse:
    def __init__(
        self,
        body=b"ok",
        content_type="text/plain",
        final_url="https://example.test/data",
        content_encoding=None,
    ):
        self._body = body
        self.headers = {"Content-Type": content_type}
        if content_encoding is not None:
            self.headers["Content-Encoding"] = content_encoding
        self._final_url = final_url
        self.read_sizes = []

    def read(self, size=-1):
        self.read_sizes.append(size)
        if size is None or size < 0:
            result, self._body = self._body, b""
            return result
        result, self._body = self._body[:size], self._body[size:]
        return result

    def geturl(self):
        return self._final_url


def http_error(status, retry_after=None):
    headers = {"Retry-After": retry_after} if retry_after is not None else {}
    return urllib.error.HTTPError(
        "https://example.test/data", status, "blocked", headers, None
    )


class NzfetchTests(unittest.TestCase):
    def setUp(self):
        self.saved_environment = {
            name: os.environ[name] for name in PROXY_ENV_VARS if name in os.environ
        }
        for name in PROXY_ENV_VARS:
            os.environ.pop(name, None)

    def tearDown(self):
        for name in PROXY_ENV_VARS:
            os.environ.pop(name, None)
        os.environ.update(self.saved_environment)

    @mock.patch("nzfetch.urllib.request.urlopen")
    def test_direct_success_uses_one_request(self, urlopen):
        urlopen.return_value = FakeResponse(
            body=b"payload",
            content_type="application/octet-stream",
            final_url="https://example.test/final",
        )

        result = nzfetch.fetch_bytes("https://example.test/data")

        self.assertEqual(
            result,
            (b"payload", "application/octet-stream", "https://example.test/final"),
        )
        urlopen.assert_called_once()

    @mock.patch("nzfetch.urllib.request.urlopen")
    def test_wire_response_exactly_at_limit_is_accepted(self, urlopen):
        response = FakeResponse(body=b"12345678")
        urlopen.return_value = response

        with mock.patch.object(nzfetch, "MAX_COMPRESSED_RESPONSE_BYTES", 8):
            body, _content_type, _final_url = nzfetch.fetch_bytes("https://example.test/data")

        self.assertEqual(body, b"12345678")
        self.assertTrue(all(isinstance(size, int) and size > 0 for size in response.read_sizes))

    @mock.patch("nzfetch.urllib.request.urlopen")
    def test_bounded_gzip_and_deflate_responses_are_decoded(self, urlopen):
        for encoding, encoded in (
            ("gzip", gzip.compress(b"decoded")),
            ("deflate", zlib.compress(b"decoded")),
        ):
            with self.subTest(encoding=encoding):
                urlopen.return_value = FakeResponse(body=encoded, content_encoding=encoding)
                body, _content_type, _final_url = nzfetch.fetch_bytes("https://example.test/data")
                self.assertEqual(body, b"decoded")

    @mock.patch("nzfetch.urllib.request.urlopen")
    def test_concatenated_gzip_members_are_decoded(self, urlopen):
        urlopen.return_value = FakeResponse(
            body=gzip.compress(b"first") + gzip.compress(b"second"),
            content_encoding="gzip",
        )

        body, _content_type, _final_url = nzfetch.fetch_bytes("https://example.test/data")

        self.assertEqual(body, b"firstsecond")

    @mock.patch("nzfetch.urllib.request.urlopen")
    def test_concatenated_gzip_member_limit_raises_typed_failure(self, urlopen):
        urlopen.return_value = FakeResponse(
            body=b"".join(gzip.compress(value) for value in (b"one", b"two", b"three")),
            content_encoding="gzip",
        )

        with mock.patch.object(nzfetch, "MAX_GZIP_MEMBERS", 2):
            with self.assertRaisesRegex(nzfetch.ResponseTooLarge, "gzip member limit"):
                nzfetch.fetch_bytes("https://example.test/data")

    @mock.patch("nzfetch.urllib.request.urlopen")
    def test_wire_response_limit_raises_typed_failure_without_unbounded_read(self, urlopen):
        response = FakeResponse(body=b"x" * 9)
        urlopen.return_value = response

        with mock.patch.object(nzfetch, "MAX_COMPRESSED_RESPONSE_BYTES", 8):
            with self.assertRaises(nzfetch.ResponseTooLarge):
                nzfetch.fetch_bytes("https://example.test/data")

        self.assertTrue(response.read_sizes)
        self.assertTrue(all(isinstance(size, int) and size > 0 for size in response.read_sizes))

    @mock.patch("nzfetch.urllib.request.urlopen")
    def test_gzip_decompressed_limit_raises_typed_failure(self, urlopen):
        urlopen.return_value = FakeResponse(
            body=gzip.compress(b"expanded!"),
            content_encoding="gzip",
        )

        with mock.patch.object(nzfetch, "MAX_DECOMPRESSED_RESPONSE_BYTES", 8):
            with self.assertRaises(nzfetch.ResponseTooLarge):
                nzfetch.fetch_bytes("https://example.test/data")

    @mock.patch("nzfetch.urllib.request.urlopen")
    def test_deflate_decompressed_limit_raises_typed_failure(self, urlopen):
        urlopen.return_value = FakeResponse(
            body=zlib.compress(b"expanded!"),
            content_encoding="deflate",
        )

        with mock.patch.object(nzfetch, "MAX_DECOMPRESSED_RESPONSE_BYTES", 8):
            with self.assertRaises(nzfetch.ResponseTooLarge):
                nzfetch.fetch_bytes("https://example.test/data")

    @mock.patch("nzfetch.urllib.request.urlopen")
    def test_blocked_direct_request_without_proxy_raises_blocked(self, urlopen):
        urlopen.side_effect = http_error(403)

        with self.assertRaises(nzfetch.Blocked):
            nzfetch.fetch_bytes("https://example.test/data")

        urlopen.assert_called_once()

    @mock.patch("nzfetch.urllib.request.urlopen")
    def test_direct_timeout_is_unavailable_not_blocked(self, urlopen):
        urlopen.side_effect = TimeoutError("synthetic socket timeout")

        with self.assertRaises(nzfetch.FetchError) as caught:
            nzfetch.fetch_bytes("https://example.test/data")

        self.assertNotIsInstance(caught.exception, nzfetch.Blocked)
        urlopen.assert_called_once()

    @mock.patch("nzfetch.urllib.request.build_opener")
    @mock.patch("nzfetch.urllib.request.urlopen")
    def test_configured_proxy_runs_after_direct_request(self, urlopen, build_opener):
        os.environ["FETCH_PROXY"] = "http://proxy.test:8080"
        os.environ["PROXY_RETRIES"] = "2"
        urlopen.side_effect = http_error(403)
        opener = mock.Mock()
        opener.open.side_effect = [http_error(403), http_error(403)]
        build_opener.return_value = opener

        with self.assertRaises(nzfetch.Blocked):
            nzfetch.fetch_bytes("https://example.test/data")

        urlopen.assert_called_once()
        self.assertEqual(opener.open.call_count, 2)

    @mock.patch("nzfetch.urllib.request.build_opener")
    @mock.patch("nzfetch.urllib.request.urlopen")
    def test_successful_proxy_attempt_returns_normally(self, urlopen, build_opener):
        os.environ["FETCH_PROXY"] = "http://proxy.test:8080"
        urlopen.side_effect = http_error(403)
        opener = mock.Mock()
        opener.open.return_value = FakeResponse(body=b"from proxy")
        build_opener.return_value = opener

        body, content_type, final_url = nzfetch.fetch_bytes(
            "https://example.test/data"
        )

        self.assertEqual(body, b"from proxy")
        self.assertEqual(content_type, "text/plain")
        self.assertEqual(final_url, "https://example.test/data")
        opener.open.assert_called_once()

    @mock.patch("nzfetch.urllib.request.urlopen")
    def test_exhausted_block_statuses_remain_blocked(self, urlopen):
        for status in (403, 406, 451):
            with self.subTest(status=status):
                urlopen.reset_mock()
                urlopen.side_effect = http_error(status)
                with self.assertRaises(nzfetch.Blocked):
                    nzfetch.fetch_bytes("https://example.test/data")
                urlopen.assert_called_once()

    @mock.patch("nzfetch.urllib.request.urlopen")
    def test_http_200_challenge_body_remains_blocked(self, urlopen):
        urlopen.return_value = FakeResponse(
            body=b"<html>Checking your browser - Incapsula</html>",
            content_type="text/html",
        )

        with self.assertRaises(nzfetch.Blocked):
            nzfetch.fetch_bytes("https://example.test/data")

    @mock.patch("nzfetch.urllib.request.urlopen")
    def test_exhausted_429_raises_rate_limited_without_header(self, urlopen):
        urlopen.side_effect = http_error(429)

        with self.assertRaises(nzfetch.RateLimited) as caught:
            nzfetch.fetch_bytes("https://example.test/data")

        self.assertIsInstance(caught.exception, nzfetch.Blocked)
        self.assertIsNone(caught.exception.retry_after)

    @mock.patch("nzfetch.urllib.request.build_opener")
    @mock.patch("nzfetch.urllib.request.urlopen")
    def test_final_proxy_429_preserves_retry_after(self, urlopen, build_opener):
        os.environ["FETCH_PROXY"] = "http://proxy.test:8080"
        os.environ["PROXY_RETRIES"] = "2"
        urlopen.side_effect = http_error(429, "60")
        opener = mock.Mock()
        opener.open.side_effect = [http_error(429, "90"), http_error(429, "120")]
        build_opener.return_value = opener

        with self.assertRaises(nzfetch.RateLimited) as caught:
            nzfetch.fetch_bytes("https://example.test/data")

        self.assertEqual(caught.exception.retry_after, "120")
        self.assertEqual(opener.open.call_count, 2)

    @mock.patch("nzfetch.urllib.request.build_opener")
    @mock.patch("nzfetch.urllib.request.urlopen")
    def test_final_429_without_header_keeps_most_recent_retry_after(
        self, urlopen, build_opener
    ):
        os.environ["FETCH_PROXY"] = "http://proxy.test:8080"
        os.environ["PROXY_RETRIES"] = "1"
        urlopen.side_effect = http_error(429, "60")
        opener = mock.Mock()
        opener.open.side_effect = http_error(429)
        build_opener.return_value = opener

        with self.assertRaises(nzfetch.RateLimited) as caught:
            nzfetch.fetch_bytes("https://example.test/data")

        self.assertEqual(caught.exception.retry_after, "60")

    @mock.patch("nzfetch.urllib.request.build_opener")
    @mock.patch("nzfetch.urllib.request.urlopen")
    def test_final_non_429_status_remains_blocked(self, urlopen, build_opener):
        os.environ["FETCH_PROXY"] = "http://proxy.test:8080"
        os.environ["PROXY_RETRIES"] = "1"
        urlopen.side_effect = http_error(429, "60")
        opener = mock.Mock()
        opener.open.side_effect = http_error(403)
        build_opener.return_value = opener

        with self.assertRaises(nzfetch.Blocked) as caught:
            nzfetch.fetch_bytes("https://example.test/data")

        self.assertNotIsInstance(caught.exception, nzfetch.RateLimited)

    @mock.patch("nzfetch.urllib.request.build_opener")
    @mock.patch("nzfetch.urllib.request.urlopen")
    def test_invalid_proxy_retries_is_actionable(self, urlopen, build_opener):
        os.environ["FETCH_PROXY"] = "http://proxy.test:8080"
        os.environ["PROXY_RETRIES"] = "many"

        with self.assertRaisesRegex(
            nzfetch.FetchError, "PROXY_RETRIES must be an integer"
        ):
            nzfetch.fetch_bytes("https://example.test/data")

        urlopen.assert_not_called()
        build_opener.assert_not_called()

    @mock.patch("nzfetch.urllib.request.build_opener")
    @mock.patch("nzfetch.urllib.request.urlopen")
    def test_negative_proxy_retries_retains_one_proxy_attempt(
        self, urlopen, build_opener
    ):
        os.environ["FETCH_PROXY"] = "http://proxy.test:8080"
        os.environ["PROXY_RETRIES"] = "-4"
        urlopen.side_effect = http_error(403)
        opener = mock.Mock()
        opener.open.side_effect = http_error(403)
        build_opener.return_value = opener

        with self.assertRaises(nzfetch.Blocked):
            nzfetch.fetch_bytes("https://example.test/data")

        opener.open.assert_called_once()

    @mock.patch("nzfetch.urllib.request.build_opener")
    @mock.patch("nzfetch.urllib.request.urlopen")
    def test_blocked_message_does_not_leak_proxy_credentials(
        self, urlopen, build_opener
    ):
        os.environ["FETCH_PROXY"] = "http://user:secret@proxy.test:8080"
        os.environ["PROXY_RETRIES"] = "1"
        urlopen.side_effect = http_error(403)
        opener = mock.Mock()
        opener.open.side_effect = http_error(403)
        build_opener.return_value = opener

        with self.assertRaises(nzfetch.Blocked) as caught:
            nzfetch.fetch_bytes("https://example.test/data")

        message = str(caught.exception)
        self.assertNotIn("user:secret", message)
        self.assertNotIn("proxy.test", message)

    @mock.patch("nzfetch.urllib.request.build_opener")
    def test_allowlist_rejects_initial_undeclared_host_before_network(self, build_opener):
        with self.assertRaisesRegex(nzfetch.FetchError, "declared allowlist"):
            nzfetch.fetch_bytes(
                "https://attacker.example/data",
                allowed_hosts={"example.test"},
            )
        build_opener.assert_not_called()

    def test_allowlist_redirect_handler_rejects_undeclared_host(self):
        handler = nzfetch._AllowlistRedirectHandler(frozenset({"example.test"}))
        with self.assertRaisesRegex(nzfetch.FetchError, "declared allowlist"):
            handler.redirect_request(
                object(), None, 302, "Found", {}, "https://attacker.example/collect"
            )

    def test_allowlist_redirect_handler_strips_credentials_on_origin_change(self):
        handler = nzfetch._AllowlistRedirectHandler(
            frozenset({"example.test", "redirect.example.test"})
        )
        request = urllib.request.Request(
            "https://example.test/data",
            headers={
                "Authorization": "Bearer secret",
                "Proxy-Authorization": "Basic proxy-secret",
                "Cookie": "session=secret",
                "Cookie2": "legacy=secret",
                "X-Request-ID": "safe",
            },
        )

        redirected = handler.redirect_request(
            request,
            None,
            302,
            "Found",
            {},
            "https://redirect.example.test/data",
        )

        self.assertIsNotNone(redirected)
        assert redirected is not None
        for header in ("Authorization", "Proxy-Authorization", "Cookie", "Cookie2"):
            self.assertFalse(redirected.has_header(header))
        self.assertEqual(redirected.get_header("X-request-id"), "safe")

    def test_allowlist_redirect_handler_preserves_credentials_on_same_origin(self):
        handler = nzfetch._AllowlistRedirectHandler(frozenset({"example.test"}))
        request = urllib.request.Request(
            "https://example.test/data",
            headers={"Authorization": "Bearer secret", "Cookie": "session=secret"},
        )

        redirected = handler.redirect_request(
            request, None, 302, "Found", {}, "https://example.test/other"
        )

        self.assertIsNotNone(redirected)
        assert redirected is not None
        self.assertEqual(redirected.get_header("Authorization"), "Bearer secret")
        self.assertEqual(redirected.get_header("Cookie"), "session=secret")

    def test_allowlist_redirect_handler_normalises_default_port_for_same_origin(self):
        handler = nzfetch._AllowlistRedirectHandler(frozenset({"example.test"}))
        request = urllib.request.Request(
            "https://example.test/data",
            headers={"Authorization": "Bearer secret"},
        )

        redirected = handler.redirect_request(
            request, None, 302, "Found", {}, "https://example.test:443/other"
        )

        self.assertIsNotNone(redirected)
        assert redirected is not None
        self.assertEqual(redirected.get_header("Authorization"), "Bearer secret")

    def test_allowlist_redirect_handler_strips_credentials_on_scheme_upgrade(self):
        handler = nzfetch._AllowlistRedirectHandler(frozenset({"example.test"}))
        request = urllib.request.Request(
            "http://example.test/data",
            headers={"Authorization": "Bearer secret"},
        )

        redirected = handler.redirect_request(
            request, None, 302, "Found", {}, "https://example.test/other"
        )

        self.assertIsNotNone(redirected)
        assert redirected is not None
        self.assertFalse(redirected.has_header("Authorization"))

    def test_allowlist_redirect_handler_rejects_https_downgrade(self):
        handler = nzfetch._AllowlistRedirectHandler(frozenset({"example.test"}))
        request = urllib.request.Request(
            "https://example.test/data",
            headers={"Authorization": "Bearer secret"},
        )

        with self.assertRaisesRegex(nzfetch.FetchError, "HTTPS redirect downgrade"):
            handler.redirect_request(
                request, None, 302, "Found", {}, "http://example.test/collect"
            )

    @mock.patch("nzfetch.urllib.request.build_opener")
    def test_allowlisted_request_accepts_exact_host(self, build_opener):
        opener = mock.Mock()
        opener.open.return_value = FakeResponse(body=b"safe")
        build_opener.return_value = opener

        body, _content_type, final_url = nzfetch.fetch_bytes(
            "https://example.test/data",
            allowed_hosts={"example.test"},
        )

        self.assertEqual(body, b"safe")
        self.assertEqual(final_url, "https://example.test/data")
        opener.open.assert_called_once()

    @mock.patch("nzfetch.urllib.request.build_opener")
    def test_allowlisted_request_rejects_escaped_final_url(self, build_opener):
        opener = mock.Mock()
        opener.open.return_value = FakeResponse(final_url="https://attacker.example/collect")
        build_opener.return_value = opener

        with self.assertRaisesRegex(nzfetch.FetchError, "declared allowlist"):
            nzfetch.fetch_bytes(
                "https://example.test/data",
                allowed_hosts={"example.test"},
            )


if __name__ == "__main__":
    unittest.main()
