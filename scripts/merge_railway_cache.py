#!/usr/bin/env python3
"""Build railways.json from OSM cache — mainline rail only (no subway/light_rail)."""
from __future__ import annotations

import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "data" / "osm_railways_cache.json"
HIST = ROOT / "data" / "historical_railways.json"
OUT = ROOT / "public" / "data" / "railways.json"
META = ROOT / "public" / "data" / "meta.json"

MAX_OSM_SEGMENTS = 8000
MIN_LENGTH = 0.12
MAX_POINTS = 4


def load_curated() -> list[list]:
    rows = json.loads(HIST.read_text(encoding="utf-8"))
    return [
        [
            r["id"],
            r.get("name_zh") or "",
            r.get("name_en") or "",
            int(r["open_year"]),
            int(r["close_year"]) if r.get("close_year") else 0,
            r["coords"],
        ]
        for r in rows
    ]


def seg_length(coords: list) -> float:
    total = 0.0
    for i in range(1, len(coords)):
        lon1, lat1 = coords[i - 1]
        lon2, lat2 = coords[i]
        dx = (lon2 - lon1) * math.cos(math.radians((lat1 + lat2) / 2))
        dy = lat2 - lat1
        total += math.hypot(dx, dy)
    return total


def simplify(coords: list, max_pts: int = MAX_POINTS) -> list:
    if len(coords) <= max_pts:
        return coords
    step = max(1, len(coords) // max_pts)
    out = coords[::step]
    if out[-1] != coords[-1]:
        out.append(coords[-1])
    return out


def main() -> None:
    curated = load_curated()
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
            coords = row[5]
            if not coords or len(coords) < 2:
                continue
            length = seg_length(coords)
            if length < MIN_LENGTH:
                continue
            scored.append((
                length,
                [rid, row[1], row[2], row[3], row[4], simplify(coords)],
            ))

    scored.sort(key=lambda x: x[0], reverse=True)
    osm_rows = [row for _, row in scored[:MAX_OSM_SEGMENTS]]
    merged = curated + osm_rows
    OUT.write_text(json.dumps(merged, ensure_ascii=False), encoding="utf-8")

    if META.exists():
        meta = json.loads(META.read_text(encoding="utf-8"))
        meta["railway_count"] = len(merged)
        meta["osm_segment_count"] = len(osm_rows)
        META.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    print(
        f"Wrote {len(merged)} mainline segments "
        f"({len(curated)} curated + {len(osm_rows)} OSM, {len(seen)} raw ways scanned)"
    )


if __name__ == "__main__":
    main()
