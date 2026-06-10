#!/usr/bin/env python3
"""Download and cache China outline GeoJSON locally."""
import json
import urllib.request
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "public" / "data" / "china_outline.json"
URL = (
    "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/"
    "master/geojson/ne_50m_admin_0_countries.geojson"
)

def main() -> None:
    with urllib.request.urlopen(URL, timeout=30) as resp:
        geo = json.loads(resp.read())
    features = [
        f for f in geo["features"]
        if f.get("properties", {}).get("ISO_A3") in {"CHN", "TWN", "HKG", "MAC"}
        or f.get("properties", {}).get("ADM0_A3") in {"CHN", "TWN", "HKG", "MAC"}
    ]
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps({"type": "FeatureCollection", "features": features}, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"Wrote {len(features)} features -> {OUT}")

if __name__ == "__main__":
    main()
