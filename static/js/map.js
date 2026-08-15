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
// 漸變色階，唔用硬門檻。原本 25/35/45kt 分段嘅問題：「大風區」按定義係例外
// 狀況，實測關東地面陣風成日淨係 6–24kt，於是成個掣八成時間都係空白，用起上嚟
// 似壞咗。改成超過一個低底就著色、風愈大色愈深，咁就一定睇到強弱分佈，
// 而真係大風嗰啲區域一樣突出。
const WIND_FLOOR_KT = 10;    // 低過呢個唔畫，否則成張圖都染到一片
const WIND_TOP_KT = 60;      // 色階上限，再大都當最深
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

// 0 = 剛過底線，1 = 到頂。畀色同透明度共用，兩樣一齊隨風速加深。
function windRatio(kt) {
  if (!(kt >= WIND_FLOOR_KT)) return null;
  return Math.min(1, (kt - WIND_FLOOR_KT) / (WIND_TOP_KT - WIND_FLOOR_KT));
}

// 黃 → 橙 → 紅。特登唔行 altColor 條橙→紫色階，免得同高度圖例撈亂。
function windColor(kt) {
  const t = windRatio(kt);
  return t === null ? null : `hsl(${Math.round(60 - t * 60)}, 85%, 55%)`;
}

// 色階圖例：淨係喺大風圖層開咗先出，唔好長期霸住 toolbar
function setWindLegend(show) {
  const el = document.getElementById('wind-legend');
  if (el) el.hidden = !show;
}

// 撳掣旁邊顯示視野內最大風速，令低風日子都知道個掣行緊、而家幾大風
function setWindMaxLabel(kt) {
  const el = document.getElementById('wx-wind-max');
  if (!el) return;
  if (kt == null) { el.textContent = ''; el.hidden = true; return; }
  el.textContent = `${Math.round(kt)}kt`;
  el.hidden = false;
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
// fetch() **冇 default timeout**：對面唔回應（TCP 黑洞）個 promise 可以永遠唔 settle。
// 雨雲個 refresh 係序列化嘅，一 hang 就會令 rainRunning 永遠卡住 true，
// 之後連用戶撳掣都開唔到雨雲。所以所有外部 fetch 一律要用 AbortController 封頂。
const WX_FETCH_TIMEOUT_MS = 15000;

async function fetchJsonTimeout(url, timeoutMs) {
  const ac = new AbortController();
  const timer = setTimeout(() => ac.abort(), timeoutMs);
  try {
    const r = await fetch(url, { cache: 'no-store', signal: ac.signal });
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    return await r.json();
  } finally {
    clearTimeout(timer);
  }
}

async function jmaLatest(url, pickLast) {
  const list = await fetchJsonTimeout(url, WX_FETCH_TIMEOUT_MS);
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
// 動畫：播最近 6 幀（5 分鐘一幀 = 半個鐘）睇到雨區真係喺度郁。
// 特登用真實歷史幀，唔用 CSS 平移做假動感 —— 郁錯方向就係竄改氣象資訊，
// 亦違反気象庁「唔可以令人以為係國家做嘅」嗰條。
const RAIN_FRAMES = 6;
const RAIN_FRAME_MS = 600;        // 每幀停留
const RAIN_LAST_HOLD_MS = 1800;   // 播到最新一幀停耐啲，睇清楚「而家」先 loop
const RAIN_OPACITY = 0.6;
// 気象庁「公共データ利用規約 第1.0版」：要出典 + 該頁 URL，有加工要另外聲明。
const RAIN_ATTRIB = '出典：<a href="https://www.jma.go.jp/bosai/nowc/" target="_blank" rel="noopener">気象庁ナウキャスト</a>を加工';

let rainFrames = [];       // [{time, layer}]，舊 → 新，播緊嗰批
// 換代期間降級嘅上一批：新 tile 未 load 完之前佢要留喺地圖頂住顯示。
// 一定要 module-level 唔可以做 local —— 做 local 嘅話熄圖層 / 被更新一批插隊
// 兩種情況都冇人拆得走佢，會遺留喺地圖上（其中一幀仲係 opacity 0.6，
// 即係撳熄咗個掣但雨雲照樣顯示）。
let rainStale = [];
let rainFramesKey = '';
// refreshRain 一次只准跑一個。之前試過用「入場序號 + 接手世代」畀佢哋並行再排先後，
// 但重疊嘅 async 換代衍生咗一長串邊界情況（舊 response 蓋過新、早退嗰次誤搶世代、
// fetch 快慢令次序倒轉…）。直接序列化就令「同時有兩次換代」根本唔可能發生，
// 成類問題一次過消失，亦唔再需要嗰兩個號。
// 跑緊嗰陣再嚟嘅呼叫唔會排隊堆積，只會標記「跑完再跑一次」（收斂到最新狀態）。
let rainRunning = false;
let rainQueued = false;

async function refreshRain() {
  if (rainRunning) { rainQueued = true; return; }
  rainRunning = true;
  try {
    do {
      rainQueued = false;
      await doRefreshRain();
    } while (rainQueued);
  } finally {
    rainRunning = false;
  }
}
let rainIdx = 0;
let rainTimer = null;

function dropRainLayers(list) { list.forEach(f => map.removeLayer(f.layer)); }
function dropStaleRain() { dropRainLayers(rainStale); rainStale = []; }

// 呢批入面有冇一幀真係喺地圖上見到（唔止 opacity——removeLayer 唔會 reset opacity，
// 所以要連 hasLayer 一齊查，否則已經拆走嘅圖層都會被當成「仲顯示緊」）。
function rainShowing(list) {
  return list.some(f => map.hasLayer(f.layer) && (f.layer.options.opacity || 0) > 0);
}

function rainTileUrl(t) {
  return `${JMA_BASE}/jmatile/data/nowc/${t.basetime}/none/${t.validtime}`
    + '/surf/hrpns/{z}/{x}/{y}.png';
}

function stopRainLoop() { clearTimeout(rainTimer); rainTimer = null; }

// basetime / validtime 係 UTC（實測最新幀距今幾分鐘），顯示要 +9 轉 JST
function setRainTimeLabel(ts) {
  const el = document.getElementById('wx-rain-time');
  if (!el) return;
  if (!ts) { el.textContent = ''; el.hidden = true; return; }
  const utc = Date.UTC(+ts.slice(0, 4), +ts.slice(4, 6) - 1, +ts.slice(6, 8),
                       +ts.slice(8, 10), +ts.slice(10, 12), 0);
  const j = new Date(utc + 9 * 3600 * 1000);
  el.textContent = `${pad(j.getUTCHours())}:${pad(j.getUTCMinutes())}`;
  el.hidden = false;
}

function showRainFrame() {
  if (!rainFrames.length) return;
  // 只切 opacity，唔換 URL —— tile 已經 load 好，切換先至冇閃白
  rainFrames.forEach((f, i) => f.layer.setOpacity(i === rainIdx ? RAIN_OPACITY : 0));
  setRainTimeLabel(rainFrames[rainIdx].time);
  const isLast = rainIdx === rainFrames.length - 1;
  rainTimer = setTimeout(() => {
    rainIdx = isLast ? 0 : rainIdx + 1;
    showRainFrame();
  }, isLast ? RAIN_LAST_HOLD_MS : RAIN_FRAME_MS);
}

function startRainLoop() {
  stopRainLoop();
  if (!rainFrames.length || !wxOn.rain) return;
  rainIdx = rainFrames.length - 1;   // 由最新一幀入手，一撳著就見到「而家」
  showRainFrame();
}

// 等一批 tile layer 真係載完，順便數實際成功／失敗嘅 tile。
// 回 {ready, stats}：
//   ready = 全部 layer 都 fire 過 'load'（唔係俾 timeout 迫出嚟）
//   stats = **逐層**嘅 {loaded, failed} tile 數，同 layers 一一對應
// stats 一定要逐層分開，唔可以加埋做一個總數：6 幀入面得 1 幀有圖都會令總數 > 0，
// 當成整批成功切咗過去，結果播 6 幀有 5 幀係空白。
// 一定要有 timeout 保底：圖層完全喺 bounds 外時根本冇 tile，'load' 唔會 fire。
// 而且淨係等 'load' 唔夠 —— Leaflet 個 'load' **連載失敗嘅 tile 都當完成**，
// 全部 404 一樣照 fire，所以要靠 stats 分辨真定假。
function whenTilesReady(layers, timeoutMs) {
  return new Promise((resolve) => {
    let pending = layers.length, settled = false;
    const stats = layers.map(() => ({ loaded: 0, failed: 0 }));
    const hooks = layers.map((l, i) => {
      const onLoad = () => { stats[i].loaded++; };
      const onErr = () => { stats[i].failed++; };
      l.on('tileload', onLoad);
      l.on('tileerror', onErr);
      return { l, onLoad, onErr };
    });
    const finish = (ready) => {
      if (settled) return;
      settled = true;
      hooks.forEach(h => { h.l.off('tileload', h.onLoad); h.l.off('tileerror', h.onErr); });
      resolve({ ready, stats });
    };
    if (!pending) return finish(true);
    layers.forEach(l => l.once('load', () => { if (--pending <= 0) finish(true); }));
    setTimeout(() => finish(false), timeoutMs);
  });
}

const RAIN_SWAP_TIMEOUT_MS = 10000;

// 淨係畀上面個序列化 wrapper 叫。因為保證唔會同自己重疊，呢度只需要處理
// 「跑緊嗰陣用戶熄咗雨雲」呢一種外部變化（每個 await 之後 re-check wxOn.rain）。
async function doRefreshRain() {
  // 呢次呼叫自己起嘅圖層。任何 bail 都要自己收拾，唔可以留低喺地圖上。
  let mine = [];
  let committed = false;
  try {
    const list = await fetchJsonTimeout(
      `${JMA_BASE}/jmatile/data/nowc/targetTimes_N1.json`, WX_FETCH_TIMEOUT_MS);
    if (!Array.isArray(list) || !list.length) throw new Error('empty targetTimes');

    // targetTimes 排新→舊，reverse 做舊→新；順住播就係雨區真實移動方向
    const want = list.slice(0, RAIN_FRAMES).reverse();
    const key = want.map(t => t.basetime).join(',');
    // 「冇新幀就唔重砌」呢個慳 request 嘅早退，淨係喺畫面真係仲掛住嗰批先算數。
    // 單靠 key 相同唔夠：熄咗之後圖層已經拆晒，key 一樣但畫面係空嘅，要照重砌。
    const mounted = rainFrames.length && rainFrames.every(f => map.hasLayer(f.layer));
    if (key === rainFramesKey && mounted) return;

    rainFramesKey = key;

    // 先停舊 loop：唔停嘅話佢下一 tick 會讀到已經換咗嘅 rainFrames，
    // 即刻將 opacity 落喺未 load 完嘅新 tile 上面。停咗之後舊嗰幀維持顯示，
    // 等新嗰批載好先無縫換代 —— 中間唔會出現空白。
    stopRainLoop();
    // 降級邊一批做「頂住顯示」嗰批，要睇邊批真係見到嘢，唔可以盲目用 rainFrames：
    // 換代等緊嗰陣又有新一批插隊嘅話，rainFrames 自己都仲係全透明（載緊），
    // 盲目降級就會拆走唯一顯示緊嗰批，令雨雲一片空白（實測見過 可見=0）。
    if (rainShowing(rainFrames)) {
      dropStaleRain();          // 舊 stale 冇用喇，即刻清走，唔好累積
      rainStale = rainFrames;
    } else {
      // rainFrames 一幀都未上過台 → 直接掉，留返真係頂住顯示嗰批做 stale
      dropRainLayers(rainFrames);
    }
    mine = want.map(t => ({
      time: t.validtime,
      // tile zoom 由 _clampZoom 全權決定（雙數、夾 4-8），所以唔設 maxNativeZoom。
      // maxZoom 要留返 18：Leaflet 喺 _setView 用未 clamp 嘅 zoom 同佢比，
      // 細過地圖 max 就會整層收起。
      layer: new RainTileLayer(rainTileUrl(t), {
        maxZoom: 18, opacity: 0, bounds: JP_RAIN_BOUNDS, attribution: RAIN_ATTRIB,
      }),
    }));
    rainFrames = mine;
    if (!wxOn.rain) { dropRainLayers(mine); dropStaleRain(); return; }

    // opacity 0 落場，等 tile 到齊先切；6 幀 × 廿幾格，慢網可以行好耐，
    // 所以唔可以好似之前咁拍個 1.5 秒定值就拆舊嗰批。
    mine.forEach(f => f.layer.addTo(map));
    const { stats } = await whenTilesReady(mine.map(f => f.layer), RAIN_SWAP_TIMEOUT_MS);

    // 等 tile 期間唯一可能變嘅係用戶熄咗雨雲（序列化之後唔會有另一次換代插隊）。
    // 用戶熄咗雨雲 —— 新舊兩批都要拆，唔可以淨係拆一批
    if (!wxOn.rain) { dropRainLayers(mine); dropStaleRain(); return; }

    // 3) 逐幀睇有冇真係載到圖。一幀都載唔到嘅唔可以留喺動畫入面，
    //    否則播到嗰幀就閃白。
    const good = mine.filter((_, i) => stats[i].loaded > 0);
    // 全部 layer 一格 tile 都冇試過載 = 視野完全喺日本範圍外，本來就冇嘢顯示，
    // 照切冇損失（唔照切嘅話用戶 pan 咗出去就會永遠卡住唔更新）。
    const nothingToLoad = stats.every(s => s.loaded === 0 && s.failed === 0);

    if (!good.length && !nothingToLoad) {
      // 成批都冇圖（timeout 未載到 / tile 全部失敗）→ **唔可以**拆舊嗰批，
      // 拆咗就係一片空白。繼續播舊嘅，清走 key 令下個 cycle 重試。
      dropRainLayers(mine);
      rainFrames = rainStale;
      rainStale = [];
      rainFramesKey = '';
      committed = true;      // rainFrames 已經指返舊嗰批，唔可以再喺 catch 度拆
      startRainLoop();
      return;
    }
    // 掉走冇圖嗰幾幀，淨返有圖嘅入動畫
    if (good.length && good.length < mine.length) {
      dropRainLayers(mine.filter((_, i) => stats[i].loaded === 0));
      rainFrames = good;
    }

    committed = true;
    dropStaleRain();
    startRainLoop();
  } catch (e) {
    // JMA 死咗就當冇雨雲，唔好阻住飛機圖；但中途爆咗唔可以留低半截圖層喺地圖上
    if (!committed) dropRainLayers(mine);
  }
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
let windAt = 0;            // 上次成功畫好嘅時間，用嚟判斷手上啲格夠唔夠新
let windMaxKt = null;      // 上次嘅視野最大值，開返掣即刻擺返個 label
const WIND_STALE_MS = 10 * 60 * 1000;   // 超過就當過時，開掣時重新攞
let windTimer = null;
// 同雨雲一樣序列化。之前用「busy 就掉頭走 + again 旗標補飛」，但每次熄掣都會將
// again 清返 false，於是連撳幾下之間嘅 in-flight request 一完，補飛就冇咗 ——
// 用戶見到嘅係「撳咗開但一格色都冇」。序列化保證任何一次開掣最終都會跑完一轉。
let windRunning = false;
let windQueued = false;

async function refreshWind() {
  if (windRunning) { windQueued = true; return; }
  windRunning = true;
  try {
    do {
      windQueued = false;
      await doRefreshWind();
    } while (windQueued && wxOn.wind);
  } finally {
    windRunning = false;
  }
}

// 當前視野嘅 bbox + key。doRefreshWind 同 applyWx 都要用，一定要同一份計法，
// 否則「開掣嗰陣覺得 cache 啱用」同「refresh 覺得要重攞」會唔一致。
function windView() {
  const b = map.getBounds();
  // worldCopyJump 開咗，pan 過日界線 lon 會爆出 ±180，一定要 clamp
  const west = Math.max(-180, b.getWest()), east = Math.min(180, b.getEast());
  const south = Math.max(-85, b.getSouth()), north = Math.min(85, b.getNorth());
  if (!(east > west && north > south)) return null;
  const key = [map.getZoom(), west, south, east, north].map(v => Number(v).toFixed(1)).join(',');
  return { key, west, east, south, north };
}

// 清走風場。色塊、標籤、同埋描述「而家畫緊咩」嗰組 metadata 一定要一齊清 ——
// 淨係 clearLayers() 而留低 windKey/windAt，就會出現「cache 話啱用但 layer 係空」：
// 視野一兜返去 windKey 嗰個，doRefreshWind 就會當 cache 啱用即刻早退，
// 圖層一路空白到過期為止。所有清場路徑都要行呢個 function。
function clearWindField() {
  windLayer.clearLayers();
  setWindMaxLabel(null);
  windMaxKt = null;
  windKey = '';
  windAt = 0;
}

// 手上啲格係咪仲用得：同一個視野 + 未過期。兩個條件缺一都唔可以拎去顯示 ——
// 視野唔同就係「錯地方嘅風」，過咗期就係「當一個鐘前嘅風係而家」，都係誤導。
function windCacheUsable() {
  const v = windView();
  return !!v && windKey !== '' && windKey === v.key
    && (Date.now() - windAt) < WIND_STALE_MS;
}

// 淨係畀上面個序列化 wrapper 叫
async function doRefreshWind() {
  if (!wxOn.wind) return;
  const v = windView();
  if (!v) return;
  const { key, west, east, south, north } = v;
  // 同一個視野而手上啲格未過時 → 唔使再打 Open-Meteo（實測一 request ~1.6 秒）
  if (windCacheUsable()) return;

  const dLat = (north - south) / WIND_ROWS, dLon = (east - west) / WIND_COLS;
  const cells = [];
  for (let r = 0; r < WIND_ROWS; r++) {
    for (let c = 0; c < WIND_COLS; c++) {
      cells.push({ s: south + r * dLat, w: west + c * dLon });
    }
  }
  const lats = cells.map(c => (c.s + dLat / 2).toFixed(3)).join(',');
  const lons = cells.map(c => (c.w + dLon / 2).toFixed(3)).join(',');

  try {
    // 一定要封頂：hang 住嘅話 windRunning 會永遠 true，之後點撳點 pan 都唔會再更新
    const data = await fetchJsonTimeout('https://api.open-meteo.com/v1/forecast'
      + `?latitude=${lats}&longitude=${lons}`
      + '&current=wind_speed_10m,wind_gusts_10m&wind_speed_unit=kn', WX_FETCH_TIMEOUT_MS);
    // await 期間用戶可能已經熄咗個圖層 —— 唔好再寫入已經由地圖移走嘅 layer，
    // 否則下次撳返著會見到一批冇人 clear 過嘅舊格仔。
    if (!wxOn.wind) return;
    const pts = Array.isArray(data) ? data : [data];
    windLayer.clearLayers();
    let maxKt = null;
    pts.forEach((p, i) => {
      const cell = cells[i];
      if (!cell || !p.current) return;
      const kt = Math.max(p.current.wind_gusts_10m ?? 0, p.current.wind_speed_10m ?? 0);
      if (maxKt === null || kt > maxKt) maxKt = kt;   // 連冇著色嘅格都要計，label 先反映到真實情況
      const t = windRatio(kt);
      if (t === null) return;
      const color = windColor(kt);
      L.rectangle([[cell.s, cell.w], [cell.s + dLat, cell.w + dLon]], {
        color, weight: 0, fillColor: color,
        fillOpacity: 0.08 + t * 0.22,   // 同色階一齊加深
        interactive: false,          // 唔好搶飛機 marker 嘅 click（同 heliCircle 一樣）
      }).addTo(windLayer);
    });
    setWindMaxLabel(maxKt);
    windMaxKt = maxKt;
    windKey = key;
    windAt = Date.now();
  } catch (e) {
    // Open-Meteo 死咗 / 超額 / timeout：清走舊格仔。舊 viewport 嗰批位置已經唔啱，
    // 留喺度會變成「錯地方有大風」，比乜都唔顯示更誤導。
    // 標籤同 metadata 都要一齊清：淨係清色塊會出現「冇色但寫住 28kt」，
    // 而嗰個數字仲可能係 pan 走咗之前嗰個視野嘅 —— 比冇數字更誤導。
    clearWindField();
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
  if (kind === 'rain') {
    if (on) {
      // 唔可以直接 addTo + startRainLoop：預設熄嘅時候 refreshRain 喺
      // `if (!wxOn.rain) return` 就早退咗，rainFrames 雖然起好但從未上過地圖、
      // 一格 tile 都未載過。即刻播就係播一批空白幀，兼且繞過晒逐幀載入檢查。
      // 一律行返 refreshRain 條受控路徑：佢會加圖層、等 tile、逐幀篩走冇圖嘅、
      // 先至開始播。清 key 係為咗迫佢真係重砌而唔係早退。
      rainFramesKey = '';
      refreshRain();
    }
    else {
      stopRainLoop();
      // 新舊兩批都要拆：換代載入期間熄掣嘅話，降級嗰批仲頂住顯示緊，
      // 淨係拆 rainFrames 就會出現「撳咗熄但雨雲仲喺度」。
      dropRainLayers(rainFrames);
      dropStaleRain();
      setRainTimeLabel('');
    }
  }
  if (kind === 'cloud' && cloudLayer) on ? cloudLayer.addTo(map) : map.removeLayer(cloudLayer);
  if (kind === 'wind') {
    // L.layerGroup 冇 attribution option，要自己掛落 attribution control
    if (on) {
      windLayer.addTo(map);
      map.attributionControl.addAttribution(WIND_ATTRIB);
      setWindLegend(true);
      // 一定要先驗 cache 先至放返上地圖。無條件 addTo 嘅話，熄咗之後 pan 走
      // （或者熄咗好耐）再開，就會先閃一閃錯視野／過期嘅風同埋舊嘅最大值，
      // 兩秒後先被新資料換走 —— 顯示過錯嘢比遲少少出更差。
      if (windCacheUsable()) {
        setWindMaxLabel(windMaxKt);   // 現成嘅格啱用，即刻連數字一齊出返
      } else {
        clearWindField();             // 用唔到就連 metadata 一齊失效，等 refresh 攞新嘅
      }
      refreshWind();                // cache 啱用就會即刻早退，唔打網絡
    } else {
      clearTimeout(windTimer);
      // 特登唔 clearLayers()：畫好嘅格留喺 layerGroup 度，撳返開就即刻見到，
      // 唔使又等成 1.6 秒 API。過時嘅話 refreshWind 會自己重攞。
      map.removeLayer(windLayer);
      map.attributionControl.removeAttribution(WIND_ATTRIB);
      setWindMaxLabel(null);
      setWindLegend(false);
      // 特登唔清 windKey / windAt：留住先至知「手上啲格係邊個視野、幾時攞嘅」，
      // 撳返開先可以即刻重用。清咗就一定要重打 API，慢返轉頭。
    }
  }
}

['cloud', 'rain', 'wind'].forEach((kind) => {
  const btn = document.getElementById(`wx-${kind}`);
  if (!btn) return;
  btn.addEventListener('click', () => { wxOn[kind] = !wxOn[kind]; saveWx(); applyWx(kind); });
  applyWx(kind);   // 還原上次狀態（layer 未 load 好時 refreshXxx 會自己補 addTo）
});

// Tab 收埋咗就唔好繼續播 —— 背景 tab 個 setTimeout 會被夾到最少 1 秒，
// 動畫既卡又白白扯住 tile；返到前景先重新開始。
document.addEventListener('visibilitychange', () => {
  if (document.hidden) stopRainLoop();
  else if (wxOn.rain) startRainLoop();
});

refreshRain();
refreshCloud();
setInterval(refreshRain, RAIN_REFRESH_MS);
setInterval(refreshCloud, CLOUD_REFRESH_MS);

// ===== 屋企 / 接收機位置 =====
// 座標只會喺已登入嘅 response 出現（web/views.py `_receiver_latlon`），
// 所以呢度唔使自己判斷登入狀態 —— 未登入根本冇 window.RX_HOME。
// 唔好用佢做初始視野：map.js 開頭特登用闊日本中心，一 setView 落屋企
// 就等於用另一種方式洩露位置畀截圖 / 錄影。
// 天線圖示：垂直桅杆 + 底座三腳 + 兩道向外發射弧。跟返 PLANE_SVG / HELI_SVG
// 嗰套（inline SVG + divIcon）；currentColor 令顏色可以喺 CSS 度控。
// 兩道弧特登只畫上半，睇落似向天發射而唔似 wifi。
const HOME_SVG = '<svg viewBox="0 0 24 24" width="100%" height="100%">'
  + '<g fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round">'
  + '<path class="w2" d="M5.2 9.6a9 9 0 0 1 13.6 0"/>'
  + '<path class="w1" d="M8.2 12.2a5.2 5.2 0 0 1 7.6 0"/>'
  + '</g>'
  + '<g fill="currentColor" stroke="#031a14" stroke-width="0.5">'
  + '<circle cx="12" cy="14.4" r="1.7"/>'
  + '<path d="M11.25 15.4h1.5L14.4 21.6h-1.7L12 18.2l-0.7 3.4H9.6z"/>'
  + '</g></svg>';

if (Array.isArray(window.RX_HOME) && window.RX_HOME.length === 2) {
  // iconAnchor 擺喺桅杆底（x 中、y 貼近底邊），令支天線係「企喺」個座標上面，
  // 唔係個座標喺圖示正中間 —— 咁樣位置讀落先準。
  const icon = L.divIcon({
    className: 'rx-home-icon',
    html: `<div class="rx-home-wrap">${HOME_SVG}</div>`,
    iconSize: [48, 48], iconAnchor: [24, 44],
  });
  L.marker(window.RX_HOME, { icon, interactive: true, zIndexOffset: -500 })
    .bindTooltip(T.map_home || 'HOME RX', { direction: 'top', offset: [0, -40], className: 'ac-tip' })
    .addTo(map);
}
