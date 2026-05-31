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
const TRAIL_MAX = 80;     // 航跡保留點數（~4 分鐘 @3s）

function matchSearch(p) {
  if (!searchTerm) return null;
  const hay = [p.flight, p.reg, p.hex, p.operator].filter(Boolean).join(' ').toLowerCase();
  return hay.indexOf(searchTerm) >= 0;
}
function applyFilter() {
  for (const hex in planes) {
    const el = planes[hex].marker && planes[hex].marker.getElement();
    if (!el) continue;
    const wrap = el.querySelector('.ac-wrap');
    if (!wrap) continue;
    const m = matchSearch(planes[hex]);
    wrap.classList.toggle('dim', m === false);
    wrap.classList.toggle('hit', m === true);
  }
}

function extrap(fix, dt) {
  const ms = (fix.gs || 0) * 0.514444;        // kt -> m/s
  const dist = ms * Math.min(dt, 30);         // cap 30s 防 poll 卡住飛走
  const rad = (fix.track || 0) * Math.PI/180;
  const dLat = (dist * Math.cos(rad)) / 111320;
  const dLon = (dist * Math.sin(rad)) / (111320 * Math.cos(fix.lat * Math.PI/180));
  return { lat: fix.lat + dLat, lon: fix.lon + dLon };
}

async function poll() {
  let data;
  try { data = await (await fetch('/api/live')).json(); }
  catch (e) { return; }
  const list = data.aircraft || [];
  const now = performance.now();
  const seen = new Set();
  const fitPts = [];
  for (const a of list) {
    if (a.lat == null || a.lon == null) continue;
    seen.add(a.hex);
    fitPts.push([a.lat, a.lon]);
    let p = planes[a.hex];
    const fix = { lat:a.lat, lon:a.lon, track:a.track, gs:a.gs, t:now };
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
  for (const hex in planes) {
    const p = planes[hex];
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
  if (followHex && planes[followHex]) {
    const d = planes[followHex].disp;
    map.setView([d.lat, d.lon], map.getZoom(), { animate: false });
  }
  requestAnimationFrame(animate);
}
requestAnimationFrame(animate);

// 搜尋：highlight 命中、其餘變淡
const searchBox = document.getElementById('search');
if (searchBox) searchBox.addEventListener('input', () => {
  searchTerm = searchBox.value.trim().toLowerCase();
  applyFilter();
});
// click 空白地圖 / 拖地圖 → 取消跟機
map.on('mousedown', () => { followHex = null; });
