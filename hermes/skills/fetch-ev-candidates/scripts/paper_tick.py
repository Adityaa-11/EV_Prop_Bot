"""Invoke one quota-gated deterministic paper tick."""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sport", default="mlb")
    arguments = parser.parse_args()

    base_url = os.getenv("EV_BACKEND_URL")
    hermes_key = os.getenv("HERMES_API_KEY")
    if not base_url or not hermes_key:
        print(json.dumps({"status": "error", "message": "Paper backend is not configured"}))
        return 2

    query = urllib.parse.urlencode({"sport": arguments.sport})
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}/api/hermes/paper/tick?{query}",
        method="POST",
        headers={
            "Accept": "application/json",
            "X-Hermes-Key": hermes_key,
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            payload = json.loads(response.read())
    except urllib.error.HTTPError as error:
        try:
            detail = json.loads(error.read()).get("detail")
        except (json.JSONDecodeError, AttributeError):
            detail = "Backend request failed"
        print(json.dumps({"status": "error", "http": error.code, "message": detail}))
        return 1
    except urllib.error.URLError:
        print(json.dumps({"status": "error", "message": "Paper backend is unavailable"}))
        return 1

    print(json.dumps(payload, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
