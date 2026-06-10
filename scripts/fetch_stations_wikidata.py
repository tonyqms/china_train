#!/usr/bin/env python3
"""Fetch intercity railway stations from Wikidata (mainland + Taiwan)."""
from __future__ import annotations

import csv
import json
import time
import urllib.parse
import urllib.request
from pathlib import Path

from date_utils import parse_year, resolve_close_years, resolve_open_years

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "stations_wikidata.csv"

# Q148 China, Q865 Taiwan
COUNTRY_CODES = ["Q148", "Q865"]

EXCLUDED_TYPES = [
    "Q928830",
    "Q953806",
    "Q2175765",
    "Q55654238",
    "Q55097243",
    "Q22808404",
]

EXCLUDE_FILTER = "\n".join(
    f"  FILTER NOT EXISTS {{ ?station wdt:P31/wdt:P279* wd:{q} . }}"
    for q in EXCLUDED_TYPES
)

COUNTRY_FILTER = "FILTER(?country IN (wd:Q148, wd:Q865))"

QUERY = f"""
SELECT ?station ?stationLabel ?lat ?lon ?opening ?closing ?dissolved ?endTime ?serviceEntry ?enLabel WHERE {{
  ?station wdt:P31/wdt:P279* wd:Q55488 ;
           wdt:P17 ?country ;
           wdt:P625 ?coord .
  BIND(geof:latitude(?coord) AS ?lat)
  BIND(geof:longitude(?coord) AS ?lon)
  {COUNTRY_FILTER}
{EXCLUDE_FILTER}
  OPTIONAL {{ ?station wdt:P1619 ?opening . }}
  OPTIONAL {{ ?station wdt:P3999 ?closing . }}
  OPTIONAL {{ ?station wdt:P576 ?dissolved . }}
  OPTIONAL {{ ?station wdt:P582 ?endTime . }}
  OPTIONAL {{ ?station wdt:P729 ?serviceEntry . }}
  OPTIONAL {{ ?station rdfs:label ?enLabel . FILTER(LANG(?enLabel) = "en") }}
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "zh". }}
}}
"""


def _date(binding: dict, key: str) -> str:
    return (binding.get(key, {}).get("value", "") or "").split("T")[0]


def fetch_bindings() -> list[dict]:
    url = "https://query.wikidata.org/sparql?" + urllib.parse.urlencode(
        {"format": "json", "query": QUERY}
    )
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "ChinaRailViz/1.3 (intercity rail research; incl. Taiwan)"},
    )
    with urllib.request.urlopen(req, timeout=300) as resp:
        data = json.loads(resp.read())
    return data["results"]["bindings"]


def aggregate_rows(bindings: list[dict]) -> list[dict]:
    grouped: dict[str, dict] = {}

    for b in bindings:
        if "lat" not in b or "lon" not in b:
            continue
        sid = b["station"]["value"].rsplit("/", 1)[-1]
        if sid not in grouped:
            grouped[sid] = {
                "id": sid,
                "name_zh": b.get("stationLabel", {}).get("value", ""),
                "name_en": b.get("enLabel", {}).get("value", ""),
                "lat": b["lat"]["value"],
                "lon": b["lon"]["value"],
                "open_dates": [],
                "close_dates": [],
            }
        g = grouped[sid]
        if b.get("enLabel", {}).get("value") and not g["name_en"]:
            g["name_en"] = b["enLabel"]["value"]
        for key, bucket in (
            ("opening", "open_dates"),
            ("serviceEntry", "open_dates"),
            ("closing", "close_dates"),
            ("dissolved", "close_dates"),
            ("endTime", "close_dates"),
        ):
            d = _date(b, key)
            if d and d not in g[bucket]:
                g[bucket].append(d)

    rows = []
    for g in grouped.values():
        open_years = [y for d in g["open_dates"] if (y := parse_year(d))]
        close_years = [y for d in g["close_dates"] if (y := parse_year(d))]
        open_res = resolve_open_years(open_years)
        close_res = resolve_close_years(close_years)
        rows.append(
            {
                "id": g["id"],
                "name_zh": g["name_zh"],
                "name_en": g["name_en"],
                "lat": g["lat"],
                "lon": g["lon"],
                "open_date": f"{open_res:04d}-01-01" if open_res else "",
                "close_date": f"{close_res:04d}-01-01" if close_res else "",
                "open_dates_raw": ";".join(sorted(g["open_dates"])),
                "close_dates_raw": ";".join(sorted(g["close_dates"])),
            }
        )
    return rows


def main() -> None:
    print("Fetching intercity stations (mainland + Taiwan) from Wikidata…", flush=True)
    bindings = fetch_bindings()
    rows = aggregate_rows(bindings)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "id", "name_zh", "name_en", "lat", "lon",
        "open_date", "close_date", "open_dates_raw", "close_dates_raw",
    ]
    with OUT.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    tw = sum(
        1 for r in rows
        if 119.2 <= float(r["lon"]) <= 122.1 and 21.8 <= float(r["lat"]) <= 25.4
    )
    print(f"Wrote {len(rows)} stations ({tw} in Taiwan bbox) -> {OUT}", flush=True)
    time.sleep(1)


if __name__ == "__main__":
    main()
