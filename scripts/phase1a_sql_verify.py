#!/usr/bin/env python3
"""Run the repository's real-data SQL checks and generate metadata summaries."""

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from kanagawa_ruins.qa.sql import validate_sql
from kanagawa_ruins.qa.report import summarize_layers, layer_table

if __name__ == "__main__":
    result = validate_sql()
    summary = summarize_layers()
    for name, value in [
        ("phase1a_sql_validation.json", result),
        ("phase1a_layers.json", summary),
    ]:
        (ROOT / "reports" / name).write_text(
            json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    (ROOT / "reports" / "phase1a_layers.md").write_text(
        "# Phase 1-A 生成レイヤー一覧\n\n" + layer_table(summary), encoding="utf-8"
    )
    print(
        json.dumps(
            {k: v for k, v in summary.items() if k != "layers"}, ensure_ascii=False
        )
    )
