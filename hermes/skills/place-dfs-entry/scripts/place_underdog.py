#!/usr/bin/env python3
"""Place or shadow-verify an Underdog slip from ENTRY_JSON env."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def main() -> int:
    entry = json.loads(os.environ.get("ENTRY_JSON", "{}"))
    shadow = os.getenv("EXECUTION_SHADOW_MODE", "true").lower() in {"1", "true", "yes"}
    profile = os.getenv("UD_BROWSER_PROFILE", str(Path.home() / ".ev-bot" / "underdog-profile"))

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print(json.dumps({"status": "failed", "error": "playwright not installed"}))
        return 1

    legs = entry.get("legs") or []
    if len(legs) < 2:
        print(json.dumps({"status": "failed", "error": "entry requires 2 legs"}))
        return 1

    with sync_playwright() as playwright:
        context = playwright.chromium.launch_persistent_context(
            profile,
            headless=os.getenv("UD_HEADLESS", "false").lower() in {"1", "true", "yes"},
        )
        page = context.new_page()
        page.goto("https://underdogfantasy.com/pick-em", wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(3000)

        missing = []
        for leg in legs:
            query = leg.get("player_name", "")
            if not query:
                missing.append("blank_player")
                continue
            if page.get_by_text(query, exact=False).count() == 0:
                missing.append(query)

        screenshot_dir = Path(os.getenv("EV_BOT_ARTIFACTS", "/tmp/ev-bot-artifacts"))
        screenshot_dir.mkdir(parents=True, exist_ok=True)
        shot = screenshot_dir / f"{entry.get('id', 'entry')}-ud.png"
        page.screenshot(path=str(shot))

        if missing:
            print(json.dumps({"status": "failed", "error": f"players_not_found:{','.join(missing)}"}))
            context.close()
            return 1

        if shadow:
            print(json.dumps({"status": "skipped", "error": f"shadow_mode screenshot={shot}"}))
            context.close()
            return 0

        print(json.dumps({
            "status": "failed",
            "error": "submit_flow_not_automated_yet_verify_selectors_in_shadow_first",
        }))
        context.close()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
