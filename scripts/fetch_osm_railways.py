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
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from railway_filters import is_metro_row, is_spur_row, simplify_coords
from region_utils import clip_coords

CACHE = ROOT / "data" / "osm_railways_cache.json"
HIST = ROOT / "data" / "historical_railways.json"

ENDPOINTS = [
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass-api.de/api/interpreter",
]
USER_AGENT = "ChinaRailViz/1.2 (local research; https://github.com/local/china-rail-viz)"

CURL_TIMEOUT = 300
OVERPASS_TIMEOUT = 180
MAX_RETRIES = 3
MAX_SPLIT_DEPTH = 3
MIN_SPLIT_DEG = 2.5

LAT_BANDS = [18, 27, 33, 39, 45, 54]
LON_BANDS = [73, 88, 103, 118, 135]


def parse_year(value: str | None) -> int | None:
    if not value:
        return None
    m = re.search(r"(\d{4})", value)
    return int(m.group(1)) if m else None


def tile_key(south: float, west: float, north: float, east: float) -> str:
    def part(x: float) -> str:
        return str(int(x)) if float(x).is_integer() else f"{x:.1f}"

    return f"{part(south)}_{part(west)}_{part(north)}_{part(east)}"


def way_to_row(el: dict) -> list | None:
    if el.get("type") != "way" or not el.get("geometry"):
        return None
    coords = [[round(p["lon"], 4), round(p["lat"], 4)] for p in el["geometry"]]
    if len(coords) < 2:
        return None

    tags = el.get("tags", {})
    name_zh = tags.get("name:zh") or tags.get("name") or ""
    name_en = tags.get("name:en") or tags.get("name") or ""

    if is_metro_row(name_zh, name_en, tags):
        return None
    if is_spur_row(name_zh, name_en, tags):
        return None

    open_y = parse_year(tags.get("start_date") or tags.get("opening_date"))
    close_y = parse_year(tags.get("end_date"))
    if tags.get("railway") in {"abandoned", "razed"}:
        close_y = close_y or 1990
        open_y = open_y or 1950
    if not open_y:
        open_y = 2008 if tags.get("highspeed") == "yes" else 1950

    coords = simplify_coords(coords, max_pts=20, epsilon=0.012)
    coords = clip_coords(coords)
    if not coords:
        return None

    return [
        f"osm-{el['id']}",
        name_zh,
        name_en,
        open_y,
        close_y or 0,
        coords,
        {
            "usage": tags.get("usage", ""),
            "service": tags.get("service", ""),
            "operator": tags.get("operator") or tags.get("operator:zh") or "",
            "highspeed": tags.get("highspeed", ""),
        },
    ]


def tile_query(south: float, west: float, north: float, east: float) -> str:
    return (
        f"[out:json][timeout:{OVERPASS_TIMEOUT}];"
        f'way["railway"="rail"]'
        f'["usage"!~"industrial|military|test|tourism|freight"]'
        f'["service"!~"yard|siding|spur|crossover|headshunt|escape"]'
        f"({south},{west},{north},{east});"
        "out tags geom;"
    )


def curl_post(query: str, endpoint: str) -> dict:
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
            endpoint,
        ],
        capture_output=True,
        timeout=CURL_TIMEOUT,
        check=False,
    )
    if proc.returncode != 0:
        err = (proc.stderr or b"").decode("utf-8", errors="replace").strip()
        raise RuntimeError(err or f"curl exit {proc.returncode}")
    raw = proc.stdout or b""
    text = raw.decode("utf-8", errors="replace").strip()
    if not text:
        raise RuntimeError("curl returned empty response")
    if text.startswith("<"):
        raise RuntimeError("Overpass returned HTML (blocked or rate-limited)")
    return json.loads(text)


def fetch_bbox(
    south: float,
    west: float,
    north: float,
    east: float,
) -> list:
    query = tile_query(south, west, north, east)
    last_err: Exception | None = None

    for attempt in range(MAX_RETRIES):
        endpoint = ENDPOINTS[attempt % len(ENDPOINTS)]
        try:
            payload = curl_post(query, endpoint)
            return [r for el in payload.get("elements", []) if (r := way_to_row(el))]
        except (subprocess.TimeoutExpired, TimeoutError) as exc:
            last_err = exc
            print(f"    timeout (attempt {attempt + 1}/{MAX_RETRIES})", flush=True)
        except Exception as exc:
            last_err = exc
            print(f"    error (attempt {attempt + 1}/{MAX_RETRIES}): {exc}", flush=True)
        time.sleep(3 + attempt * 2)

    raise RuntimeError(str(last_err) if last_err else "fetch failed")


def can_split(south: float, west: float, north: float, east: float, depth: int) -> bool:
    if depth >= MAX_SPLIT_DEPTH:
        return False
    return (north - south) > MIN_SPLIT_DEG or (east - west) > MIN_SPLIT_DEG


def fetch_tile(
    cache: dict[str, list],
    south: float,
    west: float,
    north: float,
    east: float,
    depth: int = 0,
    label: str = "",
) -> int:
    key = tile_key(south, west, north, east)
    if key in cache and cache[key]:
        print(f"{label} {key} cache hit ({len(cache[key])})", flush=True)
        return len(cache[key])

    print(f"{label} {key} fetching ...", flush=True)
    try:
        rows = fetch_bbox(south, west, north, east)
        cache[key] = rows
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        CACHE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
        print(f"  ok: {len(rows)} ways", flush=True)
        return len(rows)
    except Exception as exc:
        if not can_split(south, west, north, east, depth):
            print(f"  FAILED (no split): {exc}", flush=True)
            return 0

        print(f"  splitting tile after: {exc}", flush=True)
        mid_lat = (south + north) / 2
        mid_lon = (west + east) / 2
        total = 0
        sub_label = label.replace("]", "/4]")
        for s, n in ((south, mid_lat), (mid_lat, north)):
            for w, e in ((west, mid_lon), (mid_lon, east)):
                total += fetch_tile(cache, s, w, n, e, depth + 1, sub_label)
        return total


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

    all_tiles = tiles()
    for idx, (south, west, north, east) in enumerate(all_tiles):
        fetch_tile(
            cache,
            south,
            west,
            north,
            east,
            depth=0,
            label=f"[{idx + 1}/{len(all_tiles)}]",
        )
        time.sleep(2)

    print("\nDone caching tiles.", flush=True)
    print("Run: python scripts/merge_railway_cache.py", flush=True)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
