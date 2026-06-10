# 中国铁路百年图 · China Railways Bloom

Interactive timeline visualization inspired by [JIVX Eki · 駅](https://jivx.com/eki) — every railway station and line in China from the first Wusong segment (1876) to today.

## Features

- **Large China-focused map** (68vh+ viewport)
- **Bilingual UI** (中文 + English)
- **Stations and railways appear and disappear** by open/close year (e.g. Wusong Railway 1876–1877)
- **Start year 1876** — Wusong Railway, China's first operational line

## Quick start

Clone and open — **built data ships in `public/data/`** (no OSM fetch required):

```bash
cd public
python -m http.server 8080
```

Open **http://127.0.0.1:8080** (hard refresh: Ctrl+F5)

### Rebuild data locally (optional)

```bash
python scripts/build_data.py
python scripts/merge_railway_cache.py
cd public
python -m http.server 8080
```

## Deploy (Vercel)

1. Push to GitHub — commit **`public/data/*.json`**, not the OSM cache
2. Vercel → Import repo → **Root Directory: `public`**
3. Build Command: leave empty → Deploy

The file `data/osm_railways_cache.json` (~68 MB) is **gitignored**. It is only for local regeneration of railway lines.

## Railway lines

Shipped build includes **~5000+ OSM mainline segments** plus 9 curated historical lines in `public/data/railways.json`.

To refresh from OpenStreetMap:

```bash
# Optional: download OSM tiles (needs curl; may take a while / rate limits)
python scripts/fetch_osm_railways.py

python scripts/merge_railway_cache.py
python scripts/build_data.py
```

If `fetch_osm_railways.py` fails, `merge_railway_cache.py` still works if you already have `data/osm_railways_cache.json` on disk.

## Data sources

| Layer | Source |
|-------|--------|
| Stations | Wikidata (CC0) — mainland + Taiwan; excludes metro |
| Modern railways | OpenStreetMap → merged into `public/data/railways.json` |
| Early railways | Curated from 上海市宝山区人民政府, Cambridge IJAS 2014, 唐胥铁路档案 |
| Coastline | Natural Earth |
