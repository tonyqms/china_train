# 中国铁路百年图 · China Railways Bloom

Interactive timeline visualization inspired by [JIVX Eki · 駅](https://jivx.com/eki) — every railway station and line in China from the first Wusong segment (1876) to today.

## Features

- **Large China-focused map** (68vh+ viewport)
- **Bilingual UI** (中文 + English)
- **Stations and railways appear and disappear** by open/close year (e.g. Wusong Railway 1876–1877)
- **Start year 1876** — Wusong Railway, China's first operational line

## Quick start

```bash
python scripts/build_data.py
python scripts/merge_railway_cache.py   # builds ~3000+ lines from cached OSM tiles
cd public
python -m http.server 3456
```

Open **http://127.0.0.1:3456** (hard refresh: Ctrl+F5)

## Railway lines (why only 9 lines before?)

Default build includes **9 curated historical lines** only. To add the modern network:

```bash
# Optional: refresh OSM cache (uses curl, not Python urllib — avoids 403/406)
python scripts/fetch_osm_railways.py

# Always run after fetch (or uses existing data/osm_railways_cache.json)
python scripts/merge_railway_cache.py
```

If `fetch_osm_railways.py` still fails (Overpass rate limits), `merge_railway_cache.py` works offline from any cache already on disk (~3283 main-line segments).

## Data sources

| Layer | Source |
|-------|--------|
| Stations | Wikidata (CC0) — P625, P1619, P3999 |
| Modern railways | OpenStreetMap via Overpass API |
| Early railways | Curated from 上海市宝山区人民政府, Cambridge IJAS 2014, 唐胥铁路档案 |
| Coastline | Natural Earth |
