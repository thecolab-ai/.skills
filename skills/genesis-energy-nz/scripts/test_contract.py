#!/usr/bin/env python3
"""Offline contracts and synthetic behavioural tests. No account or network access."""
from __future__ import annotations

import contextlib
import copy
import http.cookiejar
import io
import json
import subprocess
import sys
import unittest
import urllib.error
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "lib"))
from contract_test import audit_skill
import cli
from genesis import AUTH, DATA, REDIRECT, Client, GenesisError, NoRedirect, Transport, object_json, MAX_BODY
from usage import HOUR, NZ, coverage, date_range, fetch_usage, midnight, normalise, records

FIXTURES = Path(__file__).resolve().parents[1] / "tests" / "fixtures"
NOW = datetime(2024, 2, 1, tzinfo=timezone.utc)
DAY = date(2024, 1, 1)


def sample():
    return json.loads((FIXTURES / "source-sample.json").read_text())["response"]


class QueueTransport:
    def __init__(self, responses):
        self.responses, self.calls = list(responses), []
        self.cookies = http.cookiejar.CookieJar()
        self.cookies.set_cookie(http.cookiejar.Cookie(
            0, "x-ms-cpim-csrf", "synthetic-csrf", None, False,
            "auth.genesisenergy.co.nz", False, False, "/", True, True,
            None, True, None, None, {}, False,
        ))

    def request(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        if not self.responses:
            raise AssertionError("Unexpected request")
        return self.responses.pop(0)


def login_responses():
    return [
        (200, 'var SETTINGS = {"transId":"synthetic-tx","csrf":"synthetic-csrf"};', {}),
        (200, '{"status":"200"}', {}), (200, "synthetic password page", {}),
        (200, '{"status":"200"}', {}),
        (302, "", {"Location": REDIRECT + "?code=synthetic-code"}),
        (200, '{"access_token":"synthetic-access","refresh_token":"synthetic-discarded"}', {}),
    ]


class SourceTests(unittest.TestCase):
    def test_fixture_is_synthetic_and_field_selection_deduplicates(self):
        fixture = json.loads((FIXTURES / "source-sample.json").read_text())
        self.assertFalse(fixture["contains_live_credentials"])
        self.assertFalse(fixture["contains_personal_data"])
        rows = normalise(sample(), DAY, DAY, NOW)
        result = records(dict(sorted(rows.items())), DAY, DAY, "usage")
        self.assertEqual(len(result), 2)
        self.assertEqual(set(result[0]), {"interval_start", "usage_kwh", "usage_cost_nzd"})
        self.assertNotIn("synthetic-ignored-marker", json.dumps(result))
        report = coverage(rows, DAY, DAY)
        self.assertEqual(report["observed_usage_kwh"], "0.30")
        self.assertEqual(report["observed_usage_cost_nzd"], "0.09")
        self.assertEqual(report["coverage"], "incomplete")
        self.assertEqual(report["missing_intervals"], 22)

    def test_invalid_conflicting_naive_out_of_range_capped_rows(self):
        malformed = [{}, {"usage": None}, {"usage": [{}]}, {"usage": sample()["usage"] * 34}]
        for field, value in (("kw", "NaN"), ("kw", True), ("kw", "1e100"),
                             ("costNZD", None), ("costNZD", "0.0000000000001"),
                             ("startDate", "2024-01-01T00:00:00"),
                             ("startDate", "2024-01-01T00:01:00+13:00"),
                             ("startDate", "2024-01-02T00:00:00+13:00")):
            data = sample()
            data["usage"][0][field] = value
            malformed.append(data)
        conflict = sample()
        conflict["usage"][2]["kw"] = "1"
        malformed.append(conflict)
        for data in malformed:
            with self.subTest(data=data), self.assertRaises(GenesisError) as raised:
                normalise(data, DAY, DAY, NOW)
            self.assertEqual(raised.exception.code, 6)

    def test_dst_23_and_25_hour_days_and_repeated_labels(self):
        for day, hours in ((date(2024, 4, 7), 25), (date(2024, 9, 29), 23)):
            stamps = [midnight(day) + i * HOUR for i in range(hours)]
            rows = {stamp: (Decimal("0.1"), Decimal("0.03")) for stamp in stamps}
            report = coverage(rows, day, day)
            self.assertEqual(report["expected_intervals"], hours)
            self.assertEqual(report["coverage"], "complete")
            self.assertEqual(Decimal(report["observed_usage_kwh"]), Decimal("0.1") * hours)
            output = records(rows, day, day, "usage")
            self.assertEqual(len({row["interval_start"] for row in output}), hours)

    def test_empty_lag_and_unfinished_hours_are_not_zero(self):
        empty = coverage({}, DAY, DAY)
        self.assertIsNone(empty["observed_usage_kwh"])
        self.assertIsNone(empty["observed_usage_cost_nzd"])
        self.assertEqual(empty["coverage"], "no_readings")
        now = midnight(DAY) + HOUR
        rows = normalise(sample(), DAY, DAY, now)
        self.assertEqual(len(rows), 1)
        self.assertEqual(coverage(rows, DAY, DAY)["missing_intervals"], 23)
        daily = records({}, DAY, DAY + timedelta(days=1), "summary")
        self.assertEqual(len(daily), 2)
        self.assertTrue(all(row["coverage"] == "no_readings" for row in daily))

    def test_two_date_chunks_31_day_bound_and_pause(self):
        client, pause = Mock(), Mock()
        client.electricity.return_value = {"usage": []}
        start, end = date_range("2024-01-01", "2024-01-31", date(2024, 2, 1))
        self.assertEqual(fetch_usage(client, start, end, NOW, pause), {})
        self.assertEqual(client.electricity.call_count, 16)
        self.assertEqual(pause.call_count, 15)
        self.assertEqual(client.electricity.call_args_list[0].args, (DAY, DAY + timedelta(days=1)))
        self.assertEqual(client.electricity.call_args_list[-1].args, (end, end))
        for a, b in (("2024-01-01", "2024-02-01"), ("2024-01-02", "2024-01-01"),
                     ("20240101", "2024-01-01"), ("2024-01-01", "2025-01-01")):
            with self.assertRaises(GenesisError) as raised:
                date_range(a, b, date(2024, 2, 1))
            self.assertEqual(raised.exception.code, 2)

    def test_login_posts_credentials_and_code_without_visiting_callback(self):
        transport = QueueTransport(login_responses())
        client = Client(transport)
        client.authenticate("fixture-user@example.invalid", "synthetic-password")
        self.assertEqual(client.token, "synthetic-access")
        self.assertFalse(hasattr(client, "refresh_token"))
        self.assertEqual(len(transport.calls), 6)
        for method, url, kwargs in transport.calls:
            self.assertTrue(url.startswith(AUTH + "/"))
            self.assertNotIn("synthetic-password", url)
            self.assertNotIn("synthetic-code", url)
            if "password" in kwargs.get("form", {}):
                self.assertEqual(method, "POST")
        self.assertEqual(transport.calls[-1][2]["form"]["code"], "synthetic-code")
        self.assertEqual(transport.calls[3][2]["headers"]["X-CSRF-TOKEN"], "synthetic-csrf")
        transport.responses.append((200, json.dumps(sample()), {}))
        self.assertEqual(client.electricity(DAY, DAY), sample())
        self.assertEqual(transport.calls[-1][1], DATA)
        self.assertEqual(transport.calls[-1][2]["headers"], {"Authorization": "Bearer synthetic-access"})

    def test_auth_redirect_and_callback_cannot_exfiltrate(self):
        for location in ("https://outside.invalid/?code=synthetic-code", "http://auth.genesisenergy.co.nz/", REDIRECT + "/wrong?code=synthetic-code"):
            responses = login_responses()
            responses[4] = (302, "", {"Location": location})
            transport = QueueTransport(responses)
            with self.assertRaises(GenesisError):
                Client(transport).authenticate("fixture-user@example.invalid", "synthetic-password")
            self.assertEqual(len(transport.calls), 5)
        transport = QueueTransport([(302, "", {"Location": "https://outside.invalid/"})])
        with self.assertRaises(GenesisError):
            Client(transport).navigate(AUTH)
        self.assertEqual(len(transport.calls), 1)

    def test_path_scoped_csrf_cookie_is_looked_up_at_password_endpoint(self):
        transport = QueueTransport(login_responses())
        cookie = next(iter(transport.cookies))
        transport.cookies.clear()
        cookie.path = "/auth.genesisenergy.co.nz/B2C_1A_signin/"
        transport.cookies.set_cookie(cookie)
        client = Client(transport)
        client.authenticate("fixture-user@example.invalid", "synthetic-password")
        self.assertEqual(client.token, "synthetic-access")
        self.assertEqual(transport.calls[3][2]["headers"]["X-CSRF-TOKEN"], "synthetic-csrf")

    def test_bad_login_schema_rejected_login_and_missing_csrf_are_safe(self):
        for changed in ("no settings", "var SETTINGS = [];", "var SETTINGS = null;"):
            responses = login_responses()
            responses[0] = (200, changed, {})
            with self.assertRaises(GenesisError):
                Client(QueueTransport(responses)).authenticate("fixture-user@example.invalid", "synthetic-password")
        responses = login_responses()
        responses[3] = (200, '{"status":"400","message":"synthetic-password"}', {})
        with self.assertRaises(GenesisError) as raised:
            Client(QueueTransport(responses)).authenticate("fixture-user@example.invalid", "synthetic-password")
        self.assertNotIn("synthetic-password", str(raised.exception))
        transport = QueueTransport(login_responses())
        transport.cookies.clear()
        with self.assertRaises(GenesisError):
            Client(transport).authenticate("fixture-user@example.invalid", "synthetic-password")

    def test_transport_size_rate_limit_destinations_and_static_failures(self):
        transport = Transport()
        self.assertIsNone(NoRedirect().redirect_request(None, None, 302, "", {}, DATA))
        with self.assertRaises(GenesisError):
            transport.request("POST", "https://outside.invalid/", form={"password": "synthetic-password"})
        for status, header, expected in ((429, "60", "60"), (429, "synthetic-private-header", None), (403, None, None)):
            response = urllib.error.HTTPError(DATA, status, "synthetic-private-message", {"Retry-After": header} if header else {}, io.BytesIO(b"synthetic-private-body"))
            with patch.object(transport.opener, "open", side_effect=response):
                with self.assertRaises(GenesisError) as raised:
                    transport.request("POST", DATA)
            self.assertEqual(raised.exception.code, 4)
            self.assertEqual(raised.exception.retry_after, expected)
            self.assertNotIn("synthetic-private", str(raised.exception))
        response = urllib.error.HTTPError(DATA, 200, "", {}, io.BytesIO(b"x" * (MAX_BODY + 1)))
        with patch.object(transport.opener, "open", return_value=response):
            with self.assertRaises(GenesisError) as raised:
                transport.request("POST", DATA)
        self.assertEqual(raised.exception.code, 6)
        with patch.object(transport.opener, "open", side_effect=OSError("synthetic-private-error")):
            with self.assertRaises(GenesisError) as raised:
                transport.request("POST", DATA)
        self.assertEqual(str(raised.exception), "Cannot read Genesis response")
        with self.assertRaises(GenesisError):
            object_json("[]")

    def invoke(self, args, factory=None, environment=None):
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch.dict("os.environ", environment or {}, clear=True), patch.object(cli, "Client", factory or Mock()) as client_factory:
            with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
                code = cli.main(args)
        return code, stdout.getvalue(), stderr.getvalue(), client_factory

    def test_cli_missing_credentials_invalid_input_do_not_touch_network(self):
        for args, expected in ((["usage", "--start", "2024-01-01", "--end", "2024-01-01", "--json"], 3),
                               (["--thecolab-invalid-option", "synthetic-password", "--json"], 2),
                               (["usage", "--start", "bad", "--end", "2024-01-01", "--json"], 2)):
            code, out, err, factory = self.invoke(args)
            self.assertEqual(code, expected)
            factory.assert_not_called()
            self.assertFalse(err)
            self.assertNotIn("synthetic-password", out)
            result = json.loads(out)
            self.assertEqual(result["error"]["code"], expected)
            self.assertEqual(result["results"], [])
            self.assertTrue(result["meta"]["retrieved_at"].endswith("Z"))

    def test_cli_success_field_selection_and_partial_failure_sanitised(self):
        factory = Mock()
        factory.return_value.electricity.return_value = sample()
        env = {"GENESIS_EMAIL": "fixture-user@example.invalid", "GENESIS_PASSWORD": "synthetic-password"}
        args = ["summary", "--start", "2024-01-01", "--end", "2024-01-01", "--group", "range", "--json"]
        code, out, err, _ = self.invoke(args, factory, env)
        self.assertEqual(code, 0)
        self.assertFalse(err)
        self.assertEqual(json.loads(out)["results"][0]["observed_usage_cost_nzd"], "0.09")
        for marker in (*env.values(), "synthetic-ignored-marker", "access_token"):
            self.assertNotIn(marker, out)
        factory.return_value.electricity.side_effect = [sample(), GenesisError(5, "Genesis electricity request failed")]
        args[4] = "2024-01-03"
        code, out, err, _ = self.invoke(args, factory, env)
        self.assertEqual(code, 5)
        self.assertEqual(json.loads(out)["results"], [])
        factory.return_value.authenticate.side_effect = RuntimeError("synthetic-password")
        code, out, err, _ = self.invoke(args, factory, env)
        self.assertEqual(code, 6)
        self.assertNotIn("synthetic-password", out + err)
        self.assertNotIn("Traceback", out + err)


def main():
    # Fail any accidental real network attempt, regardless of ambient credentials.
    with patch("socket.create_connection", side_effect=AssertionError("Network forbidden in offline tests")):
        suite = unittest.defaultTestLoader.loadTestsFromTestCase(SourceTests)
        result = unittest.TextTestRunner(stream=sys.stderr, verbosity=1).run(suite)
        audit = audit_skill(Path(__file__).resolve().parents[1])
    audit["ok"] = audit["ok"] and result.wasSuccessful()
    audit["checks"].append("synthetic_behaviour")
    audit["skips"] = ["live account verification intentionally gated"]
    audit["live_assertions"] = 0
    print(json.dumps(audit, indent=2))
    return 0 if audit["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
