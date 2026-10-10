#!/usr/bin/env python3
"""Repository entry point; package installation is recommended."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from kanagawa_ruins.cli import ingest_main

if __name__ == "__main__":
    raise SystemExit(ingest_main())
