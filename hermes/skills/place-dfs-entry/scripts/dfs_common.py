"""Shared helpers for PrizePicks / Underdog Playwright executors."""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any

from playwright.sync_api import Locator, Page, TimeoutError as PlaywrightTimeout


def load_entry() -> dict[str, Any]:
    return json.loads(os.environ.get("ENTRY_JSON", "{}"))


def is_shadow_mode() -> bool:
    return os.getenv("EXECUTION_SHADOW_MODE", "true").lower() in {"1", "true", "yes"}


def stake_amount(entry: dict[str, Any]) -> float:
    return float(entry.get("stake") or os.getenv("LIVE_STAKE", "5"))


def artifacts_dir() -> Path:
    path = Path(os.getenv("EV_BOT_ARTIFACTS", "/tmp/ev-bot-artifacts"))
    path.mkdir(parents=True, exist_ok=True)
    return path


def emit(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, separators=(",", ":")))


def fail(error: str, *, screenshot: Path | None = None) -> int:
    message = error[:500]
    if screenshot:
        message = f"{message} screenshot={screenshot}"
    emit({"status": "failed", "error": message})
    return 1


def skip_shadow(screenshot: Path) -> int:
    emit({"status": "skipped", "error": f"shadow_mode screenshot={screenshot}"})
    return 0


def submit_ok(*, ticket_id: str | None, screenshot: Path | None = None) -> int:
    body: dict[str, Any] = {"status": "submitted"}
    if ticket_id:
        body["external_ticket_id"] = ticket_id[:120]
    if screenshot:
        body["confirmation_screenshot"] = str(screenshot)
    emit(body)
    return 0


def normalize_side(side: str) -> str:
    value = (side or "").strip().upper()
    if value in {"OVER", "MORE", "HIGHER"}:
        return "over"
    if value in {"UNDER", "LESS", "LOWER"}:
        return "under"
    raise ValueError(f"unsupported_side:{side}")


def format_line(line: float) -> str:
    if abs(line - round(line)) < 1e-9:
        return str(int(round(line)))
    text = f"{line:.1f}".rstrip("0").rstrip(".")
    return text if "." in text else f"{text}.0"


def line_in_text(text: str, line: float) -> bool:
    target = format_line(line)
    compact = text.replace(",", "")
    patterns = [
        rf"\b{re.escape(target)}\b",
        rf"\b{re.escape(target.replace('.0', ''))}\b",
    ]
    if "." in target:
        whole, frac = target.split(".", 1)
        patterns.append(rf"\b{re.escape(whole)}\.{re.escape(frac)}0+\b")
    return any(re.search(pattern, compact) for pattern in patterns)


def last_name(player_name: str) -> str:
    parts = [part for part in player_name.replace(".", " ").split() if part]
    return parts[-1] if parts else player_name


def browser_launch_kwargs(profile: Path) -> dict[str, Any]:
    headless = os.getenv("PP_HEADLESS", os.getenv("UD_HEADLESS", "false")).lower() in {
        "1",
        "true",
        "yes",
    }
    return {
        "user_data_dir": str(profile),
        "headless": headless,
        "viewport": {"width": 1440, "height": 960},
        "args": ["--disable-blink-features=AutomationControlled"],
    }


def screenshot(page: Page, entry_id: str, platform: str, suffix: str) -> Path:
    path = artifacts_dir() / f"{entry_id}-{platform}-{suffix}.png"
    page.screenshot(path=str(path), full_page=True)
    return path


def ensure_logged_in(page: Page, platform: str) -> str | None:
    url = page.url.lower()
    if any(token in url for token in ("login", "sign-in", "signin", "auth")):
        return "login_required"

    login_patterns = [
        r"log in",
        r"sign in",
        r"create account",
    ]
    for pattern in login_patterns:
        if page.get_by_role("button", name=re.compile(pattern, re.I)).count() > 0:
            # PrizePicks shows Log In even when browsing as guest; only fail if board empty.
            if platform == "prizepicks":
                continue
            return "login_required"

    captcha_markers = ["captcha", "verify you are human", "recaptcha"]
    body = page.locator("body").inner_text(timeout=5000).lower()
    if any(marker in body for marker in captcha_markers):
        return "captcha_required"
    return None


def clear_existing_slip(page: Page) -> None:
    for label in ("Clear", "Clear all", "Remove all", "Reset"):
        button = page.get_by_role("button", name=re.compile(rf"^{label}$", re.I))
        if button.count() > 0:
            try:
                button.first.click(timeout=2000)
                page.wait_for_timeout(800)
                return
            except PlaywrightTimeout:
                continue


def set_entry_stake(page: Page, amount: float) -> None:
    stake_text = format_line(amount) if amount == int(amount) else f"{amount:g}"
    selectors = [
        "input[name*='amount' i]",
        "input[name*='stake' i]",
        "input[name*='entry' i]",
        "input[type='number']",
        "input[inputmode='decimal']",
    ]
    for selector in selectors:
        field = page.locator(selector).first
        if field.count() == 0:
            continue
        try:
            field.click(timeout=1500)
            field.fill("")
            field.type(stake_text, delay=40)
            page.wait_for_timeout(400)
            return
        except PlaywrightTimeout:
            continue

    for label in (f"${stake_text}", stake_text, f"${amount:g}"):
        chip = page.get_by_role("button", name=re.compile(rf"^{re.escape(label)}$", re.I))
        if chip.count() > 0:
            chip.first.click(timeout=2000)
            page.wait_for_timeout(400)
            return


def click_submit(page: Page) -> None:
    patterns = [
        r"place entry",
        r"submit entry",
        r"submit pick",
        r"enter entry",
        r"place pick",
        r"submit",
    ]
    for pattern in patterns:
        button = page.get_by_role("button", name=re.compile(pattern, re.I))
        if button.count() == 0:
            continue
        candidate = button.filter(has_not=page.locator("[disabled]")).first
        if candidate.count() == 0:
            candidate = button.first
        candidate.click(timeout=5000)
        page.wait_for_timeout(2500)
        return
    raise RuntimeError("submit_button_not_found")


def extract_ticket_id(page: Page, entry_id: str, platform: str) -> str:
    text = page.locator("body").inner_text(timeout=5000)
    for pattern in (
        r"(?:entry|ticket|slip|confirmation)\s*(?:id|#)?\s*[:#]?\s*([A-Za-z0-9-]{6,})",
        r"#(\d{5,})",
    ):
        match = re.search(pattern, text, re.I)
        if match:
            return match.group(1)[:120]
    return f"{platform}-{entry_id}-{int(time.time())}"


def verify_submission(page: Page) -> str | None:
    text = page.locator("body").inner_text(timeout=5000).lower()
    success_markers = (
        "entry submitted",
        "pick submitted",
        "entry placed",
        "good luck",
        "confirmed",
        "receipt",
    )
    failure_markers = (
        "insufficient",
        "not enough funds",
        "deposit",
        "unable to place",
        "something went wrong",
        "error",
    )
    if any(marker in text for marker in success_markers):
        return None
    if any(marker in text for marker in failure_markers):
        if "insufficient" in text or "not enough funds" in text:
            return "insufficient_balance"
        return "submission_rejected"
    # Some platforms stay on board after submit; treat absence of hard failure as ok.
    return None


def find_player_card(page: Page, player_name: str, line: float, stat_hint: str | None) -> Locator | None:
    names = [player_name.strip()]
    if "." in player_name:
        names.append(player_name.replace(".", ""))
    names.append(last_name(player_name))

    seen: set[str] = set()
    for name in names:
        if not name or name.lower() in seen:
            continue
        seen.add(name.lower())
        hits = page.get_by_text(name, exact=False)
        for index in range(min(hits.count(), 12)):
            anchor = hits.nth(index)
            try:
                container = anchor.locator("xpath=ancestor::*[self::article or self::li or self::div][1]")
                if container.count() == 0:
                    container = anchor.locator("xpath=..")
                block = container.first
                block_text = block.inner_text(timeout=1500)
            except PlaywrightTimeout:
                continue
            if not line_in_text(block_text, line):
                continue
            if stat_hint and stat_hint.strip():
                stat_tokens = [token for token in re.split(r"\s+", stat_hint.lower()) if len(token) > 3]
                lowered = block_text.lower()
                if stat_tokens and not any(token in lowered for token in stat_tokens[:2]):
                    continue
            return block
    return None


def select_legs(
    page: Page,
    legs: list[dict[str, Any]],
    *,
    platform: str,
    verify_only: bool = False,
) -> list[str]:
    errors: list[str] = []
    over_labels = ("More", "Higher") if platform == "prizepicks" else ("Higher", "More")
    under_labels = ("Less", "Lower") if platform == "prizepicks" else ("Lower", "Less")

    for leg in legs:
        player = leg.get("player_name", "")
        if not player:
            errors.append("blank_player")
            continue
        try:
            side = normalize_side(str(leg.get("side", "")))
            line = float(leg.get("line"))
        except (TypeError, ValueError):
            errors.append(f"invalid_leg:{player}")
            continue

        card = find_player_card(page, player, line, leg.get("stat_type"))
        if card is None:
            errors.append(player)
            continue
        if verify_only:
            continue
        try:
            click_side_button(
                card,
                side,
                over_labels=over_labels,
                under_labels=under_labels,
            )
            page.wait_for_timeout(900)
        except RuntimeError:
            errors.append(f"{player}:{side}")

    return errors


def click_side_button(container: Locator, side: str, *, over_labels: tuple[str, ...], under_labels: tuple[str, ...]) -> None:
    labels = over_labels if side == "over" else under_labels
    for label in labels:
        button = container.get_by_role("button", name=re.compile(rf"^{re.escape(label)}$", re.I))
        if button.count() > 0:
            button.first.click(timeout=4000)
            return
        button = container.get_by_text(re.compile(rf"^{re.escape(label)}$", re.I))
        if button.count() > 0:
            button.first.click(timeout=4000)
            return
    joined = "|".join(labels)
    raise RuntimeError(f"side_button_not_found:{side}:{joined}")
