#!/usr/bin/env python3
"""Generate formatted Markdown bibliography tables and summaries from references.json.

Ensures that report documentation stays perfectly synchronized with the canonical
literature database without manual duplicate editing.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.storage_utils import get_verified_data_root


def format_table(refs: list[dict]) -> str:
    """Format references into a Markdown summary table."""
    lines = [
        "| 文献ID | 著者 | 発行年 | 論文名・表題 | 掲載誌 / 出版情報 | DOI / 識別子 | オープンアクセス | PDF取得状況 |",
        "|:---|:---|:---:|:---|:---|:---|:---:|:---|"
    ]

    for r in refs:
        rid = r.get("id", "-")
        authors = r.get("authors", "-")
        # Shorten authors for table readability if too long
        if len(authors) > 30 and "," in authors:
            first_auth = authors.split(",")[0].strip()
            authors_display = f"{first_auth} et al."
        else:
            authors_display = authors

        year = str(r.get("year")) if r.get("year") else "未特定"
        title = r.get("title", "-")
        journal = r.get("journal", "-")
        doi = r.get("doi")
        doi_display = f"[`{doi}`](https://doi.org/{doi})" if doi else (r.get("url") or "-")
        oa = "○" if r.get("open_access") else "×"
        pdf = r.get("pdf_status", "-")
        if "取得済" in pdf:
            pdf_display = "**取得済**"
        elif "オープンアクセス" in pdf:
            pdf_display = "手動案内"
        elif "除外" in pdf:
            pdf_display = "確定除外"
        else:
            pdf_display = "未取得"

        lines.append(
            f"| **{rid}** | {authors_display} | {year} | {title} | {journal} | {doi_display} | {oa} | {pdf_display} |"
        )

    return "\n".join(lines)


def format_details(refs: list[dict]) -> str:
    """Format references into detailed Markdown sections."""
    sections = []
    for r in refs:
        rid = r.get("id", "-")
        authors = r.get("authors", "-")
        year = str(r.get("year")) if r.get("year") else "未特定"
        title = r.get("title", "-")
        journal = r.get("journal", "-")
        doi = r.get("doi")
        url = r.get("url") or (f"https://doi.org/{doi}" if doi else "-")
        oa = "可（Open Access）" if r.get("open_access") else "不可 / 会員限定 / ペイウォール"
        pdf_status = r.get("pdf_status", "-")

        sec = [
            f"### {rid}：{authors}（{year}）",
            "",
            f"- **正式タイトル**: {title}",
            f"- **著者**: {authors}",
            f"- **掲載誌**: {journal}",
            f"- **発行年**: {year}年",
            f"- **DOI**: `{doi}`" if doi else f"- **URL / 識別子**: {url}",
            f"- **オープンアクセス**: {oa}",
            f"- **PDF保存状況**: {pdf_status}",
            f"- **研究対象地域**: {r.get('study_area', '-')}",
            f"- **使用データ**: {r.get('data_used', '-')}",
            f"- **解析手法**: {r.get('analysis_method', '-')}",
            f"- **主要な知見**: {r.get('key_findings', '-')}",
            f"- **本プロジェクトへの応用**: {r.get('project_application', '-')}",
            f"- **監査・修正メモ**: {r.get('audit_note', '-')}",
            ""
        ]
        sections.append("\n".join(sec))
    return "\n---\n\n".join(sections)


def main():
    parser = argparse.ArgumentParser(description="Generate Markdown bibliography from canonical references.json")
    parser.add_argument("--data-root", type=Path, default=None, help="Path to data root")
    parser.add_argument("--mode", choices=["table", "details", "all"], default="table", help="Output format mode")
    parser.add_argument("--output", type=Path, default=None, help="Target markdown file to write/update")
    args = parser.parse_args()

    root = args.data_root or get_verified_data_root()
    json_path = root / "literature/bibliography/references.json"
    if not json_path.is_file():
        print(f"Error: {json_path} not found", file=sys.stderr)
        sys.exit(1)

    refs = json.loads(json_path.read_text(encoding="utf-8"))

    if args.mode == "table":
        output_text = format_table(refs)
    elif args.mode == "details":
        output_text = format_details(refs)
    else:
        output_text = f"## 参考文献一覧（要約表）\n\n{format_table(refs)}\n\n---\n\n## 参考文献詳細解題\n\n{format_details(refs)}"

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output_text + "\n", encoding="utf-8")
        print(f"Wrote bibliography to {args.output}")
    else:
        print(output_text)


if __name__ == "__main__":
    main()
