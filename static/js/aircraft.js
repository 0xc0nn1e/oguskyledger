// /aircraft/<icao>/ page JS — 由舊 AIRCRAFT_HTML inline <script> 抽出。
// 修改：ICAO 由 URL pathname parse（新 URL `/aircraft/<icao>/`，唔再 `/aircraft?icao=`）。
// base.html 已 inject window.T 同 window.LANG。

function statCard(lbl, val, sub) {
  return `<div class="stat-big"><div class="lbl">${esc(lbl)}</div><div class="val">${esc(val)}</div><div class="sub">${esc(sub||'')}</div></div>`;
}
function kvRow(k, v) {
  return v ? `<div class="row"><div class="k">${esc(k)}</div><div class="v">${v}</div></div>` : '';
}
function renderHist(daily) {
  if (!daily || !daily.length) return '<div class="loading">— —</div>';
  const max = Math.max(1, ...daily.map(d => d.count));
  return '<div class="hist">' + daily.map(d => {
    const pct = (d.count / max * 100).toFixed(1);
    return `<div class="bar-wrap"><div class="val">${d.count}</div><div class="bar-area"><div class="bar" style="height:${pct}%"></div></div><div class="day">${esc(d.day.slice(5))}</div></div>`;
  }).join('') + '</div>';
}

function categoryIcon(code) {
  if (!code) return '';
  const c = String(code).trim().toUpperCase();
  if (c === 'A7') return '🚁';
  if (c === 'B1') return '🪁';
  if (c === 'B2' || c === 'B6') return '🎈';
  if (c.startsWith('C')) return '🚗';
  return '';
}

function passLabel(p) {
  return `${p.pass_date} ${hm(p.first_seen)}–${hm(p.last_seen)}` + (p.flight ? ` · ${p.flight}` : '');
}

// 路線歷史：route_snapshots 去重後嘅時序（最近觀測先）
function renderRouteHistory(items) {
  if (!items || !items.length) return `<div class="loading">${esc(T.ac_routes_empty || '// no route history')}</div>`;
  return '<div class="route-hist">' + items.map(r => {
    const route = (r.from || r.to) ? `${esc(r.from || '—')} › ${esc(r.to || '—')}` : '—';
    return `<div class="rh-row">`
      + `<span class="rh-date">${ymd(r.last_seen)}</span>`
      + `<span class="rh-flight">${esc(r.flight || '—')}</span>`
      + `<span class="rh-route">${route}</span>`
      + (r.n > 1 ? `<span class="rh-n">×${r.n}</span>` : '')
      + `</div>`;
  }).join('') + '</div>';
}

let _passes = [], _icao = '', _loadSeq = 0;

async function loadProfile(idx) {
  const p = _passes[idx];
  if (!p) return;
  // 快手連揀兩條 pass 時，遲返嚟嘅舊 response 唔可以覆寫新揀嗰條
  const seq = ++_loadSeq;
  const wrap = document.getElementById('profile-wrap');
  wrap.innerHTML = `<div class="loading">${esc(T.loading)}</div>`;
  document.querySelectorAll('.ptable tr.pickable').forEach((tr, i) => {
    tr.classList.toggle('on', i === idx);
  });
  const sel = document.getElementById('pass-pick');
  if (sel) sel.value = String(idx);
  let pts = [];
  try {
    const r = await fetch(`/api/aircraft/track?icao=${encodeURIComponent(_icao)}&from=${encodeURIComponent(p.first_seen)}&to=${encodeURIComponent(p.last_seen)}`);
    const j = r.ok ? await r.json() : {};
    pts = j.points || [];
  } catch (e) { pts = []; }
  if (seq !== _loadSeq) return;   // 已經揀咗另一條 pass，呢個 response 過時
  drawProfile(pts);
  drawTrackMap(pts);
}

function drawProfile(pts) {
  const wrap = document.getElementById('profile-wrap');
  if (!pts || pts.length < 1) {
    wrap.innerHTML = `<div class="loading">${esc(T.ac_profile_no_data)}</div>`;
    return;
  }
  const W = 800, H = 240, padL = 44, padR = 44, padT = 14, padB = 28;
  const tMin = new Date(pts[0].ts).getTime();
  const tMax = new Date(pts[pts.length-1].ts).getTime();
  const tSpan = Math.max(1, tMax - tMin);
  const alts = pts.map(p => p.alt).filter(v => v != null);
  const gss = pts.map(p => p.gs).filter(v => v != null);
  const altMax = alts.length ? Math.max(...alts) : 1;
  const gsMax = gss.length ? Math.max(...gss) : 1;
  const niceUp = v => {
    const s = Math.pow(10, Math.floor(Math.log10(Math.max(1, v))));
    return Math.ceil(v/s)*s;
  };
  const altTop = niceUp(altMax || 1);
  const gsTop = niceUp(gsMax || 1);
  const toX = t => padL + (new Date(t).getTime() - tMin) * (W - padL - padR) / tSpan;
  const toYAlt = v => padT + (H - padT - padB) * (1 - v/altTop);
  const toYGs = v => padT + (H - padT - padB) * (1 - v/gsTop);
  let yticks = '';
  for (let i = 0; i <= 4; i++) {
    const y = padT + (H - padT - padB) * (1 - i/4);
    yticks += `<line class="axis" x1="${padL}" y1="${y}" x2="${W-padR}" y2="${y}"/>`;
    yticks += `<text class="tick" x="${padL-4}" y="${y+3}" text-anchor="end" style="fill:var(--mint)">${Math.round(altTop*i/4).toLocaleString()}</text>`;
    yticks += `<text class="tick" x="${W-padR+4}" y="${y+3}" text-anchor="start" style="fill:var(--amber)">${Math.round(gsTop*i/4)}</text>`;
  }
  const xidx = [0, Math.floor(pts.length/2), pts.length-1];
  const xlabels = xidx.map(i => `<text class="tick" x="${toX(pts[i].ts)}" y="${H-padB+14}" text-anchor="middle">${hm(pts[i].ts)}</text>`).join('');
  // 用 null 切 segments，連續嗰段先 polyline
  const segs = (yFn, key) => {
    const out = [];
    let cur = [];
    for (const p of pts) {
      if (p[key] == null) { if (cur.length) { out.push(cur); cur = []; } continue; }
      cur.push(`${toX(p.ts).toFixed(1)},${yFn(p[key]).toFixed(1)}`);
    }
    if (cur.length) out.push(cur);
    return out;
  };
  const altSegs = segs(toYAlt, 'alt').map(s => `<polyline class="alt-line" points="${s.join(' ')}"/>`).join('');
  const gsSegs = segs(toYGs, 'gs').map(s => `<polyline class="gs-line" points="${s.join(' ')}"/>`).join('');
  // 每點透明 hover 圈 + <title>：hover 睇該點時間 / 高度 / 速度
  const dots = pts.map(p => {
    const t = hm(p.ts); let s = '';
    if (p.alt != null) s += `<circle class="pt" cx="${toX(p.ts).toFixed(1)}" cy="${toYAlt(p.alt).toFixed(1)}" r="5" fill="transparent"><title>${esc(t)} · ${Math.round(p.alt).toLocaleString()} ft</title></circle>`;
    if (p.gs != null) s += `<circle class="pt" cx="${toX(p.ts).toFixed(1)}" cy="${toYGs(p.gs).toFixed(1)}" r="5" fill="transparent"><title>${esc(t)} · ${Math.round(p.gs)} kt</title></circle>`;
    return s;
  }).join('');
  wrap.innerHTML = `<svg id="profile-svg" viewBox="0 0 ${W} ${H}" preserveAspectRatio="xMidYMid meet">
    ${yticks}${altSegs}${gsSegs}${xlabels}${dots}
  </svg>`;
}

// ===== 路線地圖（Leaflet，揀 pass 時同 profile 一齊更新）=====
// 高度色階同 map.js 同一條公式：0–40,000ft 橙(35°) → 紫(265°)，無高度灰
function altColor(ft) {
  if (ft == null) return '#9aa6a3';
  const t = Math.max(0, Math.min(1, ft / 40000));
  return `hsl(${(35 + t * 230).toFixed(0)}, 85%, 58%)`;
}

// 飛機 icon 同 map.js 同一個 SVG path
const TRACK_PLANE_SVG = '<svg viewBox="0 0 24 24" width="100%" height="100%"><path fill="currentColor" stroke="#031a14" stroke-width="0.7" d="M12 1.6 C12.6 1.6 13 2.4 13 4 L13 10.4 L21.6 15.4 L21.6 17.2 L13 14.6 L13 19.4 L15.2 21 L15.2 22.4 L12 21.4 L8.8 22.4 L8.8 21 L11 19.4 L11 14.6 L2.4 17.2 L2.4 15.4 L11 10.4 L11 4 C11 2.4 11.4 1.6 12 1.6 Z"/></svg>';

// 兩點之間嘅方位角（度，0 = 正北），俾終點飛機 icon 轉向
function bearingDeg(a, b) {
  const toRad = d => d * Math.PI / 180;
  const dLon = toRad(b.lon - a.lon);
  const y = Math.sin(dLon) * Math.cos(toRad(b.lat));
  const x = Math.cos(toRad(a.lat)) * Math.sin(toRad(b.lat))
          - Math.sin(toRad(a.lat)) * Math.cos(toRad(b.lat)) * Math.cos(dLon);
  return (Math.atan2(y, x) * 180 / Math.PI + 360) % 360;
}

let _map = null, _trackLayer = null;

function drawTrackMap(pts) {
  const wrap = document.getElementById('track-map-wrap');
  if (!wrap) return;
  const geo = (pts || []).filter(p => p.lat != null && p.lon != null);
  if (!geo.length) {
    // 冇位置點：拆咗個 map（如有），顯示 no-data，唔留舊軌跡
    if (_map) { _map.remove(); _map = null; _trackLayer = null; }
    wrap.innerHTML = `<div class="loading">${esc(T.ac_map_no_data)}</div>`;
    return;
  }
  if (!_map) {
    wrap.innerHTML = '<div id="track-map"></div>';
    _map = L.map('track-map', { zoomControl: true, attributionControl: true, worldCopyJump: true });
    L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
      maxZoom: 18, subdomains: 'abcd',
      attribution: '© OpenStreetMap © CARTO'
    }).addTo(_map);
    _trackLayer = L.layerGroup().addTo(_map);
  }
  _trackLayer.clearLayers();
  // 相鄰兩點一段 polyline，色 = 兩點高度平均（pass 通常幾十點，per-segment 冇性能問題）
  for (let i = 1; i < geo.length; i++) {
    const a = geo[i - 1], b = geo[i];
    const alt = (a.alt != null && b.alt != null) ? (a.alt + b.alt) / 2 : (a.alt != null ? a.alt : b.alt);
    L.polyline([[a.lat, a.lon], [b.lat, b.lon]], {
      color: altColor(alt), weight: 2.5, opacity: 0.9,
    }).addTo(_trackLayer);
  }
  const s = geo[0], e = geo[geo.length - 1];
  // 起點 ▲ mint；終點（最後離開覆蓋嗰位）用飛機 icon，指向最後航向
  L.circleMarker([s.lat, s.lon], { radius: 5, color: '#7fffd4', fillColor: '#7fffd4', fillOpacity: 0.9, weight: 1 })
    .bindTooltip(`▲ ${hm(s.ts)}`).addTo(_trackLayer);
  // 向後搵最後一個唔同座標嘅點計航向——連續重複座標會令 bearing 錯誤變 0（指北）
  let brg = 0;
  for (let i = geo.length - 2; i >= 0; i--) {
    if (geo[i].lat !== e.lat || geo[i].lon !== e.lon) { brg = bearingDeg(geo[i], e); break; }
  }
  const planeIcon = L.divIcon({
    className: 'track-ac-icon',
    iconSize: [26, 26], iconAnchor: [13, 13],
    html: `<div class="track-ac" style="color:${altColor(e.alt)};transform:rotate(${brg.toFixed(0)}deg)">${TRACK_PLANE_SVG}</div>`,
  });
  L.marker([e.lat, e.lon], { icon: planeIcon }).bindTooltip(hm(e.ts)).addTo(_trackLayer);
  _map.invalidateSize();
  // 以接收機做中心、對稱 cover 晒全程軌跡；最少範圍要望到成個東京灣
  let bounds = L.latLngBounds(geo.map(p => [p.lat, p.lon]));
  if (window.RX_CENTER) {
    const rlat = window.RX_CENTER[0], rlon = window.RX_CENTER[1];
    let hLat = 0.45, hLon = 0.50;   // 最少半徑（度）：尾久一帶望落去見到東京灣
    for (const p of geo) {
      hLat = Math.max(hLat, Math.abs(p.lat - rlat));
      hLon = Math.max(hLon, Math.abs(p.lon - rlon));
    }
    bounds = L.latLngBounds([[rlat - hLat, rlon - hLon], [rlat + hLat, rlon + hLon]]);
  }
  _map.fitBounds(bounds, { padding: [20, 20] });
}

async function toggleWatch(a) {
  // 撳 ⭐ watch → POST /api/watch（login-gated；DRF SessionAuth 要 X-CSRFToken，
  // token 由 base.html 嘅 const CSRF 提供）。加 / 刪一條 match_type=icao 嘅 push rule。
  const wb = document.getElementById('watch-btn');
  if (!wb) return;
  const want = !wb.classList.contains('on');
  wb.disabled = true;
  try {
    const r = await fetch('/api/watch', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': (typeof CSRF !== 'undefined' ? CSRF : '') },
      body: JSON.stringify({ icao: a.icao, on: want, label: a.registration || a.icao }),
    });
    if (r.ok) {
      const on = !!(await r.json()).watched;
      wb.classList.toggle('on', on);
      wb.textContent = on ? '★ ' + (T.ac_watching || 'WATCHING') : '☆ ' + (T.ac_watch || 'WATCH');
    }
  } catch (e) { /* ignore，掣態唔變 */ }
  wb.disabled = false;
}

async function load() {
  // 新 URL 由 pathname parse ICAO：/aircraft/<icao>/
  const m = location.pathname.match(/^\/aircraft\/([^\/]+)\/?$/);
  const icao = m ? m[1] : '';
  const body = document.getElementById('body');
  if (!icao) { body.innerHTML = `<div class="loading">${esc(T.ac_notfound)}</div>`; return; }
  let a;
  try {
    const r = await fetch('/api/aircraft?icao=' + encodeURIComponent(icao));
    a = r.ok ? await r.json() : null;
  } catch (e) { a = null; }
  if (!a) { body.innerHTML = `<div class="loading">${esc(T.ac_notfound)}</div>`; return; }
  const catIcon = categoryIcon(a.category);
  const name = (catIcon ? catIcon + ' ' : '') + a.icao;
  const route = (a.from || a.to) ? `${esc(a.from || '—')} › ${esc(a.to || '—')}` : null;
  const fr24 = a.registration
    ? `https://www.flightradar24.com/data/aircraft/${a.registration.toLowerCase()}`
    : `https://www.flightradar24.com/data/aircraft/${icao.toLowerCase()}`;
  const peak = (a.peak_alt != null) ? Math.round(a.peak_alt).toLocaleString() + ' ft' : '—';
  const spd = (a.max_gs != null) ? Math.round(a.max_gs) + ' kt' : '—';
  body.innerHTML = `
    <div class="ac-head">
      <section class="panel"><div class="panel-hdr"><span class="diamond">◆</span>${esc(name)}${a.watched !== undefined ? `<button id="watch-btn" type="button" class="watch-btn${a.watched ? ' on' : ''}">${a.watched ? '★ ' + esc(T.ac_watching || 'WATCHING') : '☆ ' + esc(T.ac_watch || 'WATCH')}</button>` : ''}</div>
        <div class="panel-body"><div class="kv">
          ${kvRow(T.map_reg, esc(a.registration))}
          ${kvRow(T.map_type, esc(a.aircraft_type))}
          ${kvRow(T.map_op, esc(a.operator))}
          ${kvRow(T.map_country, esc(a.country))}
          ${kvRow(T.map_route, route)}
          ${kvRow('ICAO', esc(a.icao))}
          <div class="row"><div class="k">FR24</div><div class="v"><a href="${fr24}" target="_blank" rel="noopener">${esc(T.map_fr24)} ↗</a></div></div>
        </div></div>
      </section>
      <div><div class="stats-grid">
        ${statCard(T.ac_total_passes, (a.total_passes||0).toLocaleString(), '')}
        ${statCard(T.ac_days, a.days||0, '')}
        ${statCard(T.ac_peak_alt, peak, '')}
        ${statCard(T.ac_max_spd, spd, '')}
        ${statCard(T.ac_first_seen, ymd(a.first_seen), hm(a.first_seen))}
        ${statCard(T.ac_last_seen, ymd(a.last_seen), hm(a.last_seen))}
      </div></div>
    </div>
    <section class="panel"><div class="panel-hdr"><span class="diamond">◆</span>${esc(T.ac_routes_hdr || 'ROUTE HISTORY')}</div>
      <div class="panel-body">${renderRouteHistory(a.route_history)}</div></section>
    <section class="panel"><div class="panel-hdr"><span class="diamond">◆</span>${esc(T.ac_daily_hdr)}</div>
      <div class="panel-body">${renderHist(a.daily)}</div></section>
    <section class="panel"><div class="panel-hdr"><span class="diamond">◆</span>${esc(T.ac_profile_hdr)}</div>
      <div class="panel-body">
        <div class="profile-bar">
          <label for="pass-pick">${esc(T.ac_profile_pick)}</label>
          <select id="pass-pick">${(a.passes||[]).map((p, i) => `<option value="${i}">${esc(passLabel(p))}</option>`).join('')}</select>
          <span class="legend">
            <span><i style="background:var(--mint)"></i>${esc(T.ac_profile_alt_lbl)}</span>
            <span><i style="background:var(--amber)"></i>${esc(T.ac_profile_gs_lbl)}</span>
          </span>
        </div>
        <div id="profile-wrap"><div class="loading">${esc(T.loading)}</div></div>
      </div></section>
    <section class="panel"><div class="panel-hdr"><span class="diamond">◆</span>${esc(T.ac_map_hdr)}</div>
      <div class="panel-body">
        <div id="track-map-wrap"><div class="loading">${esc(T.loading)}</div></div>
      </div></section>
    <section class="panel"><div class="panel-hdr"><span class="diamond">◆</span>${esc(T.ac_passes_hdr)}</div>
      <div class="panel-body" style="overflow-x:auto">
        <table class="ptable"><thead><tr>
          <th>${esc(T.ac_col_date)}</th><th>${esc(T.ac_col_time)}</th><th>${esc(T.ac_col_flight)}</th>
          <th>${esc(T.ac_col_from)}</th><th>${esc(T.ac_col_to)}</th>
          <th class="r">${esc(T.ac_col_alt)}</th><th class="r">${esc(T.ac_col_samples)}</th>
        </tr></thead><tbody>
        ${(a.passes||[]).map((p, i) => {
          const al = (p.min_alt!=null||p.max_alt!=null)
            ? `${p.min_alt!=null?Math.round(p.min_alt).toLocaleString():'—'}–${p.max_alt!=null?Math.round(p.max_alt).toLocaleString():'—'}`
            : '—';
          return `<tr class="pickable" data-idx="${i}"><td>${esc(p.pass_date)}</td><td>${hm(p.first_seen)}–${hm(p.last_seen)}</td><td>${esc(p.flight||'—')}</td><td>${esc(p.from_airport||'—')}</td><td>${esc(p.to_airport||'—')}</td><td class="r">${al}</td><td class="r">${p.samples}</td></tr>`;
        }).join('')}
        </tbody></table>
      </div></section>`;
  _passes = a.passes || [];
  _icao = a.icao;
  const wb = document.getElementById('watch-btn');
  if (wb) wb.addEventListener('click', () => toggleWatch(a));
  const sel = document.getElementById('pass-pick');
  if (sel) sel.addEventListener('change', () => loadProfile(parseInt(sel.value, 10)));
  document.querySelectorAll('.ptable tr.pickable').forEach(tr => {
    tr.addEventListener('click', () => loadProfile(parseInt(tr.dataset.idx, 10)));
  });
  // 通過履歴表頭 click 排序（data-idx 跟住 row 走，揀 pass 照舊啱）
  makeSortable(document.querySelector('.ptable'));
  if (_passes.length) loadProfile(0);
  else {
    // 零 pass：兩個 panel 都要明示無數據，唔好困喺 loading
    document.getElementById('profile-wrap').innerHTML = `<div class="loading">${esc(T.ac_profile_no_data)}</div>`;
    document.getElementById('track-map-wrap').innerHTML = `<div class="loading">${esc(T.ac_map_no_data)}</div>`;
  }
}
load();
