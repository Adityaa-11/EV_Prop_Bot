#!/usr/bin/env python3
"""Place or shadow-verify an Underdog slip from ENTRY_JSON env."""

from __future__ import annotations

import os
from pathlib import Path

from dfs_common import (
    browser_launch_kwargs,
    clear_existing_slip,
    click_submit,
    ensure_logged_in,
    extract_ticket_id,
    fail,
    is_shadow_mode,
    load_entry,
    screenshot,
    select_legs,
    set_entry_stake,
    skip_shadow,
    stake_amount,
    submit_ok,
    verify_submission,
)


def main() -> int:
    entry = load_entry()
    shadow = is_shadow_mode()
    profile = Path(os.getenv("UD_BROWSER_PROFILE", str(Path.home() / ".ev-bot" / "underdog-profile")))
    entry_id = str(entry.get("id") or "entry")

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return fail("playwright not installed; run: pip install playwright && playwright install chromium")

    legs = entry.get("legs") or []
    if len(legs) < 2:
        return fail("entry requires 2 legs")

    profile.parent.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as playwright:
        context = playwright.chromium.launch_persistent_context(**browser_launch_kwargs(profile))
        page = context.new_page()
        try:
            page.goto("https://underdogfantasy.com/pick-em/higher-lower/all", wait_until="domcontentloaded", timeout=90000)
            page.wait_for_timeout(3500)

            auth_error = ensure_logged_in(page, "underdog")
            if auth_error:
                shot = screenshot(page, entry_id, "ud", "auth")
                return fail(auth_error, screenshot=shot)

            missing = select_legs(page, legs, platform="underdog", verify_only=shadow)
            shot = screenshot(page, entry_id, "ud", "preflight")
            if missing:
                return fail(f"players_not_found:{','.join(missing)}", screenshot=shot)

            if shadow:
                return skip_shadow(shot)

            clear_existing_slip(page)
            missing = select_legs(page, legs, platform="underdog", verify_only=False)
            if missing:
                shot = screenshot(page, entry_id, "ud", "missing-after-clear")
                return fail(f"players_not_found:{','.join(missing)}", screenshot=shot)

            set_entry_stake(page, stake_amount(entry))
            screenshot(page, entry_id, "ud", "pre-submit")
            click_submit(page)
            post_shot = screenshot(page, entry_id, "ud", "post-submit")

            submit_error = verify_submission(page)
            if submit_error:
                return fail(submit_error, screenshot=post_shot)

            ticket_id = extract_ticket_id(page, entry_id, "ud")
            return submit_ok(ticket_id=ticket_id, screenshot=post_shot)
        except Exception as exc:  # noqa: BLE001
            shot = screenshot(page, entry_id, "ud", "error")
            return fail(str(exc), screenshot=shot)
        finally:
            context.close()


if __name__ == "__main__":
    raise SystemExit(main())
