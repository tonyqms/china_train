"""Filters and geometry helpers for OSM railway segments."""
from __future__ import annotations

import math
import re

# Metro / urban rail — align with station filters in build_data.py
METRO_NAME = re.compile(
    r"地铁|地鐵|轨道交通|軌道交通|轻轨|輕軌|有轨|有軌|电车|電車|"
    r"捷运|捷運|"
    r"monorail|maglev|磁浮|磁悬浮|"
    r"\bsubway\b|\bmetro\b|\bmtr\b|\bbts\b|\bmrt\b|\bapm\b|"
    r"airport express|机场快线|機場快線|"
    r"people.?s mover|urban rail|城际轨道|市域铁路|市域快轨|"
    r"单轨|單軌|胶轮|膠輪|云巴|有轨电车",
    re.I,
)

# Yard spurs, industrial, depots — often create sharp stray segments
SPUR_NAME = re.compile(
    r"专用线|專用線|货场|貨場|编组|編組|机务|機務|车辆段|車輛段|"
    r"动车所|動車所|停车场|停車場|depot|siding|yard|spur|"
    r"联络线|聯絡線|走行线|走行線|牵出线|牽出線",
    re.I,
)

METRO_OPERATORS = re.compile(
    r"北京地铁|上海地铁|广州地铁|深圳地铁|港铁|MTR|"
    r"成都地铁|武汉地铁|南京地铁|杭州地铁|重庆轨道交通|"
    r"天津地铁|西安地铁|苏州地铁|郑州地铁|长沙地铁|"
    r"青岛地铁|大连地铁|沈阳地铁|哈尔滨地铁|昆明地铁|"
    r"宁波地铁|无锡地铁|佛山地铁|东莞地铁|合肥地铁|"
    r"南昌地铁|福州地铁|厦门地铁|济南地铁|温州地铁|"
    r"Beijing Subway|Shanghai Metro|Guangzhou Metro",
    re.I,
)

EXCLUDED_USAGE = {"industrial", "military", "test", "tourism", "freight"}
EXCLUDED_SERVICE = {"yard", "siding", "spur", "crossover", "headshunt", "escape"}


def _text(*parts: str | None) -> str:
    return " ".join(p for p in parts if p)


def is_metro_row(name_zh: str, name_en: str, tags: dict | None = None) -> bool:
    text = _text(name_zh, name_en)
    if METRO_NAME.search(text):
        return True
    if tags:
        op = tags.get("operator") or tags.get("operator:zh") or ""
        if METRO_OPERATORS.search(op):
            return True
        usage = (tags.get("usage") or "").lower()
        if usage in {"urban", "metro"}:
            return True
        if tags.get("passenger") == "urban":
            return True
        if tags.get("railway") in {"subway", "light_rail", "tram", "monorail", "narrow_gauge"}:
            return True
    return False


def is_spur_row(name_zh: str, name_en: str, tags: dict | None = None) -> bool:
    text = _text(name_zh, name_en)
    if SPUR_NAME.search(text):
        return True
    if tags:
        service = (tags.get("service") or "").lower()
        if service in EXCLUDED_SERVICE:
            return True
        usage = (tags.get("usage") or "").lower()
        if usage in EXCLUDED_USAGE:
            return True
        if tags.get("industrial") == "yes":
            return True
    return False


def seg_length(coords: list) -> float:
    total = 0.0
    for i in range(1, len(coords)):
        lon1, lat1 = coords[i - 1]
        lon2, lat2 = coords[i]
        dx = (lon2 - lon1) * math.cos(math.radians((lat1 + lat2) / 2))
        dy = lat2 - lat1
        total += math.hypot(dx, dy)
    return total


def _perp_dist(point: list, start: list, end: list) -> float:
    x0, y0 = point
    x1, y1 = start
    x2, y2 = end
    dx, dy = x2 - x1, y2 - y1
    if dx == 0 and dy == 0:
        return math.hypot(x0 - x1, y0 - y1)
    t = max(0, min(1, ((x0 - x1) * dx + (y0 - y1) * dy) / (dx * dx + dy * dy)))
    px, py = x1 + t * dx, y1 + t * dy
    return math.hypot(x0 - px, y0 - py)


def douglas_peucker(coords: list, epsilon: float) -> list:
    if len(coords) <= 2:
        return coords
    start, end = coords[0], coords[-1]
    max_dist = 0.0
    index = 0
    for i in range(1, len(coords) - 1):
        d = _perp_dist(coords[i], start, end)
        if d > max_dist:
            max_dist = d
            index = i
    if max_dist > epsilon:
        left = douglas_peucker(coords[: index + 1], epsilon)
        right = douglas_peucker(coords[index:], epsilon)
        return left[:-1] + right
    return [start, end]


def simplify_coords(coords: list, max_pts: int = 14, epsilon: float = 0.015) -> list:
    """Keep corridor shape while limiting point count for rendering."""
    if len(coords) <= 2:
        return coords
    simplified = douglas_peucker(coords, epsilon)
    if len(simplified) <= max_pts:
        return simplified
    step = max(1, len(simplified) // max_pts)
    out = simplified[::step]
    if out[-1] != simplified[-1]:
        out.append(simplified[-1])
    return out


def max_turn_angle(coords: list) -> float:
    """Return sharpest turn angle (degrees) along polyline."""
    if len(coords) < 3:
        return 0.0
    worst = 0.0
    for i in range(1, len(coords) - 1):
        a, b, c = coords[i - 1], coords[i], coords[i + 1]
        v1 = (b[0] - a[0], b[1] - a[1])
        v2 = (c[0] - b[0], c[1] - b[1])
        n1 = math.hypot(*v1)
        n2 = math.hypot(*v2)
        if n1 < 1e-9 or n2 < 1e-9:
            continue
        dot = max(-1.0, min(1.0, (v1[0] * v2[0] + v1[1] * v2[1]) / (n1 * n2)))
        turn = 180.0 - math.degrees(math.acos(dot))
        worst = max(worst, turn)
    return worst


def build_station_grid(
    stations: list[tuple[float, float]], cell: float = 0.5
) -> dict[tuple[int, int], list[tuple[float, float]]]:
    grid: dict[tuple[int, int], list[tuple[float, float]]] = {}
    for lon, lat in stations:
        key = (int(lon // cell), int(lat // cell))
        grid.setdefault(key, []).append((lon, lat))
    return grid


def near_station_grid(
    lon: float,
    lat: float,
    grid: dict[tuple[int, int], list[tuple[float, float]]],
    max_deg: float,
    cell: float = 0.5,
) -> bool:
    cx, cy = int(lon // cell), int(lat // cell)
    reach = int(max_deg / cell) + 1
    for dx in range(-reach, reach + 1):
        for dy in range(-reach, reach + 1):
            for slon, slat in grid.get((cx + dx, cy + dy), []):
                dlon = (lon - slon) * math.cos(math.radians((lat + slat) / 2))
                dlat = lat - slat
                if math.hypot(dlon, dlat) <= max_deg:
                    return True
    return False


def passes_near_stations_grid(
    coords: list,
    grid: dict[tuple[int, int], list[tuple[float, float]]],
    max_deg: float = 0.06,
) -> bool:
    if not grid:
        return True
    for lon, lat in coords:
        if near_station_grid(lon, lat, grid, max_deg):
            return True
    if len(coords) >= 2:
        mid = coords[len(coords) // 2]
        if near_station_grid(mid[0], mid[1], grid, max_deg):
            return True
    return False
