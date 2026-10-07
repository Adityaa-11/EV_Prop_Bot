"""Android / Dabble hardware and UI helpers. No unofficial submit API."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from typing import Any

DABBLE_PACKAGE = "com.dabblesports.us_fantasy"
MIN_ANDROID_VERSION = 7.0
APPIUM_SERVER_URL = os.getenv("APPIUM_SERVER_URL", "http://127.0.0.1:4723")

LOGIN_MARKERS = ("log in", "sign in", "create account", "sign up")
SEARCH_LABELS = ("search", "find player", "search players")
OVER_LABELS = ("More", "Over", "Higher")
UNDER_LABELS = ("Less", "Under", "Lower")
SUBMIT_LABELS = ("Place entry", "Submit entry", "Confirm entry", "Place pick", "All-In")
DISMISS_LABELS = ("Not now", "Skip", "Close", "Got it", "Allow", "While using the app")


def player_key(name: str) -> str:
    return " ".join((name or "").split()).lower()


def dabble_side_label(side: str) -> str:
    value = (side or "").strip().upper()
    if value in {"OVER", "MORE", "HIGHER"}:
        return "More"
    if value in {"UNDER", "LESS", "LOWER"}:
        return "Less"
    raise ValueError(f"unsupported_side:{side}")


def parse_android_release(raw: str) -> float | None:
    match = re.search(r"(\d+(?:\.\d+)?)", raw or "")
    if not match:
        return None
    try:
        return float(match.group(1))
    except ValueError:
        return None


def adb_bin() -> str:
    return os.getenv("ADB_BIN") or shutil.which("adb") or "adb"


def run_adb(args: list[str], timeout: int = 15) -> tuple[int, str, str]:
    command = [adb_bin(), *args]
    try:
        proc = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError:
        return 127, "", "adb_not_found"
    except subprocess.TimeoutExpired:
        return 124, "", "adb_timeout"
    return proc.returncode, proc.stdout.strip(), proc.stderr.strip()


def connected_devices() -> list[str]:
    code, stdout, _stderr = run_adb(["devices"])
    if code != 0:
        return []
    devices: list[str] = []
    for line in stdout.splitlines()[1:]:
        parts = line.split()
        if len(parts) >= 2 and parts[1] == "device":
            devices.append(parts[0])
    return devices


def hardware_report() -> dict[str, Any]:
    """Return a Mini-side gate report. Exit 0 only when a real phone is ready."""
    report: dict[str, Any] = {
        "ok": False,
        "adb": adb_bin(),
        "devices": [],
        "android_version": None,
        "dabble_installed": False,
        "errors": [],
        "checklist": [
            "Android 7.0+ with Google Play Store",
            "Dabble installed from Play Store (com.dabblesports.us_fantasy)",
            "In Georgia: Dabble shows real-money All-In 2-pick",
            "USB debugging on, stay awake while charging, no lock PIN",
            "Location high accuracy, Dabble location allowed",
            "Phone left plugged into the Atlanta Mac Mini",
            "Not a Kindle Fire, iPhone 4s, or emulator",
        ],
    }
    devices = connected_devices()
    report["devices"] = devices
    if not devices:
        report["errors"].append("no_android_device")
        return report

    udid = os.getenv("ANDROID_UDID") or devices[0]
    report["udid"] = udid
    _code, release, _err = run_adb(["-s", udid, "shell", "getprop", "ro.build.version.release"])
    version = parse_android_release(release)
    report["android_version"] = version
    if version is None or version < MIN_ANDROID_VERSION:
        report["errors"].append(f"android_version_too_low:{release or 'unknown'}")

    _code, pkg, _err = run_adb(["-s", udid, "shell", "pm", "path", DABBLE_PACKAGE])
    report["dabble_installed"] = pkg.startswith("package:")
    if not report["dabble_installed"]:
        report["errors"].append("dabble_not_installed")

    report["ok"] = not report["errors"]
    return report


def appium_options() -> dict[str, Any]:
    options = {
        "platformName": "Android",
        "automationName": "UiAutomator2",
        "appPackage": DABBLE_PACKAGE,
        "noReset": True,
        "autoGrantPermissions": True,
        "newCommandTimeout": 120,
        "dontStopAppOnReset": True,
    }
    udid = os.getenv("ANDROID_UDID")
    if udid:
        options["udid"] = udid
    device_name = os.getenv("ANDROID_DEVICE_NAME")
    if device_name:
        options["deviceName"] = device_name
    return options
