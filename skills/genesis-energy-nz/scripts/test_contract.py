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
from urllib.parse import parse_qs, urlencode, urlsplit
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "lib"))
from contract_test import audit_skill
import cli
from genesis import AUTH, DATA, GAS_DATA, REDIRECT, Client, GenesisError, NoRedirect, Transport, object_json, MAX_BODY
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
        self.assertEqual(fetch_usage(client, start, end, NOW, pause), ({}, None))
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
        factory.return_value.gas.assert_not_called()
        self.assertEqual(json.loads(out)["meta"]["fuel"], "electricity")
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


    def test_optional_gas_selects_only_gas_and_identifies_output(self):
        fixture = json.loads((FIXTURES / "gas-sample.json").read_text())
        self.assertFalse(fixture["contains_live_credentials"])
        self.assertFalse(fixture["contains_personal_data"])
        for command in ("usage", "summary"):
            factory = Mock()
            factory.return_value.gas.return_value = fixture["response"]
            env = {"GENESIS_EMAIL": "fixture-user@example.invalid", "GENESIS_PASSWORD": "synthetic-password"}
            args = [command, "--fuel", "gas", "--start", "2024-01-01", "--end", "2024-01-01", "--json"]
            code, out, err, _ = self.invoke(args, factory, env)
            self.assertEqual(code, 0)
            self.assertFalse(err)
            factory.return_value.electricity.assert_not_called()
            factory.return_value.gas.assert_called_once_with(DAY, DAY)
            result = json.loads(out)
            self.assertEqual(result["meta"]["fuel"], "gas")
            self.assertEqual(result["meta"]["source_url"], GAS_DATA)
            self.assertEqual(result["meta"]["observed_usage_cost_nzd"], "0.45")
            self.assertEqual(result["meta"]["missing_intervals"], 22)
            for value in (*env.values(), "synthetic-gas-ignored-marker", "access_token"):
                self.assertNotIn(value, out + err)

    def test_gas_uses_fixed_get_endpoint_and_date_query_without_body(self):
        fixture = json.loads((FIXTURES / "gas-sample.json").read_text())["response"]
        transport = QueueTransport([(200, json.dumps(fixture), {})])
        client = Client(transport)
        client.token = "synthetic-access"
        self.assertEqual(client.gas(DAY, DAY), fixture)
        method, url, kwargs = transport.calls[0]
        self.assertEqual(method, "GET")
        parsed = urlsplit(url)
        self.assertEqual(url.split("?")[0], GAS_DATA)
        self.assertEqual(parse_qs(parsed.query), {"startDate": ["2024-01-01"], "endDate": ["2024-01-01"], "intervalType": ["HOURLY"]})
        self.assertEqual(kwargs, {"headers": {"Authorization": "Bearer synthetic-access"}})
        real_transport = Transport()
        response = urllib.error.HTTPError(url, 200, "", {}, io.BytesIO(json.dumps(fixture).encode()))
        with patch.object(real_transport.opener, "open", return_value=response) as opened:
            self.assertEqual(object_json(real_transport.request(method, url, **kwargs)[1]), fixture)
        request = opened.call_args.args[0]
        self.assertEqual(request.get_method(), "GET")
        self.assertIsNone(request.data)
        self.assertEqual(request.get_header("Authorization"), "Bearer synthetic-access")
        self.assertNotIn("synthetic-access", request.full_url)
        with patch.object(real_transport.opener, "open") as opened:
            for invalid_url in (GAS_DATA + "/extra?" + parsed.query, url + "&token=synthetic-access", url + "&startDate=2024-01-01", url + "#fragment"):
                with self.assertRaises(GenesisError):
                    real_transport.request("GET", invalid_url)
            with self.assertRaises(GenesisError):
                real_transport.request("POST", url)
            opened.assert_not_called()

    def test_gas_unavailable_is_a_safe_error_and_does_not_affect_electricity(self):
        url = GAS_DATA + "?" + urlencode({"startDate": "2024-01-01", "endDate": "2024-01-01", "intervalType": "HOURLY"})
        env = {"GENESIS_EMAIL": "fixture-user@example.invalid", "GENESIS_PASSWORD": "synthetic-password"}
        for status in (400, 404, 422):
            transport = Transport()
            response = urllib.error.HTTPError(url, status, "synthetic-private-message", {}, io.BytesIO(b"synthetic-private-body"))
            with patch.object(transport.opener, "open", side_effect=response) as opened:
                with self.assertRaises(GenesisError) as raised:
                    transport.request("GET", url)
                opened.assert_called_once()
            self.assertEqual(raised.exception.code, 7)
            self.assertNotIn("synthetic-private", str(raised.exception))
            factory = Mock()
            factory.return_value.gas.side_effect = raised.exception
            factory.return_value.electricity.return_value = sample()
            args = ["summary", "--start", "2024-01-01", "--end", "2024-01-01", "--json"]
            code, out, err, _ = self.invoke([*args, "--fuel", "gas"], factory, env)
            self.assertEqual(code, 7)
            result = json.loads(out)
            self.assertEqual(result["error"]["type"], "unsupported_operation")
            self.assertEqual(result["results"], [])
            self.assertEqual(result["meta"]["fuel"], "gas")
            self.assertNotIn("observed_usage_cost_nzd", result["meta"])
            code, out, err, _ = self.invoke(args, factory, env)
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(out)["meta"]["fuel"], "electricity")
            self.assertEqual(factory.return_value.gas.call_count, 1)

    def test_empty_gas_never_becomes_zero(self):
        factory = Mock()
        factory.return_value.gas.return_value = {"usage": []}
        env = {"GENESIS_EMAIL": "fixture-user@example.invalid", "GENESIS_PASSWORD": "synthetic-password"}
        args = ["summary", "--fuel", "gas", "--start", "2024-01-01", "--end", "2024-01-01", "--json"]
        code, out, err, _ = self.invoke(args, factory, env)
        self.assertEqual(code, 0)
        result = json.loads(out)
        report = result["results"][0]
        self.assertEqual(report["coverage"], "no_readings")
        self.assertIsNone(report["observed_usage_kwh"])
        self.assertIsNone(report["observed_usage_cost_nzd"])
        self.assertNotIn("provider_unavailable_from", result["meta"])

    GAS_UNAVAILABLE = "Gas usage is unavailable for this account or date range; try earlier dates or check gas service"
    ENV = {"GENESIS_EMAIL": "fixture-user@example.invalid", "GENESIS_PASSWORD": "synthetic-password"}

    def invoke_gas(self, command, side_effect, end="2024-01-05", extra=()):
        """Five days = chunks starting 1, 3 and 5 Jan; returns parsed output and mocks."""
        factory = Mock()
        factory.return_value.gas.side_effect = side_effect
        args = [command, "--fuel", "gas", "--start", "2024-01-01", "--end", end, *extra]
        with patch.object(cli.time, "sleep") as sleep:
            code, out, err, _ = self.invoke(args, factory, self.ENV)
        return code, out, err, factory.return_value, sleep

    def test_later_gas_rejection_keeps_verified_rows_as_incomplete(self):
        fixture = json.loads((FIXTURES / "gas-sample.json").read_text())["response"]
        rejection = GenesisError(7, self.GAS_UNAVAILABLE)
        code, out, err, client, sleep = self.invoke_gas(
            "summary", [fixture, rejection, AssertionError("read after rejection")],
            extra=("--group", "range", "--json"))
        self.assertEqual(code, 0)
        self.assertFalse(err)
        self.assertEqual(client.gas.call_args_list, [((DAY, date(2024, 1, 2)),), ((date(2024, 1, 3), date(2024, 1, 4)),)])
        self.assertEqual(sleep.call_count, 1)
        client.electricity.assert_not_called()
        result = json.loads(out)
        self.assertNotIn("error", result)
        meta = result["meta"]
        self.assertEqual(meta["provider_unavailable_from"], "2024-01-03")
        self.assertEqual(meta["coverage"], "incomplete")
        self.assertEqual((meta["expected_intervals"], meta["received_intervals"], meta["missing_intervals"]), (120, 2, 118))
        self.assertEqual((meta["observed_usage_kwh"], meta["observed_usage_cost_nzd"]), ("5.0", "0.45"))
        self.assertEqual(meta["latest_data"], "2024-01-01T01:00:00+13:00")
        self.assertEqual(meta["usage_unit"], "kWh")
        self.assertEqual(meta["usage_unit_status"], "assumed_unverified")
        self.assertIn("interpreted as interval kWh", meta["unit_basis"])
        self.assertEqual(result["results"], [{k: meta[k] for k in result["results"][0]}])
        # Daily summary: rejected and later days stay missing, never zero.
        code, out, _, client, _ = self.invoke_gas("summary", [fixture, rejection], extra=("--json",))
        self.assertEqual(code, 0)
        daily = json.loads(out)["results"]
        self.assertEqual([day["coverage"] for day in daily], ["incomplete"] + ["no_readings"] * 4)
        self.assertTrue(all(day["observed_usage_kwh"] is None and day["observed_usage_cost_nzd"] is None for day in daily[1:]))
        # Hourly usage returns only the verified rows; text mode names the cut-off.
        code, out, _, _, _ = self.invoke_gas("usage", [fixture, rejection], extra=("--json",))
        self.assertEqual(code, 0)
        self.assertEqual([row["usage_kwh"] for row in json.loads(out)["results"]], ["2.0", "3.0"])
        code, out, err, _, _ = self.invoke_gas("usage", [fixture, rejection])
        self.assertEqual(code, 0)
        self.assertIn("rejected gas dates from 2024-01-03", out)
        self.assertNotIn("synthetic-password", out + err)

    def test_first_gas_rejection_is_still_an_error_without_rows(self):
        code, out, _, client, sleep = self.invoke_gas(
            "summary", [GenesisError(7, self.GAS_UNAVAILABLE), AssertionError("read after rejection")], extra=("--json",))
        self.assertEqual(code, 7)
        result = json.loads(out)
        self.assertEqual(result["results"], [])
        self.assertEqual(result["error"]["type"], "unsupported_operation")
        self.assertNotIn("provider_unavailable_from", result["meta"])
        self.assertNotIn("observed_usage_kwh", result["meta"])
        self.assertEqual(client.gas.call_count, 1)
        sleep.assert_not_called()

    def test_later_gas_blocked_outage_or_schema_failure_still_aborts(self):
        fixture = json.loads((FIXTURES / "gas-sample.json").read_text())["response"]
        for failure, expected in ((GenesisError(4, "Genesis rate limit; retry later"), 4),
                                  (GenesisError(5, "Genesis gas request failed"), 5),
                                  (GenesisError(6, "Genesis response schema changed"), 6),
                                  ({"usage": None}, 6)):
            with self.subTest(expected=expected, failure=failure):
                code, out, _, client, sleep = self.invoke_gas("summary", [fixture, failure], extra=("--json",))
                self.assertEqual(code, expected)
                result = json.loads(out)
                self.assertEqual(result["results"], [])
                self.assertEqual(result["error"]["code"], expected)
                self.assertNotIn("provider_unavailable_from", result["meta"])
                self.assertNotIn("observed_usage_kwh", result["meta"])
                self.assertEqual(client.gas.call_count, 2)
                self.assertEqual(sleep.call_count, 1)

    def test_empty_gas_chunk_then_rejection_is_no_readings_with_null_totals(self):
        code, out, _, client, _ = self.invoke_gas(
            "summary", [{"usage": []}, GenesisError(7, self.GAS_UNAVAILABLE)], extra=("--group", "range", "--json"))
        self.assertEqual(code, 0)
        result = json.loads(out)
        meta = result["meta"]
        self.assertEqual(meta["provider_unavailable_from"], "2024-01-03")
        self.assertEqual(meta["coverage"], "no_readings")
        self.assertEqual((meta["received_intervals"], meta["missing_intervals"]), (0, 120))
        self.assertIsNone(meta["observed_usage_kwh"])
        self.assertIsNone(meta["observed_usage_cost_nzd"])
        self.assertNotIn("latest_data", meta)
        self.assertEqual(client.gas.call_count, 2)

    def test_electricity_later_failure_and_payload_are_unchanged(self):
        factory = Mock()
        factory.return_value.electricity.side_effect = [sample(), GenesisError(5, "Genesis electricity request failed")]
        args = ["summary", "--start", "2024-01-01", "--end", "2024-01-03", "--json"]
        with patch.object(cli.time, "sleep"):
            code, out, _, _ = self.invoke(args, factory, self.ENV)
        self.assertEqual(code, 5)
        self.assertEqual(json.loads(out)["results"], [])
        self.assertNotIn("provider_unavailable_from", json.loads(out)["meta"])
        # Exit 7 cannot come from the electricity transport; even if it did, no partial rows.
        client = Mock()
        client.electricity.side_effect = [sample(), GenesisError(7, self.GAS_UNAVAILABLE)]
        with self.assertRaises(GenesisError) as raised:
            fetch_usage(client, DAY, date(2024, 1, 3), NOW, Mock())
        self.assertEqual(raised.exception.code, 7)
        factory = Mock()
        factory.return_value.electricity.return_value = sample()
        code, out, _, _ = self.invoke(["summary", "--start", "2024-01-01", "--end", "2024-01-01", "--group", "range", "--json"], factory, self.ENV)
        self.assertEqual(code, 0)
        self.assertEqual(set(json.loads(out)["meta"]), {
            "source_url", "publisher", "retrieved_at", "fuel", "start_date", "end_date", "timezone",
            "expected_intervals", "received_intervals", "missing_intervals", "coverage",
            "latest_interval_start", "observed_usage_kwh", "observed_usage_cost_nzd",
            "cost_basis", "unit_basis", "latest_data",
        })

    def test_gas_bounded_chunks_and_dst(self):
        client, pause = Mock(), Mock()
        start, end = date(2024, 4, 6), date(2024, 4, 7)
        hours = 49
        client.gas.return_value = {"usage": [
            {"startDate": (midnight(start) + i * HOUR).isoformat(), "kw": "1.0", "costNZD": "0.09"}
            for i in range(hours)
        ]}
        rows, unavailable_from = fetch_usage(client, start, end, datetime(2024, 4, 10, tzinfo=timezone.utc), pause, "gas")
        self.assertIsNone(unavailable_from)
        self.assertEqual(len(rows), hours)
        self.assertEqual(coverage(rows, start, end)["coverage"], "complete")
        self.assertEqual(coverage(rows, end, end)["expected_intervals"], 25)
        client.electricity.assert_not_called()
        client.gas.assert_called_once_with(start, end)
        pause.assert_not_called()
        client.reset_mock()
        client.gas.return_value = {"usage": []}
        fetch_usage(client, DAY, date(2024, 1, 31), NOW, pause, "gas")
        self.assertEqual(client.gas.call_count, 16)
        self.assertEqual(pause.call_count, 15)
        client.electricity.assert_not_called()

    def test_gas_auth_rate_limit_and_outage_are_not_absent_service(self):
        url = GAS_DATA + "?" + urlencode({"startDate": "2024-01-01", "endDate": "2024-01-01", "intervalType": "HOURLY"})
        for status, code in ((401, 4), (403, 4), (429, 4), (503, 5)):
            transport = Transport()
            response = urllib.error.HTTPError(url, status, "synthetic-private-message", {"Retry-After": "60"}, io.BytesIO(b"synthetic-private-body"))
            with patch.object(transport.opener, "open", side_effect=response) as opened:
                with self.assertRaises(GenesisError) as raised:
                    transport.request("GET", url)
                opened.assert_called_once()
            self.assertEqual(raised.exception.code, code)
            if status == 429:
                self.assertEqual(raised.exception.retry_after, "60")
            self.assertNotIn("synthetic-private", str(raised.exception))

    def test_gas_missing_credentials_and_invalid_fuel_do_not_query(self):
        base = ["summary", "--start", "2024-01-01", "--end", "2024-01-01", "--json"]
        for fuel, expected in (("gas", 3), ("invalid-fuel", 2)):
            code, out, err, factory = self.invoke([*base, "--fuel", fuel])
            self.assertEqual(code, expected)
            factory.assert_not_called()
            self.assertEqual(json.loads(out)["results"], [])


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
