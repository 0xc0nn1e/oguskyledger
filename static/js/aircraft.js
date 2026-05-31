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

let _passes = [], _icao = '';

async function loadProfile(idx) {
  const p = _passes[idx];
  if (!p) return;
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
  drawProfile(pts);
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
  wrap.innerHTML = `<svg id="profile-svg" viewBox="0 0 ${W} ${H}" preserveAspectRatio="xMidYMid meet">
    ${yticks}${altSegs}${gsSegs}${xlabels}
  </svg>`;
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
      <section class="panel"><div class="panel-hdr"><span class="diamond">◆</span>${esc(name)}</div>
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
  const sel = document.getElementById('pass-pick');
  if (sel) sel.addEventListener('change', () => loadProfile(parseInt(sel.value, 10)));
  document.querySelectorAll('.ptable tr.pickable').forEach(tr => {
    tr.addEventListener('click', () => loadProfile(parseInt(tr.dataset.idx, 10)));
  });
  if (_passes.length) loadProfile(0);
}
load();
