#!/usr/bin/env python3
"""Drive the official Dabble Android app from ENTRY_JSON. Hermes does not change EV."""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from dfs_common import (
    artifacts_dir,
    fail,
    format_line,
    is_shadow_mode,
    last_name,
    line_in_text,
    load_entry,
    normalize_side,
    skip_shadow,
    stake_amount,
    submit_ok,
)

from dabble_android import (
    APPIUM_SERVER_URL,
    DABBLE_PACKAGE,
    DISMISS_LABELS,
    LOGIN_MARKERS,
    OVER_LABELS,
    SEARCH_LABELS,
    SUBMIT_LABELS,
    UNDER_LABELS,
    appium_options,
    dabble_side_label,
    hardware_report,
)


def screenshot_driver(driver: Any, entry_id: str, suffix: str) -> Path:
    path = artifacts_dir() / f"{entry_id}-dabble-{suffix}.png"
    driver.get_screenshot_as_file(str(path))
    return path


def wait_click_text(driver: Any, labels: tuple[str, ...] | list[str], timeout: float = 4.0) -> bool:
    from appium.webdriver.common.appiumby import AppiumBy

    deadline = time.time() + timeout
    while time.time() < deadline:
        page = _page_text(driver)
        for label in labels:
            if label.lower() not in page.lower() and not _has_text(driver, label):
                continue
            try:
                el = driver.find_element(
                    AppiumBy.ANDROID_UIAUTOMATOR,
                    f'new UiSelector().textContains("{label}")',
                )
                el.click()
                time.sleep(0.6)
                return True
            except Exception:
                continue
        time.sleep(0.3)
    return False


def _has_text(driver: Any, label: str) -> bool:
    from appium.webdriver.common.appiumby import AppiumBy

    try:
        driver.find_element(
            AppiumBy.ANDROID_UIAUTOMATOR,
            f'new UiSelector().textContains("{label}")',
        )
        return True
    except Exception:
        return False


def _page_text(driver: Any) -> str:
    try:
        return driver.page_source or ""
    except Exception:
        return ""


def dismiss_noise(driver: Any) -> None:
    for _ in range(3):
        if not wait_click_text(driver, DISMISS_LABELS, timeout=1.5):
            break


def ensure_logged_in(driver: Any) -> str | None:
    text = _page_text(driver).lower()
    if any(marker in text for marker in LOGIN_MARKERS):
        if "all-in" not in text and "more" not in text:
            return "login_required"
    return None


def open_search(driver: Any) -> None:
    from appium.webdriver.common.appiumby import AppiumBy

    wait_click_text(driver, SEARCH_LABELS, timeout=3)
    try:
        field = driver.find_element(AppiumBy.CLASS_NAME, "android.widget.EditText")
        field.click()
    except Exception:
        pass


def type_search(driver: Any, query: str) -> None:
    from appium.webdriver.common.appiumby import AppiumBy

    try:
        field = driver.find_element(AppiumBy.CLASS_NAME, "android.widget.EditText")
        field.clear()
        field.send_keys(query)
        time.sleep(1.2)
    except Exception as exc:
        raise RuntimeError(f"search_unavailable:{query}") from exc


def find_player_source(driver: Any, player: str, line: float, stat_hint: str | None) -> str | None:
    names = [player.strip(), last_name(player)]
    source = _page_text(driver)
    lowered = source.lower()
    stat_ok = True
    if stat_hint:
        tokens = [token for token in stat_hint.lower().split() if len(token) > 3]
        if tokens:
            stat_ok = any(token in lowered for token in tokens[:2])
    for name in names:
        if name and name.lower() in lowered and line_in_text(source, line) and stat_ok:
            return source
    return None


def tap_side(driver: Any, side: str) -> bool:
    labels = OVER_LABELS if side == "over" else UNDER_LABELS
    return wait_click_text(driver, labels, timeout=4)


def set_stake(driver: Any, amount: float) -> None:
    from appium.webdriver.common.appiumby import AppiumBy

    stake_text = format_line(amount) if amount == int(amount) else f"{amount:g}"
    try:
        fields = driver.find_elements(AppiumBy.CLASS_NAME, "android.widget.EditText")
        for field in fields:
            try:
                field.clear()
                field.send_keys(stake_text)
                time.sleep(0.4)
                return
            except Exception:
                continue
    except Exception:
        pass
    wait_click_text(driver, (f"${stake_text}", stake_text), timeout=2)


def click_submit(driver: Any) -> None:
    if not wait_click_text(driver, SUBMIT_LABELS, timeout=6):
        raise RuntimeError("submit_button_not_found")


def select_legs(driver: Any, legs: list[dict[str, Any]], *, verify_only: bool) -> list[str]:
    errors: list[str] = []
    for index, leg in enumerate(legs):
        player = str(leg.get("player_name") or "")
        if not player:
            errors.append("blank_player")
            continue
        try:
            side = normalize_side(str(leg.get("side", "")))
            line = float(leg.get("line"))
        except (TypeError, ValueError):
            errors.append(f"invalid_leg:{player}")
            continue
        if index == 0:
            open_search(driver)
        type_search(driver, player)
        source = find_player_source(driver, player, line, leg.get("stat_type"))
        if source is None:
            errors.append(player)
            continue
        if verify_only:
            continue
        if not tap_side(driver, side):
            errors.append(f"{player}:{dabble_side_label(leg.get('side', ''))}")
    return errors


def connect_driver() -> Any:
    try:
        from appium import webdriver
        from appium.options.android import UiAutomator2Options
    except ImportError as exc:
        raise RuntimeError(
            "appium_not_installed; pip install Appium-Python-Client"
        ) from exc

    options = UiAutomator2Options()
    for key, value in appium_options().items():
        options.set_capability(key, value)
    return webdriver.Remote(APPIUM_SERVER_URL, options=options)


def main() -> int:
    entry = load_entry()
    shadow = is_shadow_mode()
    entry_id = str(entry.get("id") or "entry")
    legs = entry.get("legs") or []
    if len(legs) < 2:
        return fail("entry requires 2 legs")

    gate = hardware_report()
    if not gate.get("ok"):
        return fail("android_hardware_gate:" + ",".join(gate.get("errors") or ["unknown"]))

    driver = None
    try:
        driver = connect_driver()
        driver.activate_app(DABBLE_PACKAGE)
        time.sleep(2.5)
        dismiss_noise(driver)

        auth_error = ensure_logged_in(driver)
        if auth_error:
            shot = screenshot_driver(driver, entry_id, "auth")
            return fail(auth_error, screenshot=shot)

        missing = select_legs(driver, legs, verify_only=True)
        shot = screenshot_driver(driver, entry_id, "preflight")
        if missing:
            return fail(f"players_not_found:{','.join(missing)}", screenshot=shot)

        if shadow:
            return skip_shadow(shot)

        missing = select_legs(driver, legs, verify_only=False)
        if missing:
            shot = screenshot_driver(driver, entry_id, "missing")
            return fail(f"players_not_found:{','.join(missing)}", screenshot=shot)

        set_stake(driver, stake_amount(entry))
        screenshot_driver(driver, entry_id, "pre-submit")
        click_submit(driver)
        post_shot = screenshot_driver(driver, entry_id, "post-submit")
        return submit_ok(
            ticket_id=f"dabble-{entry_id}-{int(time.time())}",
            screenshot=post_shot,
        )
    except Exception as exc:  # noqa: BLE001
        shot = None
        if driver is not None:
            try:
                shot = screenshot_driver(driver, entry_id, "error")
            except Exception:
                shot = None
        return fail(str(exc), screenshot=shot)
    finally:
        if driver is not None:
            try:
                driver.quit()
            except Exception:
                pass


if __name__ == "__main__":
    raise SystemExit(main())
