#!/usr/bin/env python3
import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from cadcore.runner import main

if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
