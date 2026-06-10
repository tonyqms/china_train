#!/usr/bin/env python3
"""Audit suspicious station open/close years in raw CSV and built JSON."""
from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CSV = ROOT / "data" / "stations_wikidata.csv"
STATIONS_JSON = ROOT / "public" / "data" / "stations.json"
OUT = ROOT / "data" / "audit_report.json"

# Patterns that often indicate bad Wikidata dates
SUSPICIOUS = [
    {
        "id": "qtr_early_open",
        "check": lambda r: (
            (r.get("open_date") or "")[:4] in {"1927", "1928", "1929", "1930", "1931", "1932"}
            and float(r["lon"]) > 85
            and 26 <= float(r["lat"]) <= 36
        ),
        "suggest": "open_year=2006 (青藏铁路客运开通)",
    },
    {
        "id": "tibet_pre_rail",
        "check": lambda r: (
            (y := (r.get("open_date") or "")[:4])
            and y.isdigit()
            and int(y) < 2000
            and 85 <= float(r["lon"]) <= 104
            and 26 <= float(r["lat"]) <= 37
        ),
        "suggest": "verify opening — Qinghai-Tibet corridor station before modern rail era",
    },
    {
        "id": "hsr_name_early_open",
        "check": lambda r: (
            "高铁" in (r.get("name_zh") or "")
            and (y := (r.get("open_date") or "")[:4])
            and y.isdigit()
            and int(y) < 2003
        ),
        "suggest": "verify opening — 高铁站 unlikely before CRH era",
    },
]


def audit_csv() -> list[dict]:
    if not CSV.exists():
        return []
    rows = list(csv.DictReader(CSV.open(encoding="utf-8-sig")))
    issues = []
    for r in rows:
        name = f"{r.get('name_zh', '')} / {r.get('name_en', '')}"
        for rule in SUSPICIOUS:
            if rule["check"](r):
                issues.append({
                    "source": "csv",
                    "id": r["id"],
                    "name": name,
                    "issue": rule["id"],
                    "open_date": r.get("open_date"),
                    "close_date": r.get("close_date"),
                    "suggest": rule["suggest"],
                })
                break
    return issues, rows


def audit_built(issues: list[dict]) -> list[dict]:
    if not STATIONS_JSON.exists():
        return issues
    rows = json.loads(STATIONS_JSON.read_text(encoding="utf-8"))
    by_id = {r[0]: r for r in rows}

    checks = [
        ("Q15402249", "open_year", 2006, "马乡站"),
        ("Q798114", "close_year", 2016, "清华园站"),
    ]
    for qid, field, expected, label in checks:
        if qid not in by_id:
            issues.append({"source": "built", "id": qid, "issue": "missing", "name": label})
            continue
        r = by_id[qid]
        idx = 5 if field == "open_year" else 6
        actual = r[idx]
        if actual != expected:
            issues.append({
                "source": "built",
                "id": qid,
                "name": label,
                "issue": f"wrong_{field}",
                "expected": expected,
                "actual": actual,
            })

    # Still-visible closed stations: has name hint of closure but close_year=0
    for r in rows:
        zh = r[1] or ""
        if "废弃" in zh or "旧址" in zh:
            if r[6] == 0:
                issues.append({
                    "source": "built",
                    "id": r[0],
                    "name": zh,
                    "issue": "abandoned_name_no_close",
                    "suggest": "add close_year in station_corrections.json",
                })

    return issues


def main() -> None:
    csv_issues, csv_rows = audit_csv()
    all_issues = audit_built(csv_issues)
    year_counts = Counter(
        (r.get("open_date") or "")[:4] for r in csv_rows if r.get("open_date")
    )
    report = {
        "csv_issue_count": len(csv_issues),
        "total_issue_count": len(all_issues),
        "top_open_years": year_counts.most_common(15),
        "issues": all_issues[:300],
    }
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"CSV flags: {len(csv_issues)}, total: {len(all_issues)} -> {OUT}")


if __name__ == "__main__":
    main()
