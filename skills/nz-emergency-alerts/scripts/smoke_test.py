#!/usr/bin/env python3
import importlib.util, json, subprocess, sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
SKILL = Path(__file__).resolve().parents[1]; CLI = SKILL / "scripts" / "cli.py"
spec = importlib.util.spec_from_file_location("cap_cli", CLI); mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
body = (SKILL / "tests" / "fixtures" / "cap-atom.xml").read_bytes(); status, alerts, linked = mod.parse_feed(body, "https://alerthub.civildefence.govt.nz/atom/pwp", "2026-07-19T00:00:00Z")
assert status["updated"] and alerts[0]["id"] == "NZ-TEST-1" and alerts[0]["instruction"] == "Move to high ground."
assert mod.point_in_polygon(-41.5, 174.5, alerts[0]["areas"][0]["polygons"][0]); assert not mod.point_in_polygon(-40, 174.5, alerts[0]["areas"][0]["polygons"][0])
assert mod.point_in_circle(-41.2865, 174.7762, "-41.2865,174.7762 10") and linked == ["https://alerthub.civildefence.govt.nz/alerts/NZ-LINKED.xml"]
active = mod.active_alerts(alerts, datetime(2026, 7, 19, 12, tzinfo=timezone.utc)); assert {row["id"] for row in active} == {"NZ-TEST-1", "NZ-CIRCLE"}
update = {**alerts[0], "id": "NZ-TEST-1-UPDATE", "sent": "2026-07-19T00:05:00Z", "message_type": "Update", "references": "official@example.govt.nz,NZ-TEST-1,2026-07-19T00:00:00Z"}
assert {row["id"] for row in mod.active_alerts([alerts[0], update], datetime(2026, 7, 19, 12, tzinfo=timezone.utc))} == {"NZ-TEST-1-UPDATE"}
assert mod.feed_health(status, datetime(2026, 7, 19, 0, 10, tzinfo=timezone.utc))["healthy"] is True
assert mod.feed_health(status, datetime(2026, 7, 19, 1, 0, tzinfo=timezone.utc))["stale"] is True
try: mod.parse_feed(b"<html></html>", "https://alerthub.civildefence.govt.nz/atom/pwp", "2026-07-19T00:00:00Z")
except ValueError: pass
else: raise AssertionError("HTML must not parse as a healthy CAP feed")
malicious = body.replace(b'/alerts/NZ-LINKED.xml', b'https://example.com/alert.xml')
try: mod.parse_feed(malicious, "https://alerthub.civildefence.govt.nz/atom/pwp", "2026-07-19T00:00:00Z")
except ValueError: pass
else: raise AssertionError("linked entries must stay on the declared alert host")
root = ET.fromstring(body)
template = ET.tostring(root.find(f"{{{mod.ATOM_NS}}}entry/{{{mod.CAP_NS}}}alert"))
detail_bodies = {
    "https://alerthub.civildefence.govt.nz/alerts/first.xml": template.replace(b"NZ-TEST-1", b"NZ-FIRST"),
    "https://alerthub.civildefence.govt.nz/alerts/target.xml": template.replace(b"NZ-TEST-1", b"NZ-TARGET"),
}
fetched = []
def fake_fetch(url, **_kwargs):
    fetched.append(url)
    return detail_bodies[url], "application/xml", url
linked_alerts = mod.fetch_linked_alerts(list(detail_bodies), "2026-07-19T00:00:00Z", fetcher=fake_fetch)
target = [alert for alert in linked_alerts if alert["id"] == "NZ-TARGET"][:1]
assert [alert["id"] for alert in target] == ["NZ-TARGET"]
assert fetched == list(detail_bodies), "linked fetches must not be truncated by output --limit"
try: mod.fetch_linked_alerts([f"https://alerthub.civildefence.govt.nz/alerts/{index}.xml" for index in range(mod.MAX_LINKED_ENTRIES + 1)], "2026-07-19T00:00:00Z", fetcher=fake_fetch)
except ValueError: pass
else: raise AssertionError("oversized linked-entry feeds must fail closed")
print("[PASS] fixture CAP 1.2 fields and polygon point matching")
print("[PASS] complete bounded linked-entry retrieval precedes result filtering")
r = subprocess.run([sys.executable, str(CLI), "--help"], capture_output=True, text=True, timeout=10); assert r.returncode == 0
print("[PASS] contract CLI help is executable")
for coordinate_args in (("--lat", "91", "--lon", "174"), ("--lat", "-41", "--lon", "181"), ("--lat", "nan", "--lon", "174")):
    invalid = subprocess.run([sys.executable, str(CLI), "near", *coordinate_args, "--json"], capture_output=True, text=True, timeout=10)
    assert invalid.returncode == 2 and "invalid_input" in invalid.stderr and "blocked" not in invalid.stderr
print("[PASS] invalid near coordinates fail before network access")
r = subprocess.run([sys.executable, str(CLI), "feed-status", "--json"], capture_output=True, text=True, timeout=45)
if r.returncode == 0:
    payload = json.loads(r.stdout); assert payload["data"][0]["healthy"] is True; print("[PASS] live official CAP feed status")
elif r.returncode in {4, 5}:
    print(f"[SKIP] network official CAP feed unavailable: {r.stderr.strip()}")
else: print(r.stderr, file=sys.stderr); raise SystemExit(1)
