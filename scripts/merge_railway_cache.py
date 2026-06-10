#!/usr/bin/env python3
"""Build railways.json from OSM cache — mainline intercity rail only."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from railway_filters import (
    is_metro_row,
    is_spur_row,
    seg_length,
    simplify_coords,
)
from region_utils import clip_coords, segment_in_china

CACHE = ROOT / "data" / "osm_railways_cache.json"
HIST = ROOT / "data" / "historical_railways.json"
OUT = ROOT / "public" / "data" / "railways.json"
META = ROOT / "public" / "data" / "meta.json"

MAX_OSM_SEGMENTS = 5500
MIN_LENGTH = 0.06
MAX_POINTS = 16


def load_curated() -> list[list]:
    rows = json.loads(HIST.read_text(encoding="utf-8"))
    out = []
    for r in rows:
        coords = clip_coords(r["coords"]) or r["coords"]
        if not segment_in_china(coords):
            continue
        out.append([
            r["id"],
            r.get("name_zh") or "",
            r.get("name_en") or "",
            int(r["open_year"]),
            int(r["close_year"]) if r.get("close_year") else 0,
            coords,
        ])
    return out


def row_tags(row: list) -> dict | None:
    if len(row) > 6 and isinstance(row[6], dict):
        return row[6]
    return None


URBAN_METRO_BOXES = [
    (116.0, 39.6, 116.7, 40.2),   # Beijing
    (121.1, 30.9, 121.9, 31.5),   # Shanghai
    (113.1, 22.9, 113.6, 23.4),   # Guangzhou
    (114.0, 22.4, 114.3, 22.6),   # Shenzhen/HK border
    (113.8, 22.2, 114.2, 22.45),  # Hong Kong Kowloon
    (104.0, 30.5, 104.3, 30.8),   # Chengdu core
]


def is_urban_short_spur(coords: list, length: float) -> bool:
    """Drop short 2-node fragments in major metro cities (often mis-tagged rail)."""
    if length > 0.22 or len(coords) > 2:
        return False
    for lon, lat in (coords[0], coords[-1]):
        for west, south, east, north in URBAN_METRO_BOXES:
            if west <= lon <= east and south <= lat <= north:
                return True
    return False


def accept_osm_row(row: list) -> tuple[bool, str]:
    name_zh, name_en = row[1] or "", row[2] or ""
    tags = row_tags(row)

    if is_metro_row(name_zh, name_en, tags):
        return False, "metro"
    if is_spur_row(name_zh, name_en, tags):
        return False, "spur"

    coords = row[5]
    if not coords or len(coords) < 2:
        return False, "empty"

    length = seg_length(coords)
    if length < MIN_LENGTH:
        return False, "short"
    if is_urban_short_spur(coords, length):
        return False, "urban_spur"
    if not segment_in_china(coords):
        return False, "outside"

    return True, "ok"


def main() -> None:
    curated = load_curated()
    stats = {"metro": 0, "spur": 0, "short": 0, "urban_spur": 0, "outside": 0, "empty": 0, "ok": 0}

    if not CACHE.exists():
        print(f"No cache at {CACHE}; keeping curated lines only.")
        OUT.write_text(json.dumps(curated, ensure_ascii=False), encoding="utf-8")
        return

    cache = json.loads(CACHE.read_text(encoding="utf-8"))
    seen: set[str] = set()
    scored: list[tuple[float, list]] = []

    for rows in cache.values():
        for row in rows:
            rid = row[0]
            if rid in seen:
                continue
            seen.add(rid)

            ok, reason = accept_osm_row(row)
            stats[reason] = stats.get(reason, 0) + 1
            if not ok:
                continue

            coords = row[5]
            if len(coords) > MAX_POINTS:
                coords = simplify_coords(coords, max_pts=MAX_POINTS)
            clipped = clip_coords(coords)
            if not clipped:
                stats["outside"] = stats.get("outside", 0) + 1
                continue
            coords = clipped
            length = seg_length(coords)
            scored.append((
                length,
                [rid, row[1], row[2], row[3], row[4], coords],
            ))

    scored.sort(key=lambda x: x[0], reverse=True)
    osm_rows = [row for _, row in scored[:MAX_OSM_SEGMENTS]]
    merged = curated + osm_rows
    OUT.write_text(json.dumps(merged, ensure_ascii=False), encoding="utf-8")

    if META.exists():
        meta = json.loads(META.read_text(encoding="utf-8"))
        meta["railway_count"] = len(merged)
        meta["osm_segment_count"] = len(osm_rows)
        meta["railway_filter"] = (
            "intercity mainline within China/TW/HK/MO — metro/spurs excluded; "
            f"geometry clipped to territory, max {MAX_POINTS} pts"
        )
        META.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    print(
        f"Wrote {len(merged)} segments ({len(curated)} curated + {len(osm_rows)} OSM)\n"
        f"  scanned {len(seen)} ways — dropped metro {stats.get('metro',0)}, "
        f"spur {stats.get('spur',0)}, short {stats.get('short',0)}, "
        f"urban_spur {stats.get('urban_spur',0)}, outside {stats.get('outside',0)}"
    )


if __name__ == "__main__":
    main()
