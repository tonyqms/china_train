#!/usr/bin/env python3
"""Fetch OSM railway=rail segments via curl (avoids urllib 403/406 issues).

After fetching, run:
  python scripts/merge_railway_cache.py
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / "data" / "osm_railways_cache.json"
HIST = ROOT / "data" / "historical_railways.json"

ENDPOINT = "https://overpass.kumi.systems/api/interpreter"
USER_AGENT = "ChinaRailViz/1.0 (local research; https://github.com/local/china-rail-viz)"

LAT_BANDS = [18, 27, 33, 39, 45, 54]
LON_BANDS = [73, 88, 103, 118, 135]


def parse_year(value: str | None) -> int | None:
    if not value:
        return None
    m = re.search(r"(\d{4})", value)
    return int(m.group(1)) if m else None


def simplify(coords: list, max_pts: int = 8) -> list:
    if len(coords) <= max_pts:
        return coords
    step = max(1, len(coords) // max_pts)
    out = coords[::step]
    if out[-1] != coords[-1]:
        out.append(coords[-1])
    return out


def way_to_row(el: dict) -> list | None:
    if el.get("type") != "way" or not el.get("geometry"):
        return None
    coords = [[round(p["lon"], 3), round(p["lat"], 3)] for p in el["geometry"]]
    if len(coords) < 2:
        return None
    tags = el.get("tags", {})
    open_y = parse_year(tags.get("start_date") or tags.get("opening_date"))
    close_y = parse_year(tags.get("end_date"))
    if tags.get("railway") in {"abandoned", "razed"}:
        close_y = close_y or 1990
        open_y = open_y or 1950
    if not open_y:
        open_y = 2008 if tags.get("highspeed") == "yes" else 1950
    return [
        f"osm-{el['id']}",
        tags.get("name:zh") or tags.get("name") or "",
        tags.get("name:en") or tags.get("name") or "",
        open_y,
        close_y or 0,
        simplify(coords),
    ]


def curl_post(query: str) -> dict:
    curl = shutil.which("curl") or shutil.which("curl.exe")
    if not curl:
        raise RuntimeError("curl not found — install curl or use merge_railway_cache.py")

    proc = subprocess.run(
        [
            curl,
            "-sS",
            "-L",
            "--compressed",
            "-A",
            USER_AGENT,
            "-H",
            "Accept: application/json",
            "-H",
            "Content-Type: application/x-www-form-urlencoded",
            "--data-urlencode",
            f"data={query}",
            ENDPOINT,
        ],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or f"curl exit {proc.returncode}")
    text = proc.stdout.strip()
    if text.startswith("<"):
        raise RuntimeError("Overpass returned HTML (blocked or rate-limited)")
    return json.loads(text)


def tiles() -> list[tuple[float, float, float, float]]:
    out = []
    for i in range(len(LAT_BANDS) - 1):
        for j in range(len(LON_BANDS) - 1):
            out.append((LAT_BANDS[i], LON_BANDS[j], LAT_BANDS[i + 1], LON_BANDS[j + 1]))
    return out


def main() -> None:
    cache: dict[str, list] = {}
    if CACHE.exists():
        cache = json.loads(CACHE.read_text(encoding="utf-8"))

    for idx, (south, west, north, east) in enumerate(tiles()):
        key = f"{south}_{west}_{north}_{east}"
        if key in cache and cache[key]:
            print(f"[{idx + 1}/{len(tiles())}] {key} cache hit ({len(cache[key])})", flush=True)
            continue

        query = (
            f"[out:json][timeout:55];"
            f'way["railway"="rail"]({south},{west},{north},{east});'
            "out tags geom;"
        )
        print(f"[{idx + 1}/{len(tiles())}] {key} fetching ...", flush=True)
        try:
            payload = curl_post(query)
            rows = [r for el in payload.get("elements", []) if (r := way_to_row(el))]
            cache[key] = rows
            CACHE.parent.mkdir(parents=True, exist_ok=True)
            CACHE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
            print(f"  ok: {len(rows)} ways", flush=True)
        except Exception as exc:
            print(f"  FAILED: {exc}", flush=True)
        time.sleep(2)

    print("\nDone caching tiles.", flush=True)
    print("Run: python scripts/merge_railway_cache.py", flush=True)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
