#!/usr/bin/env python3
"""Build compact JSON datasets — intercity rail hubs only (no metro/subway)."""
from __future__ import annotations

import csv
import json
import re
from datetime import date
from pathlib import Path

from date_utils import (
    apply_corrections,
    load_corrections,
    parse_year,
    resolve_close_years,
    resolve_open_years,
)

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
OUT = ROOT / "public" / "data"
START_YEAR = 1876
END_YEAR = date.today().year

METRO_NAME = re.compile(
    r"地铁|地鐵|轨道交通|軌道交通|轻轨|輕軌|有轨|有軌|电车|電車|"
    r"捷运|捷運|"
    r"monorail|maglev|磁浮|磁悬浮|"
    r"\bsubway\b|\bmetro\b|\bmtr\b|\bbts\b|\bmrt\b|"
    r"airport express|机场快线|機場快線|"
    r"apm|people.?s mover",
    re.I,
)

INTERCITY_HINT = re.compile(
    r"铁路|鐵路|高铁|高鐵|动车|動車|城际|城際|客运|客運|"
    r"railway|intercity|high[- ]speed|hsr|train station|"
    r"火车站|火車站|动车站|動車站|高铁站|高鐵站",
    re.I,
)


def in_china_bbox(lat: float, lon: float) -> bool:
    return 73 <= lon <= 135 and 17.5 <= lat <= 54.5


def is_hk_macau_urban(lat: float, lon: float) -> bool:
    if 22.15 <= lat <= 22.56 and 113.83 <= lon <= 114.41:
        return True
    if 22.10 <= lat <= 22.22 and 113.52 <= lon <= 113.60:
        return True
    return False


def is_intercity_station(s: dict) -> bool:
    zh = s.get("name_zh") or ""
    en = s.get("name_en") or ""
    text = f"{zh} {en}"

    if METRO_NAME.search(text):
        return False

    lat, lon = float(s["lat"]), float(s["lon"])

    if is_hk_macau_urban(lat, lon):
        if INTERCITY_HINT.search(text):
            return True
        if en.lower().endswith(" station") and "rail" not in en.lower():
            return False
        if not INTERCITY_HINT.search(text):
            return False

    if en.lower().endswith(" station") and not INTERCITY_HINT.search(en):
        if "railway" not in en.lower() and "rail" not in en.lower():
            if not zh or len(zh) <= 4:
                return False

    return True


def _collect_dates(row: dict, key: str, raw_key: str) -> list[int]:
    years: list[int] = []
    primary = parse_year(row.get(key))
    if primary:
        years.append(primary)
    raw = row.get(raw_key) or ""
    for part in raw.split(";"):
        if y := parse_year(part.strip()):
            years.append(y)
    return years


def load_stations() -> list[dict]:
    path = DATA / "stations_wikidata.csv"
    corrections, rules = load_corrections()
    by_id: dict[str, dict] = {}
    dropped = 0

    with path.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            lat = float(row["lat"])
            lon = float(row["lon"])
            if not in_china_bbox(lat, lon):
                continue
            sid = row["id"]
            open_years = _collect_dates(row, "open_date", "open_dates_raw")
            close_years = _collect_dates(row, "close_date", "close_dates_raw")
            open_y = resolve_open_years(open_years)
            close_y = resolve_close_years(close_years)

            candidate = {
                "id": sid,
                "name_zh": row.get("name_zh") or "",
                "name_en": row.get("name_en") or "",
                "lat": lat,
                "lon": lon,
                "open_year": open_y,
                "close_year": close_y,
            }
            if not is_intercity_station(candidate):
                dropped += 1
                continue

            if sid not in by_id:
                by_id[sid] = candidate
            else:
                cur = by_id[sid]
                merged_open = resolve_open_years(
                    [y for y in [cur["open_year"], open_y] if y]
                )
                merged_close = resolve_close_years(
                    [y for y in [cur["close_year"], close_y] if y]
                )
                cur["open_year"] = merged_open
                cur["close_year"] = merged_close
                if not cur["name_en"] and row.get("name_en"):
                    cur["name_en"] = row["name_en"]
                if not cur["name_zh"] and row.get("name_zh"):
                    cur["name_zh"] = row["name_zh"]

    stations = []
    for s in by_id.values():
        if not s["open_year"]:
            continue
        stations.append(apply_corrections(s, corrections, rules))

    hist = json.loads((DATA / "historical_stations.json").read_text(encoding="utf-8"))
    stations.extend(hist)
    print(f"  filtered out {dropped} metro/urban-rail stations")
    if corrections or rules:
        print(f"  applied {len(corrections)} manual corrections, {len(rules)} date rules")
    return stations


def load_railways() -> list[dict]:
    rail_path = OUT / "railways.json"
    if rail_path.exists():
        rows = json.loads(rail_path.read_text(encoding="utf-8"))
        curated_ids = {
            r["id"]
            for r in json.loads(
                (DATA / "historical_railways.json").read_text(encoding="utf-8")
            )
        }
        return [
            {
                "id": r[0],
                "name_zh": r[1],
                "name_en": r[2],
                "open_year": r[3],
                "close_year": r[4] or None,
                "coords": r[5],
            }
            for r in rows
            if str(r[0]).startswith("osm-") or r[0] in curated_ids
        ]
    return json.loads((DATA / "historical_railways.json").read_text(encoding="utf-8"))


def compact_station(s: dict) -> list:
    return [
        s["id"],
        s.get("name_zh") or "",
        s.get("name_en") or "",
        round(float(s["lon"]), 4),
        round(float(s["lat"]), 4),
        int(s["open_year"]),
        int(s["close_year"]) if s.get("close_year") else 0,
    ]


def compact_railway(r: dict) -> list:
    return [
        r["id"],
        r.get("name_zh") or "",
        r.get("name_en") or "",
        int(r["open_year"]),
        int(r["close_year"]) if r.get("close_year") else 0,
        r["coords"],
    ]


def histogram(stations: list[dict], railways: list[dict]) -> list[dict]:
    bins = []
    for y in range(START_YEAR, END_YEAR + 1):
        bins.append(
            {
                "year": y,
                "stations_open": sum(1 for s in stations if s.get("open_year") == y),
                "stations_close": sum(1 for s in stations if s.get("close_year") == y),
                "railways_open": sum(1 for r in railways if r.get("open_year") == y),
                "railways_close": sum(1 for r in railways if r.get("close_year") == y),
            }
        )
    return bins


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    stations = load_stations()
    railways = load_railways()

    meta = {
        "start_year": START_YEAR,
        "end_year": END_YEAR,
        "station_count": len(stations),
        "railway_count": len(railways),
        "first_line_zh": "吴淞铁路（上海—吴淞）",
        "first_line_en": "Wusong Railway (Shanghai–Wusong)",
        "first_line_year": 1876,
        "filter": "intercity rail only — metro/subway/light rail excluded",
        "sources": [
            "Wikidata (CC0): intercity railway stations — mainland (Q148) + Taiwan (Q865)",
            "OpenStreetMap railway=rail main lines",
            "Curated historical railways: Wusong 1876, Tangxu 1881, Jinghan 1906, etc.",
            "Manual date corrections: data/station_corrections.json",
        ],
        "generated_at": date.today().isoformat(),
    }

    (OUT / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUT / "stations.json").write_text(
        json.dumps([compact_station(s) for s in stations], ensure_ascii=False),
        encoding="utf-8",
    )
    if not (OUT / "railways.json").exists():
        (OUT / "railways.json").write_text(
            json.dumps([compact_railway(r) for r in railways], ensure_ascii=False),
            encoding="utf-8",
        )
    (OUT / "histogram.json").write_text(
        json.dumps(histogram(stations, railways), ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"Built {len(stations)} intercity stations, {len(railways)} railway segments -> {OUT}")


if __name__ == "__main__":
    main()
