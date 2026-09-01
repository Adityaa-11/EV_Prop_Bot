#!/usr/bin/env python3
"""Report a live execution result back to Railway."""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request


def main() -> int:
    parser = argparse.ArgumentParser(description="Report live execution result")
    parser.add_argument("entry_id")
    parser.add_argument("status", choices=["submitted", "failed", "skipped"])
    parser.add_argument("--ticket-id")
    parser.add_argument("--error")
    args = parser.parse_args()

    base_url = os.getenv("EV_BACKEND_URL")
    key = os.getenv("HERMES_API_KEY")
    if not base_url or not key:
        print("Missing EV_BACKEND_URL or HERMES_API_KEY", file=sys.stderr)
        return 2

    body = {"status": args.status}
    if args.ticket_id:
        body["external_ticket_id"] = args.ticket_id
    if args.error:
        body["error"] = args.error

    request = urllib.request.Request(
        f"{base_url.rstrip('/')}/api/hermes/execution/{args.entry_id}/result",
        method="POST",
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "X-Hermes-Key": key,
        },
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
