/* global d3 */

const ERAS = [
  { id: 'qing', label_zh: '清末 Qing', label_en: 'Late Qing', start: 1876, end: 1911, color: '#6b4c9a' },
  { id: 'roc', label_zh: '民国 ROC', label_en: 'Republic', start: 1912, end: 1949, color: '#3d7ea6' },
  { id: 'prc', label_zh: '新中国 PRC', label_en: "People's Republic", start: 1950, end: 1978, color: '#c23b22' },
  { id: 'reform', label_zh: '改革开放 Reform', label_en: 'Reform era', start: 1979, end: 2007, color: '#2a9d8f' },
  { id: 'hsr', label_zh: '高铁时代 HSR', label_en: 'High-speed rail', start: 2008, end: 9999, color: '#e9c46a' },
];

let meta, stations, railways, histogram;
let year = 1876;
let playing = false;
let playTimer = null;
let projection, path, canvas, ctx, width, height;
let chinaGeo = null;
let hovered = null;
let activeStations = [];
let activeRailways = [];
let layoutAttempts = 0;
let mapTransform = d3.zoomIdentity;
let zoomBehavior = null;

const $ = (sel) => document.querySelector(sel);

function showFatal(msg) {
  const sub = $('#year-sub');
  if (sub) sub.textContent = msg;
  console.error(msg);
}

function unpackStation(row) {
  return {
    id: row[0], name_zh: row[1], name_en: row[2],
    lon: row[3], lat: row[4], open_year: row[5],
    close_year: row[6] > 0 ? row[6] : null,
  };
}

function unpackRailway(row) {
  return {
    id: row[0], name_zh: row[1], name_en: row[2],
    open_year: row[3],
    close_year: row[4] > 0 ? row[4] : null,
    coords: row[5],
  };
}

function isActive(item, y) {
  if (!item.open_year || item.open_year > y) return false;
  if (item.close_year && item.close_year < y) return false;
  return true;
}

function refreshActiveCache() {
  activeStations = stations.filter((s) => isActive(s, year));
  activeRailways = railways.filter((r) => isActive(r, year));
}

function countActive() {
  return { st: activeStations.length, rl: activeRailways.length };
}

function currentEra(y) {
  return ERAS.find((e) => y >= e.start && y <= e.end) || ERAS[ERAS.length - 1];
}

function yearCaption(y) {
  const captions = {
    1876: "1876 — 吴淞铁路 Wusong Railway opens. Shanghai to Wusong, 14.5 km — China's entire network begins as a single line.",
    1877: '1877 — 吴淞铁路拆除 dismantled. Qing government purchases then removes the line.',
    1881: "1881 — 唐胥铁路 Tangxu Railway opens. China's first self-built operational railway.",
    1906: '1906 — 京汉铁路 Jinghan Railway completed. North–south spine connects Beijing and Hankou.',
    1952: '1952 — 成渝铁路 Chengyu Railway, first major line after 1949.',
    2008: '2008 — 京津城际 Beijing–Tianjin intercity: high-speed rail era begins.',
  };
  return captions[y] || `${y} — 拖动滑块或按播放 Drag the slider or press Play to watch the network grow.`;
}

function setupProjection() {
  const inner = $('#map-inner');
  const wrap = $('#map-wrap');
  let w = inner.clientWidth;
  let h = inner.clientHeight;
  if (w < 20 || h < 20) {
    const r = wrap.getBoundingClientRect();
    w = Math.max(20, r.width * 0.96);
    h = Math.max(20, r.height * 0.96);
  }
  width = w;
  height = h;
  canvas.width = width * devicePixelRatio;
  canvas.height = height * devicePixelRatio;
  canvas.style.width = `${width}px`;
  canvas.style.height = `${height}px`;
  ctx.setTransform(devicePixelRatio, 0, 0, devicePixelRatio, 0, 0);

  projection = d3.geoMercator()
    .center([104, 35.5])
    .scale(Math.min(width, height) * 1.92)
    .translate([width / 2, height / 2]);

  path = d3.geoPath(projection, ctx);
  return width >= 20 && height >= 20;
}

function toMapCoords(lon, lat) {
  const p = projection([lon, lat]);
  if (!p) return null;
  return mapTransform.apply(p);
}

function resetMapView(animate) {
  mapTransform = d3.zoomIdentity;
  if (zoomBehavior) {
    const sel = d3.select(canvas);
    if (animate) sel.transition().duration(250).call(zoomBehavior.transform, d3.zoomIdentity);
    else sel.call(zoomBehavior.transform, d3.zoomIdentity);
  }
  requestAnimationFrame(drawMap);
}

function setupMapZoom() {
  zoomBehavior = d3.zoom()
    .scaleExtent([1, 12])
    .on('zoom', (event) => {
      mapTransform = event.transform;
      requestAnimationFrame(drawMap);
    });

  d3.select(canvas)
    .call(zoomBehavior)
    .on('dblclick.zoom', null);

  canvas.addEventListener('dblclick', (e) => {
    e.preventDefault();
    resetMapView(true);
  });
}

function drawMap() {
  if (!width || !height || !ctx || typeof d3 === 'undefined') return;
  ctx.clearRect(0, 0, width, height);

  if (chinaGeo) {
    ctx.save();
    ctx.translate(mapTransform.x, mapTransform.y);
    ctx.scale(mapTransform.k, mapTransform.k);
    ctx.beginPath();
    path(chinaGeo);
    ctx.fillStyle = 'rgba(30, 38, 50, 0.55)';
    ctx.fill();
    ctx.strokeStyle = 'rgba(100, 120, 150, 0.35)';
    ctx.lineWidth = 1 / mapTransform.k;
    ctx.stroke();
    ctx.restore();
  }

  const era = currentEra(year);
  ctx.lineWidth = 1.1;
  ctx.strokeStyle = 'rgba(74,158,255,0.45)';

  for (let i = 0; i < activeRailways.length; i++) {
    const r = activeRailways[i];
    const pts = [];
    for (let j = 0; j < r.coords.length; j++) {
      const p = toMapCoords(r.coords[j][0], r.coords[j][1]);
      if (p) pts.push(p);
    }
    if (pts.length < 2) continue;
    ctx.beginPath();
    ctx.moveTo(pts[0][0], pts[0][1]);
    for (let j = 1; j < pts.length; j++) ctx.lineTo(pts[j][0], pts[j][1]);
    ctx.stroke();
  }

  ctx.globalAlpha = 0.85;
  for (let i = 0; i < activeStations.length; i++) {
    const s = activeStations[i];
    const p = toMapCoords(s.lon, s.lat);
    if (!p) continue;
    const isHover = hovered && hovered.id === s.id;
    ctx.beginPath();
    ctx.arc(p[0], p[1], isHover ? 4 : 2.5, 0, Math.PI * 2);
    ctx.fillStyle = isHover ? '#fff' : era.color;
    ctx.fill();
  }
  ctx.globalAlpha = 1;

  drawHistogramMarker();
}

function drawHistogramMarker() {
  const histCanvas = $('#histogram');
  if (!histCanvas || !histogram) return;
  const hctx = histCanvas.getContext('2d');
  const hw = histCanvas.clientWidth;
  const hh = histCanvas.clientHeight;
  if (hw < 1 || hh < 1) return;
  histCanvas.width = hw * devicePixelRatio;
  histCanvas.height = hh * devicePixelRatio;
  hctx.setTransform(devicePixelRatio, 0, 0, devicePixelRatio, 0, 0);
  hctx.clearRect(0, 0, hw, hh);

  const maxVal = d3.max(histogram, (d) => d.stations_open + d.railways_open) || 1;
  const barW = hw / histogram.length;

  histogram.forEach((d, i) => {
    const total = d.stations_open + d.railways_open;
    const bh = (total / maxVal) * (hh - 16);
    const x = i * barW;
    hctx.fillStyle = 'rgba(74,158,255,0.35)';
    hctx.fillRect(x, hh - bh - 4, Math.max(barW - 0.5, 1), bh * 0.4);
    hctx.fillStyle = 'rgba(255,209,102,0.5)';
    hctx.fillRect(x, hh - bh - 4 + bh * 0.4, Math.max(barW - 0.5, 1), bh * 0.6);
  });

  const idx = year - meta.start_year;
  const mx = (idx + 0.5) * barW;
  hctx.strokeStyle = '#e85d3a';
  hctx.lineWidth = 2;
  hctx.beginPath();
  hctx.moveTo(mx, 0);
  hctx.lineTo(mx, hh);
  hctx.stroke();
}

function updateUI() {
  refreshActiveCache();
  $('#year-display').textContent = year;
  const { st, rl } = countActive();
  $('#counter').textContent = `${st.toLocaleString()} 枢纽 · ${rl.toLocaleString()} 线路`;
  $('#year-sub').textContent = yearCaption(year);
  $('#year-slider').value = year;
  $('#year-slider').min = meta.start_year;
  $('#year-slider').max = meta.end_year;

  document.querySelectorAll('.era-pill').forEach((el) => {
    const era = ERAS.find((e) => e.id === el.dataset.era);
    el.classList.toggle('active', era && year >= era.start && year <= era.end);
  });
}

function setYear(y) {
  year = Math.max(meta.start_year, Math.min(meta.end_year, y));
  updateUI();
  requestAnimationFrame(drawMap);
}
window.setYear = setYear;

function togglePlay() {
  playing = !playing;
  $('#play-btn').textContent = playing ? '暂停 Pause' : '播放 Play';
  if (playing) {
    playTimer = setInterval(() => {
      if (year >= meta.end_year) setYear(meta.start_year);
      else setYear(year + 1);
    }, 150);
  } else {
    clearInterval(playTimer);
  }
}

function findStationAt(mx, my) {
  const [ix, iy] = mapTransform.invert([mx, my]);
  let best = null;
  let bestD = 12 / mapTransform.k;
  for (let i = 0; i < activeStations.length; i++) {
    const s = activeStations[i];
    const p = projection([s.lon, s.lat]);
    if (!p) continue;
    const d = Math.hypot(p[0] - ix, p[1] - iy);
    if (d < bestD) {
      bestD = d;
      best = s;
    }
  }
  return best;
}

function showTooltip(s, x, y) {
  const tip = $('#tooltip');
  if (!s) {
    tip.style.display = 'none';
    return;
  }
  const label = s.name_zh && s.name_en ? `${s.name_zh} · ${s.name_en}` : (s.name_zh || s.name_en);
  const closeTxt = s.close_year ? ` — 关闭 closed ${s.close_year}` : '';
  tip.innerHTML = `<strong>${label}</strong><br>开通 opened ${s.open_year}${closeTxt}`;
  tip.style.display = 'block';
  tip.style.left = `${x + 12}px`;
  tip.style.top = `${y + 12}px`;
}

async function loadChinaOutline() {
  try {
    const geo = await fetch('data/china_outline.json').then((r) => {
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      return r.json();
    });
    chinaGeo = geo.type === 'FeatureCollection' ? geo : { type: 'FeatureCollection', features: [geo] };
  } catch (err) {
    console.warn('Outline load failed:', err);
  }
}

function whenLayoutReady(fn) {
  layoutAttempts = 0;
  const attempt = () => {
    layoutAttempts += 1;
    if (setupProjection()) {
      fn();
      return;
    }
    if (layoutAttempts > 120) {
      showFatal('地图尺寸异常 Map layout failed — try zoom 100% and refresh.');
      return;
    }
    requestAnimationFrame(attempt);
  };
  requestAnimationFrame(attempt);
}

function setupSearch() {
  $('#search').addEventListener('input', (e) => {
    const q = e.target.value.trim().toLowerCase();
    if (!q) return;
    const hit = stations.find((s) =>
      (s.name_zh && s.name_zh.includes(q)) ||
      (s.name_en && s.name_en.toLowerCase().includes(q))
    );
    if (hit && hit.open_year) setYear(hit.open_year);
  });
}

function setupEraPills() {
  const bar = $('#era-bar');
  ERAS.forEach((e) => {
    const btn = document.createElement('button');
    btn.className = 'era-pill';
    btn.dataset.era = e.id;
    btn.textContent = `${e.label_zh} / ${e.label_en}`;
    btn.addEventListener('click', () => setYear(e.start));
    bar.appendChild(btn);
  });
}

async function init() {
  if (location.protocol === 'file:') {
    showFatal('请用本地服务器打开：双击 start.bat，或 python -m http.server 8080 --directory public');
    return;
  }
  if (typeof d3 === 'undefined') {
    showFatal('d3 未加载 — 请确认 js/d3.min.js 存在');
    return;
  }

  canvas = $('#map-canvas');
  ctx = canvas.getContext('2d');
  $('#year-sub').textContent = '加载数据 Loading data…';

  const load = (url) => fetch(url).then((r) => {
    if (!r.ok) throw new Error(`${url} HTTP ${r.status}`);
    return r.json();
  });

  [meta, stations, railways, histogram] = await Promise.all([
    load('data/meta.json'),
    load('data/stations.json').then((rows) => rows.map(unpackStation)),
    load('data/railways.json').then((rows) => rows.map(unpackRailway)),
    load('data/histogram.json'),
  ]);

  $('#stat-stations').textContent = meta.station_count.toLocaleString();
  $('#stat-railways').textContent = railways.length.toLocaleString();
  $('#stat-years').textContent = `${meta.end_year - meta.start_year + 1}`;
  $('#stat-first').textContent = meta.first_line_year;

  const osmCount = railways.filter((r) => String(r.id).startsWith('osm-')).length;
  const hint = $('#rail-hint');
  if (hint) {
    hint.textContent = osmCount < 100
      ? `线路：${railways.length} 段（OSM ${osmCount}）。运行 merge_railway_cache.py 可增至 3000+ 段`
      : `线路：${railways.length} 段（OSM ${osmCount} + 史料 ${railways.length - osmCount}）`;
  }
  $('#intro-text').textContent =
    `1876年6月，中国全境铁路仅为上海至吴淞一条线。今日地图上有逾 ${meta.station_count.toLocaleString()} 座城际铁路枢纽（不含地铁站）。按播放，看全国铁路网如何展开。`;

  year = meta.start_year;
  setupEraPills();
  setupSearch();
  updateUI();

  whenLayoutReady(() => {
    setupMapZoom();
    drawMap();
    loadChinaOutline().then(() => requestAnimationFrame(drawMap));
  });

  $('#year-slider').addEventListener('input', (e) => setYear(Number(e.target.value)));
  $('#play-btn').addEventListener('click', togglePlay);
  $('#btn-first').addEventListener('click', () => setYear(meta.start_year));
  $('#btn-hsr').addEventListener('click', () => setYear(2008));
  $('#btn-zoom-in').addEventListener('click', () => {
    d3.select(canvas).transition().duration(200).call(zoomBehavior.scaleBy, 1.35);
  });
  $('#btn-zoom-out').addEventListener('click', () => {
    d3.select(canvas).transition().duration(200).call(zoomBehavior.scaleBy, 1 / 1.35);
  });
  $('#btn-zoom-reset').addEventListener('click', () => resetMapView(true));

  canvas.addEventListener('mousemove', (e) => {
    const rect = canvas.getBoundingClientRect();
    const s = findStationAt(e.clientX - rect.left, e.clientY - rect.top);
    if (s?.id !== hovered?.id) {
      hovered = s;
      requestAnimationFrame(drawMap);
    }
    showTooltip(s, e.clientX - rect.left, e.clientY - rect.top);
  });

  canvas.addEventListener('mouseleave', () => {
    hovered = null;
    $('#tooltip').style.display = 'none';
    requestAnimationFrame(drawMap);
  });

  window.addEventListener('resize', () => {
    if (setupProjection()) {
      resetMapView(false);
    }
  });
}

init().catch((err) => showFatal(`加载失败 Load error: ${err.message}`));
