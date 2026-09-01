#!/usr/bin/env python3
"""Poll Railway for pending live entries and drive Playwright placement."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


def request_json(
    base_url: str,
    path: str,
    *,
    method: str = "GET",
    body: dict | None = None,
    key: str | None = None,
) -> tuple[int, dict]:
    headers = {"Accept": "application/json"}
    if key:
        headers["X-Hermes-Key"] = key
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}{path}",
        method=method,
        headers=headers,
        data=data,
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as error:
        payload = json.loads(error.read() or b"{}")
        return error.code, payload


def heartbeat(base_url: str, key: str) -> None:
    request_json(base_url, "/api/hermes/execution/heartbeat", method="POST", key=key)


def main() -> int:
    base_url = os.getenv("EV_BACKEND_URL")
    key = os.getenv("HERMES_API_KEY")
    if not base_url or not key:
        print("Missing EV_BACKEND_URL or HERMES_API_KEY")
        return 2

    heartbeat(base_url, key)
    status, payload = request_json(base_url, "/api/hermes/execution/pending", key=key)
    if status != 200:
        print(f"Pending fetch failed: HTTP {status} {payload}")
        return 1
    if not payload.get("enabled"):
        print("Live execution disabled on backend.")
        return 0

    entries = payload.get("entries") or []
    if not entries:
        print("No pending live entries.")
        return 0

    scripts_dir = Path(__file__).resolve().parent
    shadow = bool(payload.get("shadow_mode"))
    errors = 0
    for entry in entries:
        entry_id = entry["id"]
        claim_status, claim_payload = request_json(
            base_url,
            f"/api/hermes/execution/{urllib.parse.quote(entry_id)}/claim",
            method="POST",
            key=key,
        )
        if claim_status != 200:
            print(f"Claim failed for {entry_id}: {claim_payload}")
            errors += 1
            continue

        claimed = claim_payload.get("entry") or entry
        platform = (claimed.get("platform") or "prizepicks").lower()
        script = "place_prizepicks.py" if platform == "prizepicks" else "place_underdog.py"
        env = os.environ.copy()
        env["ENTRY_JSON"] = json.dumps(claimed)
        env["EXECUTION_SHADOW_MODE"] = "true" if shadow else "false"
        proc = subprocess.run(
            [sys.executable, str(scripts_dir / script)],
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        if proc.returncode != 0:
            result_body = {
                "status": "failed",
                "error": (proc.stderr or proc.stdout or "playwright_failed")[:500],
            }
        else:
            try:
                result_body = json.loads(proc.stdout.strip() or "{}")
            except json.JSONDecodeError:
                result_body = {"status": "failed", "error": "invalid_playwright_output"}

        result_status, result_payload = request_json(
            base_url,
            f"/api/hermes/execution/{urllib.parse.quote(entry_id)}/result",
            method="POST",
            body=result_body,
            key=key,
        )
        if result_status != 200:
            print(f"Result post failed for {entry_id}: {result_payload}")
            errors += 1
            continue
        print(f"{entry_id}: {result_body.get('status')}")

    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
