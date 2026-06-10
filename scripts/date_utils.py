"""Resolve station open/close years from Wikidata dates and manual corrections."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORRECTIONS_PATH = ROOT / "data" / "station_corrections.json"


def parse_year(value: str | None) -> int | None:
    if not value:
        return None
    for i, ch in enumerate(value):
        if ch.isdigit():
            chunk = value[i : i + 4]
            if len(chunk) == 4 and chunk.isdigit():
                y = int(chunk)
                if 1800 <= y <= 2100:
                    return y
    return None


def resolve_open_years(years: list[int]) -> int | None:
    """Pick best opening year when Wikidata has multiple values."""
    if not years:
        return None
    years = sorted(set(years))
    if len(years) == 1:
        return years[0]
    span = years[-1] - years[0]
    # Large gap → rebuilt / reopened station (e.g. QTR 1929 vs 2006)
    if span > 25:
        return years[-1]
    return years[0]


def resolve_close_years(years: list[int]) -> int | None:
    """Earliest credible closure year."""
    if not years:
        return None
    return min(years)


def load_corrections() -> tuple[dict[str, dict], list[dict]]:
    if not CORRECTIONS_PATH.exists():
        return {}, []
    data = json.loads(CORRECTIONS_PATH.read_text(encoding="utf-8"))
    by_id = {s["id"]: s for s in data.get("stations", [])}
    return by_id, data.get("rules", [])


def in_bbox(lon: float, lat: float, bbox: list[float]) -> bool:
    min_lon, min_lat, max_lon, max_lat = bbox
    return min_lon <= lon <= max_lon and min_lat <= lat <= max_lat


def apply_rules(
    station: dict,
    rules: list[dict],
) -> dict[str, int | str | None]:
    """Return optional overrides from rule-based heuristics."""
    overrides: dict[str, int | str | None] = {}
    open_y = station.get("open_year")
    lat, lon = float(station["lat"]), float(station["lon"])

    for rule in rules:
        bbox = rule.get("bbox")
        wrong = set(rule.get("wrong_open_years", []))
        correct = rule.get("correct_open_year")
        if (
            bbox
            and open_y in wrong
            and in_bbox(lon, lat, bbox)
        ):
            overrides["open_year"] = correct
            overrides["rule_id"] = rule["id"]
            overrides["source"] = rule.get("source")
            break

    return overrides


def apply_corrections(
    station: dict,
    corrections: dict[str, dict],
    rules: list[dict],
) -> dict:
    """Apply manual overrides and rules; return updated station dict."""
    sid = station["id"]
    out = dict(station)

    rule_ov = apply_rules(out, rules)
    if "open_year" in rule_ov:
        out["open_year"] = rule_ov["open_year"]
        out["_date_source"] = f"rule:{rule_ov.get('rule_id')}"

    if sid in corrections:
        c = corrections[sid]
        if "open_year" in c:
            out["open_year"] = c["open_year"]
            out["_date_source"] = f"correction:{sid}"
        if "close_year" in c:
            out["close_year"] = c["close_year"]
            out["_date_source"] = f"correction:{sid}"

    return out
