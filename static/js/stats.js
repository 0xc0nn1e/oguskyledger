// /stats page JS — 由舊 STATS_HTML inline <script type="module"> 抽出。
// base.html 已 inject window.T 同 window.LANG，呢度全部 render function 用住 window.T。
// Radar background 用 Three.js（self-host，base.html importmap 把 `three` 指去 vendor）。

import * as THREE from 'three';

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

// ===== 新增：紀錄榜 / 全年日曆 / 速度分佈 / 最快榜 / 航向羅盤 =====

function _tile(lbl, valHTML, subHTML) {
  return `<div class="stat-big">
    <div class="lbl">${esc(lbl || '')}</div>
    <div class="val">${valHTML}</div>
    <div class="sub">${subHTML || ''}</div>
  </div>`;
}

function _fmtDur(secs) {
  secs = Math.max(0, Math.round(secs));
  const h = Math.floor(secs / 3600), m = Math.floor((secs % 3600) / 60);
  return h ? `${h}h ${pad(m)}m` : `${m}m`;
}

// 紀錄榜：最快 / 停留最耐 / 最繁忙一日 / 最常見機（最常見重用 top_icao_db[0]）
function renderRecords(r) {
  const el = document.getElementById('records');
  if (!el) return;
  const rec = r.records || {};
  const acLbl = T.stats_col_aircraft || '';
  const tiles = [];
  if (rec.fastest && rec.fastest.gs != null) {
    const f = rec.fastest, fl = (f.flight || '').trim();
    const sub = f.icao
      ? `<a href="/aircraft/${esc(f.icao)}/">✈ ${esc(fl || f.icao.toUpperCase())}</a>`
      : (fl ? '✈ ' + esc(fl) : '');
    tiles.push(_tile(T.stats_rec_fastest, Math.round(f.gs).toLocaleString() + ' kt', sub));
  }
  if (rec.longest_pass && rec.longest_pass.secs != null) {
    const lp = rec.longest_pass, fl = (lp.flight || '').trim();
    const sub = lp.icao
      ? `<a href="/aircraft/${esc(lp.icao)}/">✈ ${esc(fl || lp.icao.toUpperCase())}</a> · ${esc(lp.date || '')}`
      : esc(lp.date || '');
    tiles.push(_tile(T.stats_rec_longest, _fmtDur(lp.secs), sub));
  }
  if (rec.busiest_day && rec.busiest_day.date) {
    const bd = rec.busiest_day;
    tiles.push(_tile(T.stats_rec_busiest_day, esc(bd.date), `${bd.count} ${esc(acLbl)}`));
  }
  const ms = (r.top_icao_db && r.top_icao_db[0]) || null;
  if (ms) {
    const label = ms.reg || ms.icao.toUpperCase();
    const sub = `<a href="/aircraft/${esc(ms.icao)}/">✈ ${esc(label)}</a> · ${ms.count} ${esc(acLbl)}`;
    tiles.push(_tile(T.stats_rec_most_seen, esc((ms.type || '').trim() || label), sub));
  }
  el.innerHTML = tiles.join('') || '<div class="loading">— —</div>';
}

// 全年日曆 heatmap（GitHub 式）：列＝週、行＝星期（一起頭），色階同 heatmap 一致
function renderCalendar(cal) {
  const el = document.getElementById('calendar');
  if (!el) return;
  if (!cal || !cal.length) { el.innerHTML = '<div class="loading">— —</div>'; return; }
  const counts = {}; let max = 1;
  for (const c of cal) { counts[c.date] = c.count; if (c.count > max) max = c.count; }
  const tj = new Date(Date.now() + 9 * 3600 * 1000);  // 今日 JST
  const end = Date.UTC(tj.getUTCFullYear(), tj.getUTCMonth(), tj.getUTCDate());
  const [fy, fm, fd] = cal[0].date.split('-').map(Number);
  const s = new Date(Date.UTC(fy, fm - 1, fd));
  const dow = (s.getUTCDay() + 6) % 7;                // Mon-first 偏移
  let cur = s.getTime() - dow * 86400000;             // 退到嗰個星期一
  const wds = T.stats_heatmap_wd || ['MON', 'TUE', 'WED', 'THU', 'FRI', 'SAT', 'SUN'];
  const mons = T.stats_calendar_months || ['1', '2', '3', '4', '5', '6', '7', '8', '9', '10', '11', '12'];
  const cells = [], monLabels = []; let lastMon = -1, dayIdx = 0;
  for (; cur <= end; cur += 86400000) {
    const d = new Date(cur);
    const key = `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())}`;
    const v = counts[key] || 0;
    const alpha = v ? (0.12 + (v / max) * 0.78).toFixed(3) : 0;
    cells.push(`<div class="cal-cell" style="background:rgba(127,255,212,${alpha})" title="${key} · ${v}"></div>`);
    if (dayIdx % 7 === 0) {                            // 每星期一出一格月份 label
      const mo = d.getUTCMonth();
      monLabels.push(`<div class="cal-month">${mo !== lastMon ? esc(mons[mo]) : ''}</div>`);
      lastMon = mo;
    }
    dayIdx++;
  }
  const wdStrip = wds.map((w, i) => `<span>${i % 2 === 0 ? esc(w) : ''}</span>`).join('');
  el.innerHTML =
    `<div class="cal-months">${monLabels.join('')}</div>` +
    `<div class="cal-body"><div class="cal-wd">${wdStrip}</div>` +
    `<div class="cal-grid">${cells.join('')}</div></div>` +
    `<div class="cal-cap">${esc(cal[0].date)} → ${esc(cal[cal.length - 1].date)} · max ${max}</div>`;
}

// 速度分佈（鏡 renderAlt，但 label 用 kt，唔除 1000）
function renderSpeed(dist) {
  const wrap = document.getElementById('speed-wrap');
  if (!wrap) return;
  if (!dist || !dist.length) { wrap.innerHTML = '<div class="loading">— —</div>'; return; }
  const W = 720, H = 200, padL = 44, padR = 16, padT = 16, padB = 32;
  const maxC = Math.max(1, ...dist.map(d => d.count));
  const n = dist.length, bw = (W - padL - padR) / n;
  let bars = '';
  for (let i = 0; i < n; i++) {
    const c = dist[i].count;
    const h = (H - padT - padB) * (c / maxC);
    const x = padL + i * bw + 2, y = (H - padB) - h;
    const lbl = dist[i].hi != null ? `${dist[i].lo}–${dist[i].hi}` : `${dist[i].lo}+`;
    bars += `<rect class="bar" x="${x.toFixed(1)}" y="${y.toFixed(1)}" width="${(bw - 4).toFixed(1)}" height="${h.toFixed(1)}"><title>${esc(lbl)} · ${c}</title></rect>`;
    if (c > 0) bars += `<text class="bar-lbl" x="${(x + (bw - 4) / 2).toFixed(1)}" y="${(y - 3).toFixed(1)}">${c}</text>`;
    bars += `<text class="tick" x="${(x + (bw - 4) / 2).toFixed(1)}" y="${H - padB + 14}" text-anchor="middle">${lbl}</text>`;
  }
  let yticks = '';
  for (let i = 0; i <= 4; i++) {
    const v = Math.round(maxC * i / 4);
    const y = padT + (H - padT - padB) * (1 - i / 4);
    yticks += `<line class="axis" x1="${padL}" y1="${y}" x2="${W - padR}" y2="${y}"/>`;
    yticks += `<text class="tick" x="${padL - 4}" y="${y + 3}" text-anchor="end">${v}</text>`;
  }
  wrap.innerHTML = `<svg viewBox="0 0 ${W} ${H}" id="speed-svg" preserveAspectRatio="xMidYMid meet">${yticks}${bars}</svg>
    <div style="font-size:10px;letter-spacing:0.5px;color:var(--x-muted);margin-top:6px">${esc(T.stats_speed_unit || 'kt')}</div>`;
}

// 最快 TOP 10（鏡 renderTopIcao，尾 column 顯示 gs 唔係 count）
function renderTopFastest(targetId, items) {
  const el = document.getElementById(targetId);
  if (!el) return;
  if (!items || !items.length) { el.innerHTML = '<div class="loading">— —</div>'; return; }
  const colsHTML = `<div class="cols">
    <div class="r">${esc(T.stats_col_rank)}</div>
    <div>ICAO</div>
    <div>${esc(T.discover_col_reg)}</div>
    <div class="type">${esc(T.discover_col_type)}</div>
    <div>${esc(T.discover_col_op)}</div>
    <div class="c">${esc(T.stats_speed_unit || 'kt')}</div>
  </div>`;
  el.innerHTML = colsHTML + items.map((it, i) => {
    const hex = it.icao.toUpperCase();
    return `<div class="row">
      <div class="rank">${i + 1}</div>
      <div class="icao"><a href="/aircraft/${esc(it.icao)}/">${esc(hex)}</a></div>
      <div class="name">${esc(it.reg || '—')}</div>
      <div class="type" title="${esc(it.type)}">${esc(it.type || '—')}</div>
      <div class="op" title="${esc(it.operator)}">${esc(it.operator || '—')}</div>
      <div class="cnt">${it.gs != null ? Math.round(it.gs) : '—'}</div>
    </div>`;
  }).join('');
}

// 航向羅盤（compass rose）：16 楔形由圓心射出，長度 = count / max
function renderCompass(cm) {
  const wrap = document.getElementById('compass-wrap');
  if (!wrap) return;
  if (!cm || !cm.buckets || !cm.buckets.length) { wrap.innerHTML = '<div class="loading">— —</div>'; return; }
  const buckets = cm.buckets, max = Math.max(1, cm.max || 0);
  const S = 260, cx = S / 2, cy = S / 2, R = S / 2 - 26;
  // heading h（0=北、順時針）→ 螢幕座標：x = cx + r·sin(h)，y = cy − r·cos(h)
  const px = (r, deg) => cx + r * Math.sin(deg * Math.PI / 180);
  const py = (r, deg) => cy - r * Math.cos(deg * Math.PI / 180);
  let rings = '';
  for (const f of [0.25, 0.5, 0.75, 1]) rings += `<circle class="ring" cx="${cx}" cy="${cy}" r="${(R * f).toFixed(1)}"/>`;
  let wedges = '';
  for (let i = 0; i < 16; i++) {
    const v = buckets[i] || 0;
    if (v <= 0) continue;
    const len = R * (v / max);
    const a0 = i * 22.5 - 11.25, a1 = i * 22.5 + 11.25;
    wedges += `<path class="wedge" d="M${cx},${cy} L${px(len, a0).toFixed(1)},${py(len, a0).toFixed(1)} A${len.toFixed(1)},${len.toFixed(1)} 0 0 1 ${px(len, a1).toFixed(1)},${py(len, a1).toFixed(1)} Z"><title>${v}</title></path>`;
  }
  const dirs = T.stats_compass_dir || ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW'];
  let labels = '';
  for (let k = 0; k < 8; k++) {
    const deg = k * 45;
    labels += `<text class="dir" x="${px(R + 12, deg).toFixed(1)}" y="${(py(R + 12, deg) + 3).toFixed(1)}" text-anchor="middle">${esc(dirs[k])}</text>`;
  }
  wrap.innerHTML = `<svg viewBox="0 0 ${S} ${S}" id="compass-svg" preserveAspectRatio="xMidYMid meet">${rings}${wedges}${labels}</svg>`;
}

// 接收範圍覆蓋圖：同 renderCompass 共用一套極座標數學，但楔形長度 =
// 該方位收得幾遠（km）而唔係 sample 數，而且 ring 要標實際距離。
function renderCoverage(cv) {
  const wrap = document.getElementById('coverage-wrap');
  if (!wrap) return;
  // cv 可以係 null（config 冇 receiver.lat/lon）→ 同冇資料一樣處理
  if (!cv || !cv.buckets || !cv.max) { wrap.innerHTML = '<div class="loading">— —</div>'; return; }
  const buckets = cv.buckets, max = cv.max;
  const S = 260, cx = S / 2, cy = S / 2, R = S / 2 - 26;
  const px = (r, deg) => cx + r * Math.sin(deg * Math.PI / 180);
  const py = (r, deg) => cy - r * Math.cos(deg * Math.PI / 180);
  let rings = '', ringLbls = '';
  for (const f of [0.25, 0.5, 0.75, 1]) {
    rings += `<circle class="ring" cx="${cx}" cy="${cy}" r="${(R * f).toFixed(1)}"/>`;
    // 沿 NE 標 km，避開正北個方位字
    ringLbls += `<text class="tick" x="${px(R * f, 45).toFixed(1)}" y="${(py(R * f, 45) - 2).toFixed(1)}" text-anchor="middle">${Math.round(max * f)}</text>`;
  }
  let wedges = '';
  for (let i = 0; i < 16; i++) {
    const km = buckets[i] || 0;
    if (km <= 0) continue;
    const len = R * (km / max);
    const a0 = i * 22.5 - 11.25, a1 = i * 22.5 + 11.25;
    const n = (cv.samples && cv.samples[i]) || 0;
    wedges += `<path class="wedge" d="M${cx},${cy} L${px(len, a0).toFixed(1)},${py(len, a0).toFixed(1)} A${len.toFixed(1)},${len.toFixed(1)} 0 0 1 ${px(len, a1).toFixed(1)},${py(len, a1).toFixed(1)} Z"><title>${km.toFixed(1)} km · ${n}</title></path>`;
  }
  const dirs = T.stats_compass_dir || ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW'];
  let labels = '';
  for (let k = 0; k < 8; k++) {
    const deg = k * 45;
    labels += `<text class="dir" x="${px(R + 12, deg).toFixed(1)}" y="${(py(R + 12, deg) + 3).toFixed(1)}" text-anchor="middle">${esc(dirs[k])}</text>`;
  }
  // 窗口由 sightings_raw 嘅 retention 決定（30 日），唔係歷來紀錄——一定要講明，
  // 否則會被誤讀成「我部機史上最遠收過咁遠」。
  const d = toJSTDate(cv.since);
  const sinceStr = d ? `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}-${pad(d.getUTCDate())}` : '';
  wrap.innerHTML = `<svg viewBox="0 0 ${S} ${S}" id="coverage-svg" preserveAspectRatio="xMidYMid meet">${rings}${ringLbls}${wedges}${labels}</svg>`
    + `<div style="font-size:10px;letter-spacing:0.5px;color:var(--x-muted);margin-top:6px">${esc(T.stats_coverage_note || '')}${sinceStr ? ' · ' + esc(sinceStr) + ' →' : ''}</div>`;
}

// ===== main load =====

function renderCacheUpdated(response) {
  const el = document.getElementById('stats-last-updated');
  const iso = response.headers.get('X-Stats-Cache-Generated-At');
  const parsed = iso ? new Date(iso) : null;
  if (!el || !parsed || Number.isNaN(parsed.getTime())) return;
  const jst = new Date(parsed.getTime() + 9 * 3600 * 1000);
  const stamp = `${jst.getUTCFullYear()}-${pad(jst.getUTCMonth() + 1)}-${pad(jst.getUTCDate())}`
    + ` ${pad(jst.getUTCHours())}:${pad(jst.getUTCMinutes())}:${pad(jst.getUTCSeconds())} JST`;
  el.textContent = `${T.stats_last_updated || '統計最後更新'} · ${stamp}`;
  el.hidden = false;
}

async function load() {
  try {
    const response = await fetch('/api/stats');
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const r = await response.json();
    renderCacheUpdated(response);
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
    renderRecords(r);
    renderCompass(r.compass);
    renderCoverage(r.coverage);
  } catch (e) {
    document.getElementById('hist').innerHTML = '<div class="loading">error: ' + esc(String(e)) + '</div>';
  }
  try {
    const d = await (await fetch('/api/discover')).json();
    renderCurve(d.discovery_curve);
    renderAlt(d.altitude_dist);
    renderRare(d.rare_finds);
    renderCalendar(d.calendar);
    renderSpeed(d.speed_dist);
    renderTopFastest('top-fastest', d.fastest_icao);
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
