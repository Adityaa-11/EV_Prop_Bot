#!/usr/bin/env bash
# Mac Mini: ADB + Appium for the spare Android. Does not enable live submit.
set -euo pipefail

echo "Dabble Android Mini setup (shadow only)"
echo "Requires: Android 7+ with Play Store Dabble, GPS in Georgia, USB debugging, no lock PIN."

if ! command -v adb >/dev/null 2>&1; then
  if command -v brew >/dev/null 2>&1; then
    echo "Installing android-platform-tools via Homebrew..."
    brew install --cask android-platform-tools || brew install android-platform-tools
  else
    echo "Install Android platform-tools (adb) then re-run."
    exit 1
  fi
fi

python3 -m pip install -r "$(dirname "$0")/requirements.txt"

if command -v npm >/dev/null 2>&1; then
  if ! command -v appium >/dev/null 2>&1; then
    echo "Installing Appium 2..."
    npm install -g appium
  fi
  appium driver install uiautomator2 >/dev/null 2>&1 || true
else
  echo "npm not found. Install Node, then: npm install -g appium && appium driver install uiautomator2"
fi

python3 "$(dirname "$0")/check_android.py"
echo
echo "Next:"
echo "  1. Log into Dabble once on the phone in Atlanta (All-In visible)."
echo "  2. Start Appium: appium --port 4723"
echo "  3. Shadow only: EXECUTION_SHADOW_MODE=true python3 run_executor.py"
echo "Do not set LIVE_EXECUTION_ENABLED=true until a shadow screenshot finds both legs."
