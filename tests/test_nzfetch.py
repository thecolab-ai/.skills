import os
import pathlib
import sys
import unittest
import urllib.error
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
    ):
        self._body = body
        self.headers = {"Content-Type": content_type}
        self._final_url = final_url

    def read(self):
        return self._body

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
    def test_blocked_direct_request_without_proxy_raises_blocked(self, urlopen):
        urlopen.side_effect = http_error(403)

        with self.assertRaises(nzfetch.Blocked):
            nzfetch.fetch_bytes("https://example.test/data")

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


if __name__ == "__main__":
    unittest.main()
