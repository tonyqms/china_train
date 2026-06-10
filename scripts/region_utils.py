"""Geographic bounds for China + Taiwan + HK + Macau."""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTLINE = ROOT / "public" / "data" / "china_outline.json"

# Fallback if outline missing
FALLBACK_BBOX = (73.0, 17.5, 135.0, 54.5)  # min_lon, min_lat, max_lon, max_lat


@lru_cache(maxsize=1)
def _load_polygons() -> tuple[tuple, ...]:
    if not OUTLINE.exists():
        return tuple()
    geo = json.loads(OUTLINE.read_text(encoding="utf-8"))
    polys: list[tuple] = []
    for feat in geo.get("features", []):
        geom = feat.get("geometry") or {}
        gtype = geom.get("type")
        coords = geom.get("coordinates") or []
        if gtype == "Polygon":
            polys.append(_poly_rings(coords))
        elif gtype == "MultiPolygon":
            for poly in coords:
                polys.append(_poly_rings(poly))
    return tuple(polys)


def _poly_rings(poly_coords: list) -> tuple:
    rings = []
    for ring in poly_coords:
        rings.append(tuple((float(p[0]), float(p[1])) for p in ring))
    return tuple(rings)


def _point_in_ring(lon: float, lat: float, ring: tuple) -> bool:
    inside = False
    n = len(ring)
    if n < 3:
        return False
    j = n - 1
    for i in range(n):
        xi, yi = ring[i]
        xj, yj = ring[j]
        if ((yi > lat) != (yj > lat)) and (
            lon < (xj - xi) * (lat - yi) / (yj - yi + 1e-15) + xi
        ):
            inside = not inside
        j = i
    return inside


def point_in_china(lon: float, lat: float) -> bool:
    polys = _load_polygons()
    if not polys:
        w, s, e, n = FALLBACK_BBOX
        return w <= lon <= e and s <= lat <= n
    for rings in polys:
        if not rings:
            continue
        if _point_in_ring(lon, lat, rings[0]):
            in_hole = any(_point_in_ring(lon, lat, hole) for hole in rings[1:])
            if not in_hole:
                return True
    return False


def clip_coords(coords: list) -> list | None:
    """Keep the longest contiguous run of points inside China/TW/HK/MO."""
    if not coords or len(coords) < 2:
        return None

    best: list = []
    current: list = []
    for pt in coords:
        lon, lat = float(pt[0]), float(pt[1])
        if point_in_china(lon, lat):
            current.append([lon, lat])
        else:
            if len(current) > len(best):
                best = current
            current = []
    if len(current) > len(best):
        best = current

    return best if len(best) >= 2 else None


def segment_in_china(coords: list) -> bool:
    """True if at least two points fall inside the territory."""
    return clip_coords(coords) is not None
