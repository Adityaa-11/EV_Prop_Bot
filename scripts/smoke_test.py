"""Production-safe API smoke test.

Usage:
    HERMES_API_KEY=... python scripts/smoke_test.py https://your-api.example
    HERMES_API_KEY=... python scripts/smoke_test.py https://your-api.example --scan --sport mlb
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request


def request_json(
    base_url: str,
    path: str,
    *,
    method: str = "GET",
    hermes_key: str | None = None,
) -> tuple[int, dict]:
    headers = {"Accept": "application/json"}
    if hermes_key:
        headers["X-Hermes-Key"] = hermes_key
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}{path}",
        method=method,
        headers=headers,
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("base_url")
    parser.add_argument("--sport", default="mlb")
    parser.add_argument("--platform", default="all", choices=["all", "prizepicks", "underdog"])
    parser.add_argument("--scan", action="store_true")
    arguments = parser.parse_args()

    hermes_key = os.getenv("HERMES_API_KEY")
    if not hermes_key:
        print("HERMES_API_KEY is required", file=sys.stderr)
        return 2

    health_status, health = request_json(arguments.base_url, "/api/health")
    print(
        json.dumps(
            {
                "check": "health",
                "http": health_status,
                "status": health.get("status"),
                "odds_api_configured": health.get("odds_api_configured"),
                "hermes_api_configured": health.get("hermes_api_configured"),
            }
        )
    )
    if health_status != 200 or health.get("status") != "ok":
        return 1

    if arguments.scan:
        query = urllib.parse.urlencode(
            {
                "sport": arguments.sport,
                "platform": arguments.platform,
                "min_books": 2,
            }
        )
        scan_status, scan = request_json(
            arguments.base_url,
            f"/api/hermes/scan?{query}",
            method="POST",
            hermes_key=hermes_key,
        )
        print(
            json.dumps(
                {
                    "check": "scan",
                    "http": scan_status,
                    "count": scan.get("count"),
                    "error": scan.get("error"),
                }
            )
        )
        if scan_status != 200:
            return 1

    candidates_status, candidates = request_json(
        arguments.base_url,
            (
                f"/api/hermes/candidates?"
                f"sport={urllib.parse.quote(arguments.sport)}&"
                f"platform={urllib.parse.quote(arguments.platform)}"
            ),
        hermes_key=hermes_key,
    )
    print(
        json.dumps(
            {
                "check": "candidates",
                "http": candidates_status,
                "count": candidates.get("count"),
                "age_seconds": candidates.get("age_seconds"),
                "detail": candidates.get("detail"),
            }
        )
    )
    return 0 if candidates_status == 200 else 1


if __name__ == "__main__":
    raise SystemExit(main())

