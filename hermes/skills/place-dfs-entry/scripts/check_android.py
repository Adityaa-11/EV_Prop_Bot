#!/usr/bin/env python3
"""Mini hardware gate: USB Android + Dabble Play Store install. No submit."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from dabble_android import hardware_report  # noqa: E402


def main() -> int:
    report = hardware_report()
    print(json.dumps(report, indent=2))
    if report.get("ok"):
        print("Android hardware gate passed. Leave the phone plugged in at the Mini.")
        return 0
    print("Android hardware gate failed. Fix the checklist before shadow placing.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
