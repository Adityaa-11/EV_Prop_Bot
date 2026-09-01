#!/usr/bin/env python3
"""Poll the Railway execution queue for pending live entries."""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request


def main() -> int:
    base_url = os.getenv("EV_BACKEND_URL")
    key = os.getenv("HERMES_API_KEY")
    if not base_url or not key:
        print("Missing EV_BACKEND_URL or HERMES_API_KEY", file=sys.stderr)
        return 2

    request = urllib.request.Request(
        f"{base_url.rstrip('/')}/api/hermes/execution/pending",
        headers={"Accept": "application/json", "X-Hermes-Key": key},
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            print(response.read().decode("utf-8"))
            return 0
    except urllib.error.HTTPError as error:
        print(error.read().decode("utf-8"), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
