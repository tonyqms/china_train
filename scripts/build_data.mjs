import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.join(__dirname, '..');
const DATA = path.join(ROOT, 'data');
const OUT = path.join(ROOT, 'public', 'data');

const START_YEAR = 1876; // 吴淞铁路 — China's first operational railway segment
const END_YEAR = new Date().getFullYear();

const TILES = [
  { name: 'nw', south: 32, west: 73, north: 54, east: 100 },
  { name: 'ne', south: 32, west: 100, north: 54, east: 135 },
  { name: 'sw', south: 18, west: 73, north: 32, east: 100 },
  { name: 'se', south: 18, west: 100, north: 32, east: 135 },
];

function parseYear(value) {
  if (!value) return null;
  const m = String(value).match(/(\d{4})/);
  return m ? Number(m[1]) : null;
}

function inChinaBBox(lat, lon) {
  return lon >= 73 && lon <= 135 && lat >= 17.5 && lat <= 54.5;
}

function dedupeStations(rows) {
  const map = new Map();
  for (const row of rows) {
    const lat = Number(row.lat);
    const lon = Number(row.lon);
    if (!inChinaBBox(lat, lon)) continue;

    const id = row.id;
    const openYear = parseYear(row.open_date);
    const closeYear = parseYear(row.close_date);
    const existing = map.get(id);

    if (!existing) {
      map.set(id, {
        id,
        name_zh: row.name_zh || '',
        name_en: row.name_en || '',
        lat,
        lon,
        open_year: openYear,
        close_year: closeYear,
      });
      continue;
    }

    if (openYear && (!existing.open_year || openYear < existing.open_year)) {
      existing.open_year = openYear;
    }
    if (closeYear) existing.close_year = closeYear;
    if (!existing.name_en && row.name_en) existing.name_en = row.name_en;
    if (!existing.name_zh && row.name_zh) existing.name_zh = row.name_zh;
  }
  return [...map.values()];
}

function parseCsv(text) {
  const lines = text.replace(/^\uFEFF/, '').split(/\r?\n/).filter(Boolean);
  const headers = lines[0].split(',').map((h) => h.replace(/^"|"$/g, ''));
  return lines.slice(1).map((line) => {
    const cols = [];
    let cur = '';
    let inQ = false;
    for (let i = 0; i < line.length; i++) {
      const ch = line[i];
      if (ch === '"') {
        inQ = !inQ;
        continue;
      }
      if (ch === ',' && !inQ) {
        cols.push(cur);
        cur = '';
        continue;
      }
      cur += ch;
    }
    cols.push(cur);
    const obj = {};
    headers.forEach((h, i) => {
      obj[h] = cols[i] ?? '';
    });
    return obj;
  });
}

function addHistoricalStations(stations) {
  const extras = [
    {
      id: 'hist-wusong-shanghai',
      name_zh: '上海站（吴淞铁路）',
      name_en: 'Shanghai Station (Wusong Railway)',
      lat: 31.2304,
      lon: 121.4737,
      open_year: 1876,
      close_year: 1877,
    },
    {
      id: 'hist-wusong-jiangwan',
      name_zh: '江湾站',
      name_en: 'Jiangwan Station',
      lat: 31.298,
      lon: 121.458,
      open_year: 1876,
      close_year: 1877,
    },
    {
      id: 'hist-wusong-wusong',
      name_zh: '吴淞站',
      name_en: 'Wusong Station',
      lat: 31.378,
      lon: 121.438,
      open_year: 1876,
      close_year: 1877,
    },
    {
      id: 'hist-tangshan',
      name_zh: '唐山站（唐胥铁路起点）',
      name_en: 'Tangshan Station (Tangxu Railway origin)',
      lat: 39.63,
      lon: 118.18,
      open_year: 1881,
      close_year: null,
    },
    {
      id: 'hist-xugezhuang',
      name_zh: '胥各庄站',
      name_en: 'Xugezhuang Station',
      lat: 39.725,
      lon: 118.33,
      open_year: 1888,
      close_year: null,
    },
  ];
  return [...stations, ...extras];
}

async function fetchTileRailways(tile) {
  const query = `[out:json][timeout:90];
(
  way["railway"~"^(rail|light_rail|subway|tram)$"](${tile.south},${tile.west},${tile.north},${tile.east});
);
out tags geom;`;

  const body = new URLSearchParams({ data: query });
  const res = await fetch('https://overpass.kumi.systems/api/interpreter', {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body,
  });
  if (!res.ok) throw new Error(`Overpass ${tile.name}: ${res.status}`);
  const json = await res.json();
  return json.elements || [];
}

function simplifyCoords(coords, maxPoints = 12) {
  if (coords.length <= maxPoints) return coords;
  const step = Math.ceil(coords.length / maxPoints);
  const out = [];
  for (let i = 0; i < coords.length; i += step) out.push(coords[i]);
  const last = coords[coords.length - 1];
  const tail = out[out.length - 1];
  if (!tail || tail[0] !== last[0] || tail[1] !== last[1]) out.push(last);
  return out;
}

function processOsmWays(elements) {
  const lines = [];
  for (const el of elements) {
    if (el.type !== 'way' || !el.geometry?.length) continue;
    const coords = el.geometry.map((p) => [p.lon, p.lat]);
    if (coords.length < 2) continue;

    const tags = el.tags || {};
    let openYear = parseYear(tags.start_date || tags.opening_date || tags.construction_start);
    let closeYear = parseYear(tags.end_date || tags.abandoned || tags.demolished);

    if (tags.railway === 'abandoned' || tags.railway === 'razed') {
      if (!closeYear) closeYear = parseYear(tags['abandoned:date']) || 1990;
      if (!openYear) openYear = 1950;
    }

    if (!openYear) {
      if (tags.highspeed === 'yes' || tags.usage === 'main') openYear = 2008;
      else if (tags.railway === 'subway' || tags.railway === 'light_rail') openYear = 1990;
      else openYear = 1950;
    }

    lines.push({
      id: `osm-${el.id}`,
      name_zh: tags['name:zh'] || tags.name || '',
      name_en: tags['name:en'] || tags.name || '',
      open_year: openYear,
      close_year: closeYear,
      railway: tags.railway || 'rail',
      coords: simplifyCoords(coords, 10),
    });
  }
  return lines;
}

function buildYearHistogram(stations, railways, start, end) {
  const bins = [];
  for (let y = start; y <= end; y++) {
    bins.push({
      year: y,
      stations_open: 0,
      stations_close: 0,
      railways_open: 0,
      railways_close: 0,
    });
  }
  const idx = (y) => y - start;

  for (const s of stations) {
    if (s.open_year && s.open_year >= start && s.open_year <= end) bins[idx(s.open_year)].stations_open++;
    if (s.close_year && s.close_year >= start && s.close_year <= end) bins[idx(s.close_year)].stations_close++;
  }
  for (const r of railways) {
    if (r.open_year && r.open_year >= start && r.open_year <= end) bins[idx(r.open_year)].railways_open++;
    if (r.close_year && r.close_year >= start && r.close_year <= end) bins[idx(r.close_year)].railways_close++;
  }
  return bins;
}

async function main() {
  fs.mkdirSync(OUT, { recursive: true });

  const csvPath = path.join(DATA, 'stations_wikidata.csv');
  if (!fs.existsSync(csvPath)) {
    console.error('Missing stations_wikidata.csv — run Wikidata fetch first.');
    process.exit(1);
  }

  let stations = dedupeStations(parseCsv(fs.readFileSync(csvPath, 'utf8')));
  stations = addHistoricalStations(stations);
  stations = stations.filter((s) => s.open_year || s.close_year === null);

  const historical = JSON.parse(fs.readFileSync(path.join(DATA, 'historical_railways.json'), 'utf8'));
  let railways = historical.map((r) => ({
    id: r.id,
    name_zh: r.name_zh,
    name_en: r.name_en,
    open_year: r.open_year,
    close_year: r.close_year,
    source: 'curated',
    coords: r.coords,
  }));

  console.log('Fetching OSM railway tiles...');
  for (const tile of TILES) {
    try {
      console.log(`  tile ${tile.name}...`);
      const elements = await fetchTileRailways(tile);
      const lines = processOsmWays(elements);
      railways.push(...lines);
      console.log(`    +${lines.length} segments`);
    } catch (err) {
      console.warn(`  tile ${tile.name} failed: ${err.message}`);
    }
  }

  const compactStations = stations
    .filter((s) => s.open_year)
    .map((s) => [
      s.id,
      s.name_zh,
      s.name_en,
      Math.round(s.lon * 10000) / 10000,
      Math.round(s.lat * 10000) / 10000,
      s.open_year,
      s.close_year || 0,
    ]);

  const compactRailways = railways.map((r) => [
    r.id,
    r.name_zh,
    r.name_en,
    r.open_year,
    r.close_year || 0,
    r.coords.map(([lon, lat]) => [Math.round(lon * 1000) / 1000, Math.round(lat * 1000) / 1000]),
  ]);

  const histogram = buildYearHistogram(stations.filter((s) => s.open_year), railways, START_YEAR, END_YEAR);

  const meta = {
    start_year: START_YEAR,
    end_year: END_YEAR,
    station_count: compactStations.length,
    railway_count: compactRailways.length,
    first_line_zh: '吴淞铁路（上海—吴淞）',
    first_line_en: 'Wusong Railway (Shanghai–Wusong)',
    first_line_year: 1876,
    sources: [
      'Wikidata (CC0): railway stations in China with coordinates and P1619/P3999 dates',
      'OpenStreetMap: railway ways with start_date/end_date tags where available',
      'Curated historical segments: Wusong 1876, Tangxu 1881, Jinghan 1906, etc.',
      '上海市宝山区人民政府; Cambridge IJAS 2014 (Wusong Railway)',
    ],
    generated_at: new Date().toISOString().slice(0, 10),
  };

  fs.writeFileSync(path.join(OUT, 'meta.json'), JSON.stringify(meta, null, 2));
  fs.writeFileSync(path.join(OUT, 'stations.json'), JSON.stringify(compactStations));
  fs.writeFileSync(path.join(OUT, 'railways.json'), JSON.stringify(compactRailways));
  fs.writeFileSync(path.join(OUT, 'histogram.json'), JSON.stringify(histogram));

  console.log(`Done: ${compactStations.length} stations, ${compactRailways.length} railway segments`);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
