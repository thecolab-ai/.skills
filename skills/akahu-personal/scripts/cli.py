#!/usr/bin/env python3
import argparse
import csv
import json
import os
import re
import stat
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

DEFAULT_BASE_URL = "https://api.akahu.io/v1"
ACCOUNT_RE = re.compile(r"\b(?:\d{2}|x{4})-(?:\d{4}|x{4})-(?:\d{6,7}|x{4})-(?:\d{2,4})\b", re.I)
SAFE_METHODS = {"GET"}
MUTATING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def die(message, code=1):
    print(f"error: {message}", file=sys.stderr)
    raise SystemExit(code)


def env_required(name):
    value = os.environ.get(name)
    if not value:
        die(f"missing {name}; export it before running this authenticated personal-data CLI")
    return value


def redact_account(value):
    if not isinstance(value, str):
        return value

    def repl(match):
        text = match.group(0)
        tail = text.split("-")[-1]
        return f"xx-xxxx-xxxxxxx-{tail}"

    return ACCOUNT_RE.sub(repl, value)


def redact_obj(obj):
    if isinstance(obj, dict):
        out = {}
        for key, value in obj.items():
            if key in {"formatted_account", "other_account"} and isinstance(value, str):
                out[key] = redact_account(value)
            else:
                out[key] = redact_obj(value)
        return out
    if isinstance(obj, list):
        return [redact_obj(item) for item in obj]
    if isinstance(obj, str):
        return redact_account(obj)
    return obj


def parse_params(params):
    parsed = []
    for item in params or []:
        if "=" not in item:
            die(f"query parameter must be key=value, got: {item}")
        key, value = item.split("=", 1)
        if not key:
            die(f"query parameter key cannot be empty: {item}")
        parsed.append((key, value))
    return parsed


class AkahuClient:
    def __init__(self, base_url, app_token, user_token):
        self.base_url = base_url.rstrip("/")
        self.app_token = app_token
        self.user_token = user_token

    def request(self, method, path, params=None, json_body=None):
        method = method.upper()
        url = f"{self.base_url}/{path.lstrip('/')}"
        if params:
            query = urllib.parse.urlencode(params)
            if query:
                url = f"{url}?{query}"
        body = None
        headers = {
            "Authorization": f"Bearer {self.user_token}",
            "X-Akahu-Id": self.app_token,
            "Accept": "application/json",
            "User-Agent": "thecolab-skills-akahu-personal/1.0",
        }
        if json_body is not None:
            body = json.dumps(json_body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=body, headers=headers, method=method)
        response_body = ""
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                response_body = resp.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:500]
            die(f"Akahu HTTP {exc.code} for {method} {path}: {detail}")
        except urllib.error.URLError as exc:
            die(f"Akahu request failed for {method} {path}: {exc.reason}")
        if not response_body:
            return None
        try:
            return json.loads(response_body)
        except json.JSONDecodeError as exc:
            die(f"Akahu returned non-JSON for {method} {path}: {exc}")

    def get(self, path, params=None):
        return self.request("GET", path, params=params)


def get_client(args):
    return AkahuClient(
        base_url=args.base_url,
        app_token=env_required(args.app_token_env),
        user_token=env_required(args.user_token_env),
    )


def emit(data, as_json=False):
    if as_json:
        print(json.dumps(data, indent=2, sort_keys=True))
    else:
        print_human(data)


def print_human(data):
    if data is None:
        print("null")
    elif isinstance(data, dict) and "items" in data and isinstance(data["items"], list):
        for item in data["items"]:
            if "balance" in item:
                bal = item.get("balance") or {}
                print(f"{item.get('name', item.get('_id'))}: {bal.get('current')} {bal.get('currency', '')} ({item.get('type', '')}, {item.get('formatted_account', '')})")
            elif "amount" in item:
                print(f"{item.get('date')} {item.get('amount')} {item.get('type', '')}: {item.get('description', '')}")
            else:
                print(json.dumps(item, sort_keys=True))
    else:
        print(json.dumps(data, indent=2, sort_keys=True))


def maybe_redact(data, raw):
    return data if raw else redact_obj(data)


def cmd_me(args):
    data = get_client(args).get("/me")
    emit(data, args.json)


def cmd_accounts(args):
    data = get_client(args).get("/accounts")
    emit(maybe_redact(data, args.raw_account_numbers), args.json)


def cmd_transactions(args):
    params = [("limit", str(args.limit))]
    if args.start:
        params.append(("start", args.start))
    if args.end:
        params.append(("end", args.end))
    data = get_client(args).get("/transactions", params=params)
    emit(maybe_redact(data, args.raw_account_numbers), args.json)


def cmd_endpoint(args):
    method = args.method.upper()
    if method not in SAFE_METHODS | MUTATING_METHODS:
        die(f"unsupported method {method}; use one of GET, POST, PUT, PATCH, DELETE")
    if method in MUTATING_METHODS and not args.i_understand_this_can_mutate:
        die(f"{method} can mutate Akahu state or initiate/cancel actions; re-run with --i-understand-this-can-mutate")
    json_body = None
    if args.data_json:
        try:
            json_body = json.loads(args.data_json)
        except json.JSONDecodeError as exc:
            die(f"--data-json is not valid JSON: {exc}")
    elif args.data_file:
        try:
            json_body = json.loads(Path(args.data_file).read_text(encoding="utf-8"))
        except OSError as exc:
            die(f"cannot read --data-file: {exc}")
        except json.JSONDecodeError as exc:
            die(f"--data-file is not valid JSON: {exc}")
    params = parse_params(args.param)
    data = get_client(args).request(method, args.path, params=params, json_body=json_body)
    emit(maybe_redact(data, args.raw_account_numbers), True)


def chmod_private(path):
    try:
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass


def cmd_export(args):
    out_dir = Path(args.out_dir).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(out_dir, stat.S_IRWXU)
    except OSError:
        pass

    client = get_client(args)
    datasets = {
        "me.json": client.get("/me"),
        "accounts.json": maybe_redact(client.get("/accounts"), args.raw_account_numbers),
        "transactions_recent.json": maybe_redact(client.get("/transactions", [("limit", str(args.limit))]), args.raw_account_numbers),
    }
    for filename, data in datasets.items():
        path = out_dir / filename
        path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
        chmod_private(path)

    tx_items = datasets["transactions_recent.json"].get("items", [])
    csv_path = out_dir / "transactions_recent.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["date", "account_id", "amount", "balance", "type", "description", "merchant", "category_group", "category"])
        for tx in tx_items:
            category = tx.get("category") or {}
            group = ((category.get("groups") or {}).get("personal_finance") or {}).get("name")
            writer.writerow([
                tx.get("date"),
                tx.get("_account"),
                tx.get("amount"),
                tx.get("balance"),
                tx.get("type"),
                tx.get("description"),
                (tx.get("merchant") or {}).get("name"),
                group,
                category.get("name"),
            ])
    chmod_private(csv_path)
    print(json.dumps({"out_dir": str(out_dir), "files": sorted(datasets.keys()) + ["transactions_recent.csv"]}, indent=2))


def add_common(parser):
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="Akahu API base URL")
    parser.add_argument("--app-token-env", default="AKAHU_APP_TOKEN", help="environment variable holding the App ID Token")
    parser.add_argument("--user-token-env", default="AKAHU_USER_TOKEN", help="environment variable holding the User Access Token")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Akahu Personal App CLI for user-owned banking data")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("me", help="fetch /me")
    add_common(p)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_me)

    p = sub.add_parser("accounts", help="fetch accounts and balances")
    add_common(p)
    p.add_argument("--json", action="store_true")
    p.add_argument("--raw-account-numbers", action="store_true", help="do not redact account numbers")
    p.set_defaults(func=cmd_accounts)

    p = sub.add_parser("transactions", help="fetch recent transactions")
    add_common(p)
    p.add_argument("--limit", type=int, default=50)
    p.add_argument("--start", help="exclusive ISO start timestamp/date query parameter")
    p.add_argument("--end", help="inclusive ISO end timestamp/date query parameter")
    p.add_argument("--json", action="store_true")
    p.add_argument("--raw-account-numbers", action="store_true", help="do not redact account numbers")
    p.set_defaults(func=cmd_transactions)

    p = sub.add_parser("endpoint", help="call any Akahu API path with Personal App auth")
    add_common(p)
    p.add_argument("path", help="API path, e.g. /accounts/{id}/transactions/pending")
    p.add_argument("--method", default="GET", help="HTTP method: GET, POST, PUT, PATCH, DELETE")
    p.add_argument("--param", action="append", default=[], help="query parameter as key=value; repeatable")
    p.add_argument("--data-json", help="JSON request body for POST/PUT/PATCH")
    p.add_argument("--data-file", help="path to JSON request body for POST/PUT/PATCH")
    p.add_argument("--raw-account-numbers", action="store_true", help="do not redact account numbers")
    p.add_argument("--i-understand-this-can-mutate", action="store_true", help="required for POST/PUT/PATCH/DELETE")
    p.set_defaults(func=cmd_endpoint)

    p = sub.add_parser("export", help="write private JSON/CSV exports")
    add_common(p)
    p.add_argument("--out-dir", required=True)
    p.add_argument("--limit", type=int, default=100)
    p.add_argument("--raw-account-numbers", action="store_true", help="do not redact account numbers")
    p.set_defaults(func=cmd_export)

    args = parser.parse_args(argv)
    if hasattr(args, "limit") and args.limit < 1:
        die("--limit must be >= 1")
    if getattr(args, "data_json", None) and getattr(args, "data_file", None):
        die("use only one of --data-json or --data-file")
    args.func(args)


if __name__ == "__main__":
    main()
