#!/usr/bin/env python3
"""Force EXECUTION_SHADOW_MODE and run place_dabble.py. Never taps Submit."""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ["EXECUTION_SHADOW_MODE"] = "true"
sys.path.insert(0, str(Path(__file__).resolve().parent))

from place_dabble import main

if __name__ == "__main__":
    if not os.environ.get("ENTRY_JSON"):
        print("Set ENTRY_JSON to a 2-leg payload from GET /api/paper. Shadow will not submit.")
        raise SystemExit(2)
    raise SystemExit(main())
