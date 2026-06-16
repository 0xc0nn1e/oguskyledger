// /stats page JS — 由舊 STATS_HTML inline <script type="module"> 抽出。
// base.html 已 inject window.T 同 window.LANG，呢度全部 render function 用住 window.T。
// Radar background 用 Three.js（unpkg CDN module）。

import * as THREE from 'https://unpkg.com/three@0.160.0/build/three.module.js';

// ===== render top-10 helpers =====

function renderTop(targetId, items) {
  const el = document.getElementById(targetId);
  if (!items || !items.length) { el.innerHTML = '<div class="loading">— —</div>'; return; }
  const colsHTML = `<div class="cols"><div class="r">${esc(T.stats_col_rank)}</div><div>NAME</div><div class="c">${esc(T.stats_col_aircraft)}</div></div>`;
  el.innerHTML = colsHTML + items.map((it, i) => `
    <div class="row">
      <div class="rank">${i+1}</div>
      <div class="name" title="${esc(it.name)}">${esc(it.name)}</div>
      <div class="cnt">${it.count}</div>
    </div>`).join('');
}

function renderTopIcao(targetId, items) {
  const el = document.getElementById(targetId);
  if (!items || !items.length) { el.innerHTML = '<div class="loading">— —</div>'; return; }
  const colsHTML = `<div class="cols">
    <div class="r">${esc(T.stats_col_rank)}</div>
    <div>ICAO</div>
    <div>${esc(T.discover_col_reg)}</div>
    <div class="type">${esc(T.discover_col_type)}</div>
    <div>${esc(T.discover_col_op)}</div>
    <div class="c">${esc(T.stats_col_aircraft)}</div>
  </div>`;
  el.innerHTML = colsHTML + items.map((it, i) => {
    const hex = it.icao.toUpperCase();
    return `<div class="row">
      <div class="rank">${i+1}</div>
      <div class="icao"><a href="/aircraft/${esc(it.icao)}/">${esc(hex)}</a></div>
      <div class="name">${esc(it.reg || '—')}</div>
      <div class="type" title="${esc(it.type)}">${esc(it.type || '—')}</div>
      <div class="op" title="${esc(it.operator)}">${esc(it.operator || '—')}</div>
      <div class="cnt">${it.count}</div>
    </div>`;
  }).join('');
}

// category code → 友善名（同 ADS-B emitter category 對應）
const CAT_LABEL = {
  A1:'Light', A2:'Small', A3:'Large', A4:'B757', A5:'Heavy', A6:'High-perf', A7:'Heli',
  B1:'Glider', B2:'Balloon', B3:'Parachute', B4:'Ultralight', B6:'UAV', B7:'Space',
  C1:'Vehicle', C2:'Vehicle', C3:'Obstacle', '(unknown)':'—',
};

function renderRoutes(targetId, items) {
  const el = document.getElementById(targetId);
  if (!items || !items.length) { el.innerHTML = '<div class="loading">— —</div>'; return; }
  const colsHTML = `<div class="cols"><div class="r">${esc(T.stats_col_rank)}</div><div>${esc(T.stats_col_route || 'ROUTE')}</div><div class="c">${esc(T.stats_col_aircraft)}</div></div>`;
  el.innerHTML = colsHTML + items.map((it, i) => `
    <div class="row">
      <div class="rank">${i+1}</div>
      <div class="name" title="${esc(it.from + ' › ' + it.to)}">${esc(it.from)} › ${esc(it.to)}</div>
      <div class="cnt">${it.count}</div>
    </div>`).join('');
}

function renderCategory(targetId, items) {
  const el = document.getElementById(targetId);
  if (!items || !items.length) { el.innerHTML = '<div class="loading">— —</div>'; return; }
  const colsHTML = `<div class="cols"><div class="r">${esc(T.stats_col_rank)}</div><div>NAME</div><div class="c">${esc(T.stats_col_aircraft)}</div></div>`;
  el.innerHTML = colsHTML + items.map((it, i) => {
    const lbl = (CAT_LABEL[it.name] || it.name) + (CAT_LABEL[it.name] ? ' · ' + it.name : '');
    return `<div class="row"><div class="rank">${i+1}</div><div class="name" title="${esc(it.name)}">${esc(lbl)}</div><div class="cnt">${it.count}</div></div>`;
  }).join('');
}

// ===== histograms =====

function renderHist(hist) {
  const el = document.getElementById('hist');
  if (!hist || !hist.length) { el.innerHTML = '<div class="loading">— —</div>'; return; }
  const max = Math.max(1, ...hist.map(h => h.count));
  el.innerHTML = hist.map(h => {
    const pct = (h.count / max * 100).toFixed(1);
    const md = h.day.slice(5);
    return `<div class="bar-wrap" title="${esc(md)} · ${h.count}">
      <div class="val">${h.count}</div>
      <div class="bar-area"><div class="bar" style="height:${pct}%"></div></div>
      <div class="day">${md}</div>
    </div>`;
  }).join('');
}

function renderHist24(hourly) {
  const el = document.getElementById('hist24');
  if (!hourly || !hourly.length) { el.innerHTML = '<div class="loading">— —</div>'; return; }
  const max = Math.max(1, ...hourly.map(h => h.count));
  el.innerHTML = hourly.map(h => {
    const pct = (h.count / max * 100).toFixed(1);
    const valTxt = h.count ? h.count : '';
    const now = h.current ? ' now' : '';
    return `<div class="bar-wrap${now}" title="${pad(h.hour)}:00 · ${h.count}">
      <div class="val">${valTxt}</div>
      <div class="bar-area"><div class="bar${now}" style="height:${pct}%"></div></div>
      <div class="day">${pad(h.hour)}</div>
    </div>`;
  }).join('');
}

function renderHeatmap(hm) {
  const el = document.getElementById('heatmap');
  const lg = document.getElementById('heatmap-legend');
  if (!hm || !hm.cells) { el.innerHTML = '<div class="loading">— —</div>'; return; }
  const wds = T.stats_heatmap_wd || ['MON','TUE','WED','THU','FRI','SAT','SUN'];
  const max = Math.max(1, hm.max || 0);
  let html = '<div class="hr-lbl"></div>';
  for (let h = 0; h < 24; h++) html += `<div class="hr-lbl">${h%3===0?pad(h):''}</div>`;
  for (let wd = 0; wd < 7; wd++) {
    html += `<div class="wd-lbl">${esc(wds[wd])}</div>`;
    for (let h = 0; h < 24; h++) {
      const v = hm.cells[wd][h] || 0;
      const alpha = v ? (0.12 + (v / max) * 0.78).toFixed(3) : 0;
      html += `<div class="cell" style="background:rgba(127,255,212,${alpha})" title="${esc(wds[wd])} ${pad(h)}:00 · ${v}"></div>`;
    }
  }
  el.innerHTML = html;
  const steps = [0, 0.25, 0.5, 0.75, 1].map(t => {
    const a = t ? (0.12 + t * 0.78).toFixed(3) : 0;
    return `<span style="background:rgba(127,255,212,${a})"></span>`;
  }).join('');
  lg.innerHTML = `${esc(T.stats_heatmap_low)}<span class="scale">${steps}</span>${esc(T.stats_heatmap_high)} · max ${hm.max}`;
}

// ===== discover sections =====

function renderCurve(curve) {
  const wrap = document.getElementById('curve-wrap');
  if (!curve || !curve.length) { wrap.innerHTML = '<div class="loading">— —</div>'; return; }
  const W = 720, H = 240, padL = 44, padR = 16, padT = 16, padB = 28;
  const maxT = curve[curve.length-1].total;
  const minD = curve[0].date, maxD = curve[curve.length-1].date;
  const toX = i => padL + (curve.length<=1?0:i*(W-padL-padR)/(curve.length-1));
  const toY = v => padT + (H-padT-padB)*(1 - v/Math.max(1,maxT));
  const pts = curve.map((p, i) => `${toX(i).toFixed(1)},${toY(p.total).toFixed(1)}`).join(' ');
  const area = `${padL},${(H-padB).toFixed(1)} ${pts} ${(W-padR).toFixed(1)},${(H-padB).toFixed(1)}`;
  let yticks = '';
  for (let i = 0; i <= 4; i++) {
    const v = Math.round(maxT * i/4);
    const y = toY(v);
    yticks += `<line class="axis" x1="${padL}" y1="${y}" x2="${W-padR}" y2="${y}"/>`;
    yticks += `<text class="tick" x="${padL-4}" y="${y+3}" text-anchor="end">${v}</text>`;
  }
  const xidx = curve.length <= 3 ? curve.map((_,i)=>i) : [0, Math.floor(curve.length/2), curve.length-1];
  const xlabels = xidx.map(i => {
    const p = curve[i];
    return `<text class="tick" x="${toX(i)}" y="${H-padB+14}" text-anchor="middle">${esc(p.date.slice(5))}</text>`;
  }).join('');
  const dots = curve.map((p, i) => `<circle cx="${toX(i).toFixed(1)}" cy="${toY(p.total).toFixed(1)}" r="6" fill="transparent"><title>${esc(p.date)} · ${p.total}</title></circle>`).join('');
  wrap.innerHTML = `<svg viewBox="0 0 ${W} ${H}" id="curve-svg" preserveAspectRatio="xMidYMid meet">
    ${yticks}<polygon class="area" points="${area}"/><polyline class="line" points="${pts}"/>${xlabels}${dots}
  </svg>
  <div style="font-size:10px;letter-spacing:0.5px;color:var(--x-muted);margin-top:6px">${maxT.toLocaleString()} ${esc(T.discover_curve_total_lbl)} · ${esc(minD)} → ${esc(maxD)}</div>`;
}

function renderAlt(dist) {
  const wrap = document.getElementById('alt-wrap');
  if (!dist || !dist.length) { wrap.innerHTML = '<div class="loading">— —</div>'; return; }
  const W = 720, H = 200, padL = 44, padR = 16, padT = 16, padB = 32;
  const maxC = Math.max(1, ...dist.map(d => d.count));
  const n = dist.length;
  const bw = (W - padL - padR) / n;
  let bars = '';
  for (let i = 0; i < n; i++) {
    const c = dist[i].count;
    const h = (H - padT - padB) * (c / maxC);
    const x = padL + i*bw + 2;
    const y = (H - padB) - h;
    const lbl = dist[i].hi ? `${dist[i].lo/1000}–${dist[i].hi/1000}k` : `${dist[i].lo/1000}k+`;
    bars += `<rect class="bar" x="${x.toFixed(1)}" y="${y.toFixed(1)}" width="${(bw-4).toFixed(1)}" height="${h.toFixed(1)}"><title>${esc(lbl)} · ${c}</title></rect>`;
    if (c > 0) bars += `<text class="bar-lbl" x="${(x + (bw-4)/2).toFixed(1)}" y="${(y-3).toFixed(1)}">${c}</text>`;
    bars += `<text class="tick" x="${(x + (bw-4)/2).toFixed(1)}" y="${H-padB+14}" text-anchor="middle">${lbl}</text>`;
  }
  let yticks = '';
  for (let i = 0; i <= 4; i++) {
    const v = Math.round(maxC * i/4);
    const y = padT + (H-padT-padB)*(1 - i/4);
    yticks += `<line class="axis" x1="${padL}" y1="${y}" x2="${W-padR}" y2="${y}"/>`;
    yticks += `<text class="tick" x="${padL-4}" y="${y+3}" text-anchor="end">${v}</text>`;
  }
  wrap.innerHTML = `<svg viewBox="0 0 ${W} ${H}" id="alt-svg" preserveAspectRatio="xMidYMid meet">${yticks}${bars}</svg>
    <div style="font-size:10px;letter-spacing:0.5px;color:var(--x-muted);margin-top:6px">${esc(T.discover_alt_unit)}</div>`;
}

function toJSTDate(iso){ if(!iso) return null; const d=new Date(iso); return isNaN(d)?null:new Date(d.getTime()+9*3600*1000); }
function ymdJST(iso){ const j=toJSTDate(iso); return j ? j.getUTCFullYear()+'-'+pad(j.getUTCMonth()+1)+'-'+pad(j.getUTCDate()) : '—'; }
function hmJST(iso){ const j=toJSTDate(iso); return j ? pad(j.getUTCHours())+':'+pad(j.getUTCMinutes()) : '—'; }

function renderRare(rare) {
  const wrap = document.getElementById('rare-wrap');
  if (!rare || !rare.length) { wrap.innerHTML = `<div class="loading">${esc(T.discover_no_rare)}</div>`; return; }
  wrap.innerHTML = `<table class="rtable"><thead><tr>
    <th>ICAO / ${esc(T.discover_col_reg)}</th>
    <th>${esc(T.discover_col_type)}</th>
    <th>${esc(T.discover_col_op)}</th>
    <th class="r">${esc(T.discover_col_passes)}</th>
    <th>${esc(T.discover_col_first_seen)}</th>
    <th>${esc(T.discover_col_last_seen)}</th>
  </tr></thead><tbody>${rare.map(r => {
    const label = r.reg || r.icao.toUpperCase();
    return `<tr>
      <td><a href="/aircraft/${esc(r.icao)}/" title="${esc(r.icao.toUpperCase())}">${esc(label)}</a></td>
      <td>${esc(r.type || '—')}</td>
      <td>${esc(r.operator || '—')}</td>
      <td class="r">${r.count}</td>
      <td>${ymdJST(r.first_seen)}</td>
      <td>${ymdJST(r.last_seen)} ${hmJST(r.last_seen)}</td>
    </tr>`;
  }).join('')}</tbody></table>`;
}

// ===== main load =====

async function load() {
  try {
    const r = await (await fetch('/api/stats')).json();
    document.getElementById('db-total').textContent = r.db_total;
    document.getElementById('db-types').textContent = r.db_types;
    if (r.peak_alt && r.peak_alt.alt != null) {
      document.getElementById('peak-alt').textContent = Math.round(r.peak_alt.alt).toLocaleString() + ' ft';
      const fl = r.peak_alt.flight ? r.peak_alt.flight.trim() : '';
      const sub = document.getElementById('peak-alt-sub');
      // click ✈ 入去嗰架機 detail 頁（detail keyed by icao）
      if (r.peak_alt.icao) {
        sub.innerHTML = `<a href="/aircraft/${esc(r.peak_alt.icao)}/">✈ ${esc(fl || r.peak_alt.icao.toUpperCase())}</a>`;
      } else {
        sub.textContent = fl ? '✈ ' + fl : '';
      }
    }
    if (r.busiest_hour && r.busiest_hour.hour != null) {
      const h = r.busiest_hour.hour;
      document.getElementById('busiest-hour').textContent = pad(h) + ':00–' + pad((h + 1) % 24) + ':00';
      document.getElementById('busiest-hour-sub').textContent = r.busiest_hour.count + ' ' + T.stats_col_aircraft;
    }
    renderHist(r.histogram);
    renderHist24(r.hourly);
    renderHeatmap(r.heatmap);
    renderTop('top-types', r.top_types);
    renderTop('top-ops', r.top_ops);
    renderTop('top-from', r.top_from);
    renderTop('top-to', r.top_to);
    renderTop('top-op-country', r.top_op_country);
    renderCategory('top-category', r.category_dist);
    renderRoutes('top-routes', r.route_top);
    renderTopIcao('top-icao-7d', r.top_icao_7d);
    renderTopIcao('top-icao-db', r.top_icao_db);
  } catch (e) {
    document.getElementById('hist').innerHTML = '<div class="loading">error: ' + esc(String(e)) + '</div>';
  }
  try {
    const d = await (await fetch('/api/discover')).json();
    renderCurve(d.discovery_curve);
    renderAlt(d.altitude_dist);
    renderRare(d.rare_finds);
  } catch (e) {
    document.getElementById('curve-wrap').innerHTML = '<div class="loading">error: ' + esc(String(e)) + '</div>';
  }
}
load();

// ===== Three.js radar background =====

const MINT=0x7fffd4, AMBER=0xf5d96f, RING=0x1f5a4a;
const canvas = document.getElementById('radar');
const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(45, innerWidth/innerHeight, 0.1, 200);
camera.position.set(0, 8, 14); camera.lookAt(0, 0, 0);
const renderer = new THREE.WebGLRenderer({ canvas, alpha:true, antialias:true });
renderer.setSize(innerWidth, innerHeight);
renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
for (const r of [2,4,6,8,10]) {
  scene.add(new THREE.Mesh(
    new THREE.RingGeometry(r-0.01, r+0.01, 96),
    new THREE.MeshBasicMaterial({ color:RING, transparent:true, opacity:0.5, side:THREE.DoubleSide })
  )).rotation.x = -Math.PI/2;
}
scene.add(new THREE.LineSegments(
  new THREE.BufferGeometry().setFromPoints([
    new THREE.Vector3(-10,0,0), new THREE.Vector3(10,0,0),
    new THREE.Vector3(0,0,-10), new THREE.Vector3(0,0,10),
  ]),
  new THREE.LineBasicMaterial({ color:RING, transparent:true, opacity:0.35 })
));
const sweepGroup = new THREE.Group();
sweepGroup.add(new THREE.Line(
  new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(0,0,0), new THREE.Vector3(10,0,0)]),
  new THREE.LineBasicMaterial({ color:MINT, transparent:true, opacity:0.7 })
));
const wedge = new THREE.Mesh(
  new THREE.CircleGeometry(10, 48, -Math.PI/4, Math.PI/4),
  new THREE.MeshBasicMaterial({ color:MINT, transparent:true, opacity:0.08, side:THREE.DoubleSide })
);
wedge.rotation.x = -Math.PI/2; sweepGroup.add(wedge); scene.add(sweepGroup);
addEventListener('resize', () => {
  camera.aspect = innerWidth/innerHeight; camera.updateProjectionMatrix();
  renderer.setSize(innerWidth, innerHeight);
});
function animate() {
  sweepGroup.rotation.y -= 0.012;
  renderer.render(scene, camera);
  requestAnimationFrame(animate);
}
animate();
