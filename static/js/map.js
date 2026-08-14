// /map page JS — 由舊 MAP_HTML inline <script> 抽出。
// 用 Leaflet @1.9.4 + tar1090 fetch /api/live + dead-reckoning smooth move。
// base.html inline 已 inject window.T 同 window.LANG，呢度直接用。

// ===== Leaflet 地圖 =====
// 初始視野用闊 Japan 中心（唔透露接收機位置），有 live 機就即刻 fitBounds
const map = L.map('map', { zoomControl:true, attributionControl:true, worldCopyJump:true })
  .setView([37.5, 138.0], 5);
L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
  maxZoom: 18, subdomains:'abcd',
  attribution: '© OpenStreetMap © CARTO'
}).addTo(map);

// ===== 高度色階 / icon / label helpers =====
function altColor(ft) {
  if (ft == null) return '#9aa6a3';   // 落地 / 無高度 = 灰
  const t = Math.max(0, Math.min(1, ft / 40000));
  return `hsl(${(35 + t * 230).toFixed(0)}, 85%, 58%)`;   // 35°橙 → 265°紫
}
function trendArrow(rate) {
  if (rate == null) return '';
  if (rate > 256) return ' ↑';
  if (rate < -256) return ' ↓';
  return '';
}
const PLANE_SVG = '<svg viewBox="0 0 24 24" width="100%" height="100%"><path fill="currentColor" stroke="#031a14" stroke-width="0.7" d="M12 1.6 C12.6 1.6 13 2.4 13 4 L13 10.4 L21.6 15.4 L21.6 17.2 L13 14.6 L13 19.4 L15.2 21 L15.2 22.4 L12 21.4 L8.8 22.4 L8.8 21 L11 19.4 L11 14.6 L2.4 17.2 L2.4 15.4 L11 10.4 L11 4 C11 2.4 11.4 1.6 12 1.6 Z"/></svg>';
const HELI_SVG = '<svg viewBox="0 0 24 24" width="100%" height="100%"><g fill="currentColor" stroke="#031a14" stroke-width="0.6"><rect x="2.5" y="11.1" width="19" height="1.8" rx="0.9"/><rect x="11.1" y="2.5" width="1.8" height="19" rx="0.9"/><circle cx="12" cy="12" r="3"/><rect x="11.3" y="14.4" width="1.4" height="6.4"/><rect x="9" y="19.6" width="6" height="1.5" rx="0.7"/></g></svg>';
function isHeli(p) { return p.category === 'A7'; }
function acScale(p) {
  if (isHeli(p)) return 0.95;
  if (p.category === 'A1') return 0.78;
  if (p.category === 'A5') return 1.22;
  return 1;
}
function isEmerg(p) { return !!p.emergency || ['7500','7600','7700'].indexOf(p.squawk) >= 0; }
function emergTag(p) {
  if (p.squawk === '7500') return 'HIJACK';
  if (p.squawk === '7600') return 'NORDO';
  if (p.squawk === '7700' || p.emergency) return 'EMERG';
  return T.map_emerg;
}
function nameOf(p) { return p.flight || (p.hex || '').toUpperCase(); }
function altOf(p) { return (p.alt != null) ? Math.round(p.alt).toLocaleString() + ' ft' : '—'; }

function makeIcon(p) {
  const rot = (p.track != null) ? p.track : 0;
  const tag = isEmerg(p) ? `<span class="tag">${esc(emergTag(p))}</span>` : '';
  const html = `<div class="ac-wrap${isEmerg(p) ? ' emerg' : ''}">`
    + `<div class="ac" style="color:${altColor(p.alt)};transform:rotate(${rot}deg) scale(${acScale(p)})">${isHeli(p) ? HELI_SVG : PLANE_SVG}</div>`
    + `<div class="ac-lbl"><span class="fl">${esc(nameOf(p))}</span><span class="al">${esc(altOf(p))}${trendArrow(p.rate)}</span>${tag}</div></div>`;
  return L.divIcon({ className:'ac-icon', html, iconSize:[26,26], iconAnchor:[13,13] });
}
function syncLabel(p) {
  const el = p.marker.getElement();
  if (!el) return;
  const ac = el.querySelector('.ac');
  if (ac) {
    ac.style.transform = `rotate(${p.track != null ? p.track : 0}deg) scale(${acScale(p)})`;
    ac.style.color = altColor(p.alt);
  }
  const fl = el.querySelector('.ac-lbl .fl');
  if (fl) fl.textContent = nameOf(p);
  const wrap = el.querySelector('.ac-wrap');
  if (wrap) {
    wrap.classList.toggle('emerg', isEmerg(p));
    wrap.classList.toggle('stale', (p.seen != null && p.seen > 30));
  }
}
function setAltLabel(p, ft) {
  const el = p.marker.getElement();
  if (!el) return;
  const al = el.querySelector('.ac-lbl .al');
  if (al) al.textContent = ((ft != null) ? ft.toLocaleString() + ' ft' : '—') + trendArrow(p.rate);
}
function tipHTML(p) {
  const spd = (p.gs != null) ? Math.round(p.gs) + ' kt' : '—';
  return `<b>${esc(nameOf(p))}</b><br><span class="k">${esc(T.map_alt)}</span> ${altOf(p)} · <span class="k">${esc(T.map_spd)}</span> ${spd}`;
}
function prow(k, v) {
  return v ? `<div class="pr"><span class="pk">${esc(k)}</span><span class="pv">${esc(v)}</span></div>` : '';
}
function buildPopup(p) {
  const spd = (p.gs != null) ? Math.round(p.gs) + ' kt' : null;
  const vs = (p.rate != null) ? ((p.rate > 0 ? '+' : '') + Math.round(p.rate) + ' ft/min') : null;
  const hdg = (p.track != null) ? (Math.round(p.track) + '°') : null;
  const route = (p.from || p.to) ? `${p.from || '—'} › ${p.to || '—'}` : null;
  const fr24 = p.reg ? `https://www.flightradar24.com/data/aircraft/${p.reg.toLowerCase()}`
                     : `https://www.flightradar24.com/data/aircraft/${p.hex}`;
  const emTag = isEmerg(p) ? ` <span style="color:#ff5b5b;font-weight:700">⚠ ${esc(emergTag(p))}</span>` : '';
  let h = `<div class="pop"><div class="pop-h"><a href="/aircraft/${esc(p.hex)}/" style="color:inherit;text-decoration:none">${esc(nameOf(p))} ›</a>${emTag}</div>`;
  h += prow(T.map_reg, p.reg);
  h += prow(T.map_type, p.type);
  h += prow(T.map_op, p.operator);
  h += prow(T.map_country, p.country);
  h += prow(T.map_route, route);
  h += prow(T.map_alt, (p.alt != null) ? Math.round(p.alt).toLocaleString() + ' ft' : null);
  h += prow(T.map_vs, vs);
  h += prow(T.map_spd, spd);
  h += prow(T.map_hdg, hdg);
  h += prow('Squawk', p.squawk);
  h += prow('ICAO', (p.hex || '').toUpperCase());
  h += `<a class="pop-link" href="${fr24}" target="_blank" rel="noopener">${esc(T.map_fr24)} ↗</a>`;
  return h + '</div>';
}

// ===== state =====
const planes = {};
let firstFit = true;
let followHex = null;     // click 一架機跟住
let searchTerm = '';      // 搜尋 highlight
let catFilter = '';       // 機型 filter：'' / plane / heli / light / heavy
let altFilter = '';       // 高度帶 filter：'' / 'lo-hi'（ft）
const TRAIL_MAX = 80;     // 航跡保留點數（~4 分鐘 @3s）

function matchSearch(p) {
  if (!searchTerm) return null;
  const hay = [p.flight, p.reg, p.hex, p.operator].filter(Boolean).join(' ').toLowerCase();
  return hay.indexOf(searchTerm) >= 0;
}
function matchCat(p) {
  if (!catFilter) return true;
  if (catFilter === 'heli') return isHeli(p);
  if (catFilter === 'plane') return !isHeli(p);
  if (catFilter === 'light') return p.category === 'A1';
  if (catFilter === 'heavy') return p.category === 'A5';
  return true;
}
function matchAlt(p) {
  if (!altFilter) return true;
  if (p.alt == null) return false;
  const [lo, hi] = altFilter.split('-').map(Number);
  return p.alt >= lo && p.alt < hi;
}
function applyFilter() {
  // 綜合：機型 ∧ 高度帶（filter）+ search（highlight）。任一 filter 唔中 → dim。
  for (const hex in planes) {
    const p = planes[hex];
    const el = p.marker && p.marker.getElement();
    if (!el) continue;
    const wrap = el.querySelector('.ac-wrap');
    if (!wrap) continue;
    const filtOk = matchCat(p) && matchAlt(p);
    const s = matchSearch(p);   // null（冇 search）/ true / false
    wrap.classList.toggle('dim', !filtOk || s === false);
    wrap.classList.toggle('hit', s === true && filtOk);
  }
}
function renderEmergList() {
  const box = document.getElementById('emerg-list');
  if (!box) return;
  const ems = Object.keys(planes).filter(h => isEmerg(planes[h]));
  if (!ems.length) { box.hidden = true; box.innerHTML = ''; return; }
  box.hidden = false;
  box.innerHTML = `<div class="em-hdr">⚠ ${esc(T.map_emerg_hdr || 'EMERGENCY')}</div>`
    + ems.map(h => `<button type="button" class="em-row" data-hex="${esc(h)}">`
        + `<span class="em-tag">${esc(emergTag(planes[h]))}</span>`
        + `<span class="em-fl">${esc(nameOf(planes[h]))}</span></button>`).join('');
}

// 直升機群集事故 alert：頂部橫額 + 範圍圈 + member marker 高亮（query_live 計好）
let heliCircle = null;
function clearHeliHighlight() {
  for (const hex in planes) {
    const el = planes[hex].marker && planes[hex].marker.getElement();
    if (el) el.classList.remove('heli-cluster-on');
  }
}
function renderHeliCluster(hc) {
  const box = document.getElementById('heli-alert');
  if (!hc || !hc.active) {
    if (box) { box.hidden = true; box.innerHTML = ''; }
    if (heliCircle) { map.removeLayer(heliCircle); heliCircle = null; }
    clearHeliHighlight();
    return;
  }
  const msg = (T.map_heli_cluster || '⚠ {n} helicopters clustered — possible incident')
    .replace('{n}', hc.count);
  if (box) {
    box.hidden = false;
    box.innerHTML = `<button type="button" class="heli-alert-btn" `
      + `data-lat="${hc.center[0]}" data-lon="${hc.center[1]}">${esc(msg)}</button>`;
  }
  const r = (hc.radius_km || 8) * 1000;
  if (!heliCircle) {
    heliCircle = L.circle(hc.center, { radius:r, color:'#f5d96f', weight:2, opacity:0.85,
      fillColor:'#f5d96f', fillOpacity:0.07, interactive:false, className:'heli-cluster-circle' }).addTo(map);
  } else {
    heliCircle.setLatLng(hc.center); heliCircle.setRadius(r);
  }
  const set = new Set(hc.members || []);
  for (const hex in planes) {
    const el = planes[hex].marker && planes[hex].marker.getElement();
    if (el) el.classList.toggle('heli-cluster-on', set.has(hex));
  }
}

function extrap(fix, dt) {
  const ms = (fix.gs || 0) * 0.514444;        // kt -> m/s
  // Cap 5 秒（poll 係 3 秒一次，5 秒有餘裕，正常運作完全唔受影響）。
  // 舊值 30 秒太闊：ADS-B 收唔穩、架機由 feed 消失十幾秒係家常便飯，
  // 而外推係假設「直線等速」。架機喺中斷期間轉彎或者減速（東京附近埋場成日咁），
  // marker 就會直飛幾公里出去，一收返真位置即刻 snap 返轉頭 —— 即係「飛機跳返後面」。
  // 實測倒退幅度：中斷 10s 轉 30° = −711m、15s 轉 40° = −1,478m、20s 轉 60° = −3,241m。
  // 收窄到 5 秒之後全部變成向前修正（+18m ~ +838m），睇落係追上去，唔會倒退。
  const dist = ms * Math.min(dt, 5);
  const rad = (fix.track || 0) * Math.PI/180;
  const dLat = (dist * Math.cos(rad)) / 111320;
  const dLon = (dist * Math.sin(rad)) / (111320 * Math.cos(fix.lat * Math.PI/180));
  return { lat: fix.lat + dLat, lon: fix.lon + dLon };
}

// poll 係 async 兼由 setInterval 每 3 秒叫一次，request 有機會並行。
// fetch 一慢，舊 request 就可以遲過新 request 返到 —— 舊 response 帶住舊位置，
// 覆蓋咗新位置就會令 marker 跳返後面。用序號只接受「至今最新」嗰個 response。
let pollSeq = 0, pollApplied = 0;

async function poll() {
  const seq = ++pollSeq;
  let data;
  try { data = await (await fetch('/api/live')).json(); }
  catch (e) { return; }
  if (seq < pollApplied) return;   // 有更新嘅 response 已經套用咗，呢個係遲到嘅舊嘢
  pollApplied = seq;
  const list = data.aircraft || [];
  const now = performance.now();
  // 份快照由 server 攞到之後喺 cache 度停留咗幾耐（0～1 秒，逐次 poll 都唔同）。
  // 唔加返落 seen_pos 度，位置年齡就會隨機少計，marker 會不停前後抖。
  const snapAge = Math.max(0, Number(data.snapshot_age) || 0);
  const seen = new Set();
  const fitPts = [];
  for (const a of list) {
    if (a.lat == null || a.lon == null) continue;
    seen.add(a.hex);
    fitPts.push([a.lat, a.lon]);
    let p = planes[a.hex];
    // 時間戳一定要倒推返「真正觀測到呢個位置」嗰刻，唔可以用到達時間。
    // tar1090 收唔到新位置嗰陣會一直回同一個座標、seen_pos 一路變大。
    // 若果照 stamp `now`，每次 poll 都會將 dt 重設做 0 → target 彈返舊座標，
    // 而 marker 已經外推咗 3 秒 → 每 3 秒倒退一次（實測見過 seen_pos 48 秒）。
    // 倒推之後 fix.t 對同一個觀測維持不變，dt 連續遞增，配合 extrap 個 5 秒 cap
    // 就會停喺原地等新資料，唔會前後彈。
    // seen_pos 係「快照生成嗰刻」個位置幾舊，要加返快照本身喺 cache 停留嗰段時間
    const posAge = (Math.max(0, Number(a.seen_pos ?? a.seen ?? 0)) || 0) + snapAge;
    const fix = { lat:a.lat, lon:a.lon, track:a.track, gs:a.gs, t: now - posAge * 1000 };
    if (!p) {
      p = planes[a.hex] = {
        marker:null, trailLine:null, trail:[[a.lat, a.lon]],
        fix, disp:{lat:a.lat, lon:a.lon},
        hex:a.hex, lastSeen:now, rot:(a.track!=null?a.track:0),
        altFix:a.alt, rate:a.rate, altT:now, dispAlt:a.alt, altShown:null,
        flight:a.flight, alt:a.alt, gs:a.gs, track:a.track,
        reg:a.reg, type:a.type, operator:a.operator, country:a.country, from:a.from, to:a.to,
        squawk:a.squawk, emergency:a.emergency, category:a.category, seen:a.seen,
      };
      p.trailLine = L.polyline(p.trail, { color:altColor(a.alt), weight:1.6, opacity:0.4, interactive:false }).addTo(map);
      p.marker = L.marker([a.lat, a.lon], { icon: makeIcon(p) })
        .bindTooltip('', { className:'ac-tip', direction:'top', offset:[0,-10], opacity:1 })
        .bindPopup('', { className:'ac-pop', maxWidth:280, autoPan:true })
        .addTo(map);
      p.marker.on('click', () => {
        followHex = p.hex;
        p.marker.setPopupContent(buildPopup(p));
        p.marker.openPopup();
      });
    } else {
      p.fix = fix; p.lastSeen = now;
      p.altFix = a.alt; p.rate = a.rate; p.altT = now;
      if (p.dispAlt == null) p.dispAlt = a.alt;
      p.flight = a.flight; p.alt = a.alt; p.gs = a.gs; p.track = a.track;
      p.reg = a.reg; p.type = a.type; p.operator = a.operator;
      p.country = a.country; p.from = a.from; p.to = a.to;
      p.squawk = a.squawk; p.emergency = a.emergency; p.category = a.category; p.seen = a.seen;
      p.trail.push([a.lat, a.lon]);
      if (p.trail.length > TRAIL_MAX) p.trail.shift();
      if (p.trailLine) {
        p.trailLine.setLatLngs(p.trail);
        p.trailLine.setStyle({ color: altColor(a.alt) });
      }
    }
    p.marker.setTooltipContent(tipHTML(p));
    syncLabel(p);
    if (p.marker.isPopupOpen()) p.marker.setPopupContent(buildPopup(p));
  }
  // 移走出區（45 秒冇再見）嘅機（連航跡）
  for (const hex in planes) {
    if (!seen.has(hex) && (now - planes[hex].lastSeen) > 45000) {
      map.removeLayer(planes[hex].marker);
      if (planes[hex].trailLine) map.removeLayer(planes[hex].trailLine);
      if (followHex === hex) followHex = null;
      delete planes[hex];
    }
  }
  const hexes = Object.keys(planes);
  const n = hexes.length;
  const emg = hexes.filter(h => isEmerg(planes[h])).length;
  document.getElementById('cnt').textContent = n ? (n + ' ' + T.map_unit) : T.map_empty;
  document.getElementById('emerg-cnt').textContent = emg ? ('⚠ ' + emg + ' ' + T.map_emerg) : '';
  applyFilter();
  renderEmergList();
  renderHeliCluster(data.heli_cluster);
  if (firstFit && fitPts.length) {
    firstFit = false;
    try { map.fitBounds(fitPts, { padding:[40,40], maxZoom:10 }); } catch (e) {}
  }
}
poll();
setInterval(poll, 3000);

// ===== 平滑移動（dead-reckoning + lerp，似 FR24）=====
function animate() {
  const now = performance.now();
  // 錯誤隔離一定要落到**逐架機**。包喺 for 外面係唔夠嘅：壞嗰架會令迴圈
  // 每一幀都喺同一點斷開，排喺佢後面嘅飛機就會永久停擺（loop 睇落仲行緊，
  // 但下半批機唔郁）。逐架包先至只損失出事嗰架。
  for (const hex in planes) {
    try { animatePlane(planes[hex], now); }
    catch (e) { /* 跳過呢架，其餘照行 */ }
  }
  try {
    if (followHex && planes[followHex]) {
      const d = planes[followHex].disp;
      map.setView([d.lat, d.lon], map.getZoom(), { animate: false });
    }
  } catch (e) { /* 跟機失敗唔可以殺 loop */ }
  // 擺喺所有 try 外面：上面冇嘢會拋出嚟，所以呢行必定行到，rAF 鏈唔會斷
  requestAnimationFrame(animate);
}

function animatePlane(p, now) {
  const target = extrap(p.fix, (now - p.fix.t) / 1000);
  p.disp.lat += (target.lat - p.disp.lat) * 0.12;
  p.disp.lon += (target.lon - p.disp.lon) * 0.12;
  p.marker.setLatLng([p.disp.lat, p.disp.lon]);

  // 高度即時跳動：用 baro_rate 外推 + lerp，按 25 ft 級更新 label
  if (p.altFix != null) {
    const dtA = Math.min((now - p.altT) / 1000, 60);
    const tgtAlt = p.altFix + (p.rate || 0) / 60 * dtA;
    p.dispAlt += (tgtAlt - p.dispAlt) * 0.15;
    const r = Math.round(p.dispAlt / 25) * 25;
    if (r !== p.altShown) { p.altShown = r; setAltLabel(p, r); }
  }
}
requestAnimationFrame(animate);

// 搜尋：highlight 命中、其餘變淡 + clear ✕
const searchBox = document.getElementById('search');
const clearBtn = document.getElementById('search-clear');
function updateClear() { if (clearBtn) clearBtn.hidden = !searchTerm; }
if (searchBox) searchBox.addEventListener('input', () => {
  searchTerm = searchBox.value.trim().toLowerCase();
  updateClear();
  applyFilter();
});
if (clearBtn) clearBtn.addEventListener('click', () => {
  searchBox.value = ''; searchTerm = ''; updateClear(); applyFilter(); searchBox.focus();
});
// 機型 / 高度帶 filter
const catSel = document.getElementById('cat-filter');
if (catSel) catSel.addEventListener('change', () => { catFilter = catSel.value; applyFilter(); });
const altSel = document.getElementById('alt-filter');
if (altSel) altSel.addEventListener('change', () => { altFilter = altSel.value; applyFilter(); });
// emergency 側欄：click 一行 → 跟機 + 開 popup
const emergBox = document.getElementById('emerg-list');
if (emergBox) emergBox.addEventListener('click', (e) => {
  const row = e.target.closest('.em-row');
  if (!row) return;
  const p = planes[row.dataset.hex];
  if (!p) return;
  followHex = p.hex;
  p.marker.setPopupContent(buildPopup(p));
  p.marker.openPopup();
  map.setView([p.disp.lat, p.disp.lon], Math.max(map.getZoom(), 8), { animate: true });
});
// 直升機群集橫額：click → pan 去 cluster 中心
const heliBox = document.getElementById('heli-alert');
if (heliBox) heliBox.addEventListener('click', (e) => {
  const btn = e.target.closest('.heli-alert-btn');
  if (!btn) return;
  map.setView([parseFloat(btn.dataset.lat), parseFloat(btn.dataset.lon)],
    Math.max(map.getZoom(), 11), { animate: true });
});
// click 空白地圖 / 拖地圖 → 取消跟機
map.on('mousedown', () => { followHex = null; });

// ===== 天氣圖層（雲 / 雨雲 / 大風區）=====
// 三個源全部免 API key、有 CORS，browser 直接打，唔經 Django。
// 鐵律：天氣壞咗唔可以拖冧飛機圖 —— 下面每個 fetch 都包 try/catch，
// 失敗就靜靜哋唔畫，/api/live 個 3 秒 poll 同 marker 動畫照行。
const JMA_BASE = 'https://www.jma.go.jp/bosai';
// 兩層各自跟返自己個源嘅節奏，唔好夾硬用同一個 interval：
//   Himawari 日本域：實測 864 幀 / 36 小時，863 個間隔全部 2 分鐘
//   JMA hrpns：實測 37 幀，36 個間隔全部 5 分鐘
// Poll 只係攞個細 JSON（衛星 gzip 4.1KB、雨雲 304B），而 Leaflet 個 setUrl
// 見到 URL 冇變會自動 noRedraw，唔會重下載 tile，所以密少少冇代價。
const CLOUD_REFRESH_MS = 2 * 60 * 1000;
const RAIN_REFRESH_MS = 5 * 60 * 1000;
// 日本境外冇資料，用 bounds 擋住，唔好白費 request
const JP_RAIN_BOUNDS = L.latLngBounds([[20, 118], [48, 150]]);
const JP_SAT_BOUNDS = L.latLngBounds([[12, 110], [55, 165]]);

// 陣風分段（kt）。色跟返 emergency 色系由淺到深，同 --amber 一路去 #ff5b5b。
const WIND_BANDS = [[45, '#ff5b5b'], [35, '#ff9a3c'], [25, '#f5d96f']];
const WIND_MIN_KT = WIND_BANDS[WIND_BANDS.length - 1][0];
const WIND_COLS = 6, WIND_ROWS = 7;          // 42 點：實測 40 點 ≈ 14.8KB / 1.6s
const WIND_DEBOUNCE_MS = 600;
// Open-Meteo 免費 API 條款：資料以 CC-BY 4.0 提供、限非商業用途。
// CC BY 4.0 第 3.a.1 要求三樣：來源、授權（連結）、**同埋有冇改過**
// —— 「indicate if You modified the Licensed Material」。
// 我哋唔係原樣顯示數值：攞 wind_speed_10m / wind_gusts_10m 取大值、
// 分 25/35/45kt 三段門檻、再砌成 6×7 網格色塊，屬於加工，所以「を加工」唔可以慳
// （同兩個気象庁圖層一致）。
const WIND_ATTRIB = '<a href="https://open-meteo.com/" target="_blank" rel="noopener">Open-Meteo</a>'
  + '（<a href="https://creativecommons.org/licenses/by/4.0/" target="_blank" rel="noopener">CC BY 4.0</a>）を加工';

function windColor(kt) {
  for (const [min, color] of WIND_BANDS) if (kt >= min) return color;
  return null;
}

// toggle 狀態（localStorage 記住）。要喺下面啲 refreshXxx / refreshWind 之前定義，
// 佢哋開頭就會讀 wxOn 決定 load 完之後使唔使即刻上圖。
const WX_STORE = 'ph_map_wx';
const wxOn = (() => {
  const off = { cloud: false, rain: false, wind: false };
  try { return Object.assign(off, JSON.parse(localStorage.getItem(WX_STORE) || '{}')); }
  catch (e) { return off; }
})();

function saveWx() {
  try { localStorage.setItem(WX_STORE, JSON.stringify(wxOn)); } catch (e) { /* 私隱模式 */ }
}

// 攞 JMA targetTimes（雨雲同衛星格式唔同：雨雲要 [0]，衛星要最後一個）
async function jmaLatest(url, pickLast) {
  const r = await fetch(url, { cache: 'no-store' });
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  const list = await r.json();
  if (!Array.isArray(list) || !list.length) throw new Error('empty targetTimes');
  return pickLast ? list[list.length - 1] : list[0];
}

// --- 雨雲：JMA 高解像度降水ナウキャスト（250m）---
// JMA 個 tile pyramid **淨係有雙數 zoom**。同一個有雨嘅點實測：
//   z4 1448B / z5 334B / z6 4217B / z7 334B / z8 3533B / z9 334B / z10 297B
// 即係單數 zoom（同 z10 以上）一律回 334B 空 tile —— HTTP 200，冇 error，
// 淨係乜都唔畫。所以用戶 zoom 一級雨雲就會「消失」，再 zoom 一級又返嚟。
// Leaflet 冇「只用雙數 zoom」呢個 option，唯有 override _clampZoom：
// 地圖喺 z7 就攞 z6 tile 放大，永遠唔會叫到空 tile。
const RAIN_MIN_Z = 4, RAIN_MAX_Z = 8;
const RainTileLayer = L.TileLayer.extend({
  _clampZoom(zoom) {
    return Math.max(RAIN_MIN_Z, Math.min(RAIN_MAX_Z, Math.floor(zoom / 2) * 2));
  },
});
let rainLayer = null;
async function refreshRain() {
  try {
    const t = await jmaLatest(`${JMA_BASE}/jmatile/data/nowc/targetTimes_N1.json`, false);
    const url = `${JMA_BASE}/jmatile/data/nowc/${t.basetime}/none/${t.validtime}`
      + '/surf/hrpns/{z}/{x}/{y}.png';
    if (rainLayer) { rainLayer.setUrl(url); return; }
    // tile zoom 由上面 _clampZoom 全權決定（雙數、夾 4-8），所以唔設 maxNativeZoom。
    // maxZoom 要留返 18：Leaflet 喺 _setView 會用未 clamp 嘅 zoom 同佢比，
    // 細過地圖 max 就會整層收起。
    rainLayer = new RainTileLayer(url, {
      maxZoom: 18, opacity: 0.6, bounds: JP_RAIN_BOUNDS,
      // 気象庁「公共データ利用規約 第1.0版」要求：(1) 寫明出典 + 該頁 URL、
      // (2) 有編集・加工就要另外註明加工咗。呢度 tile 疊落自己張地圖兼調過透明度，
      // 屬於加工，所以「を加工」唔可以慳。
      attribution: '出典：<a href="https://www.jma.go.jp/bosai/nowc/" target="_blank" rel="noopener">気象庁ナウキャスト</a>を加工',
    });
    if (wxOn.rain) rainLayer.addTo(map);
  } catch (e) { /* JMA 死咗就當冇雨雲，唔好阻住飛機圖 */ }
}

// --- 雲：Himawari-9 紅外（B13/TBB）---
// 一定要用紅外：可見光同真彩色喺日本夜晚係全黑，IR 日夜都有雲。
let cloudLayer = null;
async function refreshCloud() {
  try {
    const t = await jmaLatest(`${JMA_BASE}/himawari/data/satimg/targetTimes_jp.json`, true);
    const url = `${JMA_BASE}/himawari/data/satimg/${t.basetime}/jp/${t.validtime}`
      + '/B13/TBB/{z}/{x}/{y}.jpg';
    if (cloudLayer) { cloudLayer.setUrl(url); return; }
    cloudLayer = L.tileLayer(url, {
      // 實測 z3-z6 有資料，z2 同 z7 都係 404 —— 兩邊都要夾，
      // 淨係設 max 嘅話 zoom 出去 z2 一樣會成版 404 兼冇雲
      minNativeZoom: 3, maxNativeZoom: 6, maxZoom: 18, opacity: 0.55, bounds: JP_SAT_BOUNDS,
      // IR 係灰階，黑底會冚實張地圖 → CSS 用 mix-blend-mode:screen 剩返亮嘅雲
      className: 'wx-ir-tiles',
      // 同上；呢層仲落咗 CSS filter（brightness/contrast）同 screen blend，
      // 加工程度更明顯，一定要聲明。
      attribution: '出典：<a href="https://www.jma.go.jp/bosai/map.html#contents=himawari" target="_blank" rel="noopener">気象庁ひまわり</a>を加工',
    });
    if (wxOn.cloud) cloudLayer.addTo(map);
  } catch (e) { /* 同上 */ }
}

// --- 大風區：Open-Meteo 網格，陣風超門檻先著色 ---
const windLayer = L.layerGroup();
let windKey = '';          // 已經畫咗嗰個 viewport 嘅 key（zoom + 四捨五入 bbox）
let windTimer = null;
let windBusy = false;
let windAgain = false;     // fetch 途中又郁過 → 完事補跑一次

async function refreshWind() {
  if (!wxOn.wind) return;
  // 有 fetch 未返就唔好並行打，但一定要記低「仲要再跑」：
  // debounce timer 已經燒完，唔補飛嘅話 pan 落新範圍嗰下啱撞正 in-flight，
  // 用戶停低之後就永遠冇風資料（冇下一個 moveend 嚟救）。
  if (windBusy) { windAgain = true; return; }

  const b = map.getBounds();
  // worldCopyJump 開咗，pan 過日界線 lon 會爆出 ±180，一定要 clamp
  const west = Math.max(-180, b.getWest()), east = Math.min(180, b.getEast());
  const south = Math.max(-85, b.getSouth()), north = Math.min(85, b.getNorth());
  if (!(east > west && north > south)) return;
  const key = [map.getZoom(), west, south, east, north].map(v => Number(v).toFixed(1)).join(',');
  if (key === windKey) return;

  const dLat = (north - south) / WIND_ROWS, dLon = (east - west) / WIND_COLS;
  const cells = [];
  for (let r = 0; r < WIND_ROWS; r++) {
    for (let c = 0; c < WIND_COLS; c++) {
      cells.push({ s: south + r * dLat, w: west + c * dLon });
    }
  }
  const lats = cells.map(c => (c.s + dLat / 2).toFixed(3)).join(',');
  const lons = cells.map(c => (c.w + dLon / 2).toFixed(3)).join(',');

  windBusy = true;
  try {
    const r = await fetch('https://api.open-meteo.com/v1/forecast'
      + `?latitude=${lats}&longitude=${lons}`
      + '&current=wind_speed_10m,wind_gusts_10m&wind_speed_unit=kn', { cache: 'no-store' });
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    const data = await r.json();
    // await 期間用戶可能已經熄咗個圖層 —— 唔好再寫入已經由地圖移走嘅 layer，
    // 否則下次撳返著會見到一批冇人 clear 過嘅舊格仔。
    if (!wxOn.wind) return;
    const pts = Array.isArray(data) ? data : [data];
    windLayer.clearLayers();
    pts.forEach((p, i) => {
      const cell = cells[i];
      if (!cell || !p.current) return;
      const kt = Math.max(p.current.wind_gusts_10m ?? 0, p.current.wind_speed_10m ?? 0);
      const color = windColor(kt);
      if (!color) return;
      L.rectangle([[cell.s, cell.w], [cell.s + dLat, cell.w + dLon]], {
        color, weight: 0, fillColor: color,
        fillOpacity: 0.1 + Math.min(0.18, (kt - WIND_MIN_KT) / 100),
        interactive: false,          // 唔好搶飛機 marker 嘅 click（同 heliCircle 一樣）
      }).addTo(windLayer);
    });
    windKey = key;
  } catch (e) {
    // Open-Meteo 死咗 / 超額：清走舊格仔。舊 viewport 嗰批位置已經唔啱，
    // 留喺度會變成「錯地方有大風」，比乜都唔顯示更誤導。
    windLayer.clearLayers();
    windKey = '';
  } finally {
    windBusy = false;
    // 補飛：fetch 途中郁過就再跑一次，攞返最新 viewport
    if (windAgain) { windAgain = false; scheduleWind(); }
  }
}

function scheduleWind() {
  if (!wxOn.wind) return;
  clearTimeout(windTimer);
  windTimer = setTimeout(refreshWind, WIND_DEBOUNCE_MS);
}
map.on('moveend', scheduleWind);

// --- toggle 掣 ---
function applyWx(kind) {
  const on = wxOn[kind];
  const btn = document.getElementById(`wx-${kind}`);
  if (btn) { btn.classList.toggle('on', on); btn.setAttribute('aria-pressed', String(on)); }
  if (kind === 'rain' && rainLayer) on ? rainLayer.addTo(map) : map.removeLayer(rainLayer);
  if (kind === 'cloud' && cloudLayer) on ? cloudLayer.addTo(map) : map.removeLayer(cloudLayer);
  if (kind === 'wind') {
    // L.layerGroup 冇 attribution option，要自己掛落 attribution control
    if (on) {
      windLayer.addTo(map);
      map.attributionControl.addAttribution(WIND_ATTRIB);
      refreshWind();
    } else {
      clearTimeout(windTimer);
      windLayer.clearLayers();
      map.removeLayer(windLayer);
      map.attributionControl.removeAttribution(WIND_ATTRIB);
      // windAgain 一定要一齊清：唔清嘅話熄咗之後 in-flight 嗰個 finally
      // 仍然會 scheduleWind()，撳返著先發現個 key 已經係舊 viewport
      windKey = '';
      windAgain = false;
    }
  }
}

['cloud', 'rain', 'wind'].forEach((kind) => {
  const btn = document.getElementById(`wx-${kind}`);
  if (!btn) return;
  btn.addEventListener('click', () => { wxOn[kind] = !wxOn[kind]; saveWx(); applyWx(kind); });
  applyWx(kind);   // 還原上次狀態（layer 未 load 好時 refreshXxx 會自己補 addTo）
});

refreshRain();
refreshCloud();
setInterval(refreshRain, RAIN_REFRESH_MS);
setInterval(refreshCloud, CLOUD_REFRESH_MS);
