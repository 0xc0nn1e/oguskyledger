// /coverage page JS — 由舊 COVERAGE_HTML inline <script> 抽出。
// 純 SVG polar radar，由 base.html inline 注入 window.T。

function compass(deg) {
  return ['N','NE','E','SE','S','SW','W','NW'][Math.round(deg/45)%8];
}

function niceMax(km) {
  if (km <= 0) return 100;
  const step = km > 400 ? 200 : 100;
  return Math.ceil(km/step)*step;
}

function renderRadar(cov) {
  const wrap = document.getElementById('radar-wrap');
  const sectors = cov.sectors || [];
  const maxScale = niceMax(cov.max_km || 0);
  const S = 480, cx = S/2, cy = S/2, R = S/2 - 34;
  const pt = (deg, km) => {
    const r = (km/maxScale)*R, a = deg*Math.PI/180;
    return [cx + r*Math.sin(a), cy - r*Math.cos(a)];
  };
  let svg = `<svg id="radar-svg" viewBox="0 0 ${S} ${S}">`;
  // range rings + labels
  for (let i = 1; i <= 4; i++) {
    const rr = R*i/4;
    svg += `<circle class="ring" cx="${cx}" cy="${cy}" r="${rr.toFixed(1)}"/>`;
    svg += `<text class="rlabel" x="${cx+3}" y="${(cy-rr+11).toFixed(1)}">${Math.round(maxScale*i/4)} km</text>`;
  }
  // N-S / E-W axes
  svg += `<line class="axis" x1="${cx}" y1="${cy-R}" x2="${cx}" y2="${cy+R}"/>`;
  svg += `<line class="axis" x1="${cx-R}" y1="${cy}" x2="${cx+R}" y2="${cy}"/>`;
  // coverage polygon
  const pts = sectors.map(s => pt(s.deg, s.km).map(n => n.toFixed(1)).join(',')).join(' ');
  if (pts) svg += `<polygon class="cov" points="${pts}"/>`;
  // compass labels
  const dirs = [['N',0],['E',90],['S',180],['W',270]];
  for (const [lab, deg] of dirs) {
    const [x,y] = pt(deg, maxScale*1.06);
    svg += `<text class="dir" x="${x.toFixed(1)}" y="${(y+4).toFixed(1)}" text-anchor="middle">${lab}</text>`;
  }
  svg += '</svg>';
  wrap.innerHTML = svg;
}

async function load() {
  let cov;
  try {
    cov = await (await fetch('/api/coverage')).json();
  } catch (e) {
    cov = {error: 'fetch'};
  }
  if (cov.error === 'no_receiver_coords') {
    document.getElementById('radar-wrap').innerHTML =
      `<div class="loading">${esc(T.cov_nocoords)}</div>`;
    return;
  }
  document.getElementById('cov-hdr').textContent =
    (T.cov_hdr || '').replace('{n}', cov.window_days || 30);
  document.getElementById('c-max').textContent =
    (cov.max_km != null) ? cov.max_km + ' km' : '—';
  document.getElementById('c-max-nm').textContent =
    (cov.max_nm != null) ? cov.max_nm + ' nm' : '';
  document.getElementById('c-ac').textContent =
    (cov.aircraft_with_pos != null) ? cov.aircraft_with_pos.toLocaleString() : '—';
  const f = cov.farthest;
  if (f) {
    document.getElementById('c-far').textContent = f.registration || f.icao || '—';
    document.getElementById('c-far-sub').textContent = [
      f.km != null ? f.km + ' km' : null,
      f.bearing != null ? compass(f.bearing) + ' ' + f.bearing + '°' : null,
      f.operator,
    ].filter(Boolean).join(' · ');
  }
  renderRadar(cov);
}
load();
