// / home page JS — 由舊 HOME_HTML inline <script type="module"> 抽出。
// Three.js radar + clock + datepicker + search + group collapse + load + render with cascading reveal。
// base.html 已 inject window.T 同 window.LANG。

import * as THREE from 'https://unpkg.com/three@0.160.0/build/three.module.js';

// ===== Three.js radar 背景 =====
const MINT = 0x7fffd4, AMBER = 0xf5d96f, RING = 0x1f5a4a;
const canvas = document.getElementById('radar');
const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(45, innerWidth/innerHeight, 0.1, 200);
camera.position.set(0, 8, 14); camera.lookAt(0, 0, 0);
const renderer = new THREE.WebGLRenderer({ canvas, alpha:true, antialias:true });
renderer.setSize(innerWidth, innerHeight);
renderer.setPixelRatio(Math.min(devicePixelRatio, 2));

for (const r of [2,4,6,8,10]) {
  const ring = new THREE.Mesh(
    new THREE.RingGeometry(r-0.01, r+0.01, 96),
    new THREE.MeshBasicMaterial({ color:RING, transparent:true, opacity:0.5, side:THREE.DoubleSide })
  );
  ring.rotation.x = -Math.PI/2;
  scene.add(ring);
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
wedge.rotation.x = -Math.PI/2;
sweepGroup.add(wedge);
scene.add(sweepGroup);

const blips = [];
for (let i = 0; i < 14; i++) {
  const angle = Math.random()*Math.PI*2, dist = 2+Math.random()*8, y = 0.3+Math.random()*2.0;
  const mat = new THREE.MeshBasicMaterial({ color:AMBER, transparent:true, opacity:0.4 });
  const blip = new THREE.Mesh(new THREE.SphereGeometry(0.12, 12, 12), mat);
  blip.position.set(Math.cos(angle)*dist, y, Math.sin(angle)*dist);
  const trail = new THREE.Line(
    new THREE.BufferGeometry().setFromPoints([blip.position.clone(), blip.position.clone()]),
    new THREE.LineBasicMaterial({ color:AMBER, transparent:true, opacity:0.25 })
  );
  scene.add(blip); scene.add(trail);
  blips.push({ mesh:blip, trail, angle, dist, y, drift:(Math.random()-0.5)*0.003, prev:blip.position.clone() });
}

addEventListener('resize', () => {
  camera.aspect = innerWidth/innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(innerWidth, innerHeight);
});

const container = document.querySelector('.container');
let scrollFactor = 0;
if (container) {
  container.addEventListener('scroll', () => {
    const max = container.scrollHeight - container.clientHeight;
    scrollFactor = max > 0 ? container.scrollTop / max : 0;
  });
}

function lerp(a, b, t) { return a+(b-a)*t; }
let sweepAngle = 0, running = true, lookYCurrent = 0;
document.addEventListener('visibilitychange', () => {
  running = !document.hidden;
  if (running) animate();
});

function animate() {
  if (!running) return;
  sweepAngle += 0.012;
  sweepGroup.rotation.y = sweepAngle;
  const sx = Math.cos(sweepAngle), sz = -Math.sin(sweepAngle);
  blips.forEach(b => {
    b.angle += b.drift;
    b.prev.copy(b.mesh.position);
    b.mesh.position.x = Math.cos(b.angle)*b.dist;
    b.mesh.position.z = Math.sin(b.angle)*b.dist;
    b.mesh.position.y = b.y;
    b.trail.geometry.setFromPoints([b.prev, b.mesh.position]);
    const mag = Math.hypot(b.mesh.position.x, b.mesh.position.z) || 1;
    const dot = (sx*b.mesh.position.x + sz*b.mesh.position.z) / mag;
    const intensity = Math.max(0, dot);
    b.mesh.scale.setScalar(0.4 + intensity*0.6);
    b.mesh.material.opacity = 0.25 + intensity*0.75;
  });
  camera.position.y = lerp(camera.position.y, lerp(8, 5, scrollFactor), 0.06);
  camera.position.z = lerp(camera.position.z, lerp(14, 10, scrollFactor), 0.06);
  lookYCurrent = lerp(lookYCurrent, lerp(0, -0.3, scrollFactor), 0.06);
  camera.lookAt(0, lookYCurrent, 0);
  renderer.render(scene, camera);
  requestAnimationFrame(animate);
}
animate();

// ===== Helpers =====
function airportCode(s) {
  if (!s || s === '-') return '—';
  const m = s.match(/\(([A-Z0-9]{3,4})\)/);
  if (m) return m[1];
  return s.slice(0, 3).toUpperCase();
}
function altColor(ft) {
  if (ft == null) return null;
  const n = Number(ft);
  if (n < 25000) return 'var(--mint)';
  if (n <= 35000) return 'var(--amber)';
  return 'var(--coral)';
}
function altLabel(ft) {
  if (ft == null) return '— — —';
  return Math.round(Number(ft)/1000) + 'k';
}
function lastTime(jstStr) {
  if (!jstStr || jstStr === '-') return '—';
  const m = jstStr.match(/\d{4}-\d{2}-\d{2} (\d{2}:\d{2}:\d{2})/);
  return m ? m[1] : jstStr;
}
function nVal(v) { return (v === '-' || v == null) ? null : v; }

// ===== Date picker =====
const todayStr = (() => {
  const j = new Date(Date.now() + 9*3600*1000);
  return `${j.getUTCFullYear()}-${pad(j.getUTCMonth()+1)}-${pad(j.getUTCDate())}`;
})();
function dateParts(value) {
  const [year, month, day] = value.split('-').map(Number);
  return { year, month, day };
}
function dateString(year, month, day) {
  return `${year}-${pad(month)}-${pad(day)}`;
}
function displayDate(value) { return value.replaceAll('-', '/'); }

const dateControl = document.getElementById('dateControl');
const datePicker = document.getElementById('datePicker');
const dateValue = document.getElementById('dateValue');
const calendarPopover = document.getElementById('calendarPopover');
const calendarMonth = document.getElementById('calendarMonth');
const calendarDays = document.getElementById('calendarDays');
const calendarPrev = document.getElementById('calendarPrev');
const calendarNext = document.getElementById('calendarNext');
const calendarToday = document.getElementById('calendarToday');
// calendar label i18n——template 入面係英文 fallback，呢度按語言填
if (T.cal_weekdays) {
  const wd = T.cal_weekdays.split(',');
  document.querySelectorAll('.calendar-weekdays span').forEach((el, i) => { if (wd[i]) el.textContent = wd[i]; });
}
if (T.cal_today) calendarToday.textContent = T.cal_today;
if (T.cal_date_lbl) datePicker.dataset.label = T.cal_date_lbl;
if (T.cal_aria_choose) calendarPopover.setAttribute('aria-label', T.cal_aria_choose);
if (T.cal_aria_prev) calendarPrev.setAttribute('aria-label', T.cal_aria_prev);
if (T.cal_aria_next) calendarNext.setAttribute('aria-label', T.cal_aria_next);
let currentDay = todayStr;
let calendarView = { ...dateParts(todayStr) };
dateValue.textContent = displayDate(currentDay);

function setCalendarOpen(open) {
  dateControl.classList.toggle('open', open);
  calendarPopover.hidden = !open;
  datePicker.setAttribute('aria-expanded', String(open));
  if (open) renderCalendar();
}
function selectDay(value) {
  currentDay = value;
  dateValue.textContent = displayDate(value);
  calendarView = { ...dateParts(value) };
  setCalendarOpen(false);
  load();
}
function renderCalendar() {
  const { year, month } = calendarView;
  calendarMonth.textContent = `${year} · ${pad(month)}`;
  const firstWeekday = new Date(Date.UTC(year, month - 1, 1)).getUTCDay();
  const daysInMonth = new Date(Date.UTC(year, month, 0)).getUTCDate();
  const prevMonthDays = new Date(Date.UTC(year, month - 1, 0)).getUTCDate();
  const cells = [];

  for (let i = 0; i < 42; i++) {
    let cellYear = year;
    let cellMonth = month;
    let day = i - firstWeekday + 1;
    let otherMonth = false;
    if (day < 1) {
      otherMonth = true;
      cellMonth -= 1;
      if (cellMonth < 1) { cellMonth = 12; cellYear -= 1; }
      day = prevMonthDays + day;
    } else if (day > daysInMonth) {
      otherMonth = true;
      day -= daysInMonth;
      cellMonth += 1;
      if (cellMonth > 12) { cellMonth = 1; cellYear += 1; }
    }
    const value = dateString(cellYear, cellMonth, day);
    const classes = ['calendar-day'];
    if (otherMonth) classes.push('other-month');
    if (value === todayStr) classes.push('today');
    if (value === currentDay) classes.push('selected');
    cells.push(`<button type="button" class="${classes.join(' ')}" data-date="${value}"${value > todayStr ? ' disabled' : ''}>${day}</button>`);
  }
  calendarDays.innerHTML = cells.join('');
  const today = dateParts(todayStr);
  calendarNext.disabled = year > today.year || (year === today.year && month >= today.month);
}

datePicker.addEventListener('click', () => setCalendarOpen(calendarPopover.hidden));
calendarPrev.addEventListener('click', () => {
  calendarView.month -= 1;
  if (calendarView.month < 1) { calendarView.month = 12; calendarView.year -= 1; }
  renderCalendar();
});
calendarNext.addEventListener('click', () => {
  calendarView.month += 1;
  if (calendarView.month > 12) { calendarView.month = 1; calendarView.year += 1; }
  renderCalendar();
});
calendarDays.addEventListener('click', (e) => {
  const day = e.target.closest('.calendar-day:not(:disabled)');
  if (day) selectDay(day.dataset.date);
});
calendarToday.addEventListener('click', () => selectDay(todayStr));
document.addEventListener('click', (e) => {
  if (!dateControl.contains(e.target)) setCalendarOpen(false);
});
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape' && !calendarPopover.hidden) {
    setCalendarOpen(false);
    datePicker.focus();
  }
});

// ===== Search =====
const searchInput = document.getElementById('search');
addEventListener('keydown', (e) => {
  if (e.key === '/' && document.activeElement !== searchInput
      && !['INPUT','TEXTAREA'].includes(document.activeElement?.tagName)) {
    e.preventDefault();
    searchInput.focus();
  } else if (e.key === 'Escape' && document.activeElement === searchInput) {
    searchInput.value = '';
    applyFilter();
    searchInput.blur();
  }
});
searchInput.addEventListener('input', applyFilter);

function applyFilter() {
  const q = searchInput.value.trim().toLowerCase();
  document.querySelectorAll('.flight').forEach(el => {
    const hay = el.dataset.search || '';
    el.classList.toggle('hidden', q && !hay.includes(q));
  });
  document.querySelectorAll('.group').forEach(g => {
    // search 緊嗰陣連摺埋嘅 extra row 都要現身，唔係搵唔到第 11 架之後嘅機
    g.classList.toggle('search-show', !!q);
    const visible = g.querySelectorAll('.flight:not(.hidden)').length > 0;
    g.style.display = (q && !visible) ? 'none' : '';
  });
}

// ===== Collapse / 展開全部 =====
document.addEventListener('click', (e) => {
  const more = e.target.closest('.more-btn');
  if (more) { more.closest('.group').classList.add('expanded'); return; }
  const hdr = e.target.closest('.group-hdr');
  if (hdr) hdr.parentElement.classList.toggle('collapsed');
});

// ===== Load + render =====
let _homeLoadSeq = 0;
async function load() {
  // 快手連換日期時，遲返嚟嘅舊 response 唔可以覆寫新揀嗰日
  const seq = ++_homeLoadSeq;
  document.getElementById('groups').innerHTML = `<div class="loading">${esc(T.loading)}</div>`;
  const res = await fetch(`/api/today?day=${currentDay}`);
  const data = await res.json();
  if (seq !== _homeLoadSeq) return;
  render(data);
  // 重新 render 完要重套現有 search，唔係 extra row 同無關行會走樣
  if (searchInput.value.trim()) applyFilter();
}

// 一行 aircraft row。extra = 第 11 架起，預設摺埋（撳 .more-btn / search 時先現身）
function flightRow(f, extra) {
  const altMax = nVal(f.max_alt_baro);
  const altPct = altMax != null ? Math.min(100, Number(altMax)/45000*100) : 0;
  const altC = altColor(altMax);
  const altLbl = altLabel(altMax);
  const fromC = airportCode(f.from_airport);
  const toC = airportCode(f.to_airport);
  const hay = [f.icao, f.flight, f.registration, f.aircraft_type, fromC, toC, f.operator]
    .filter(x => x && x !== '-').map(s => String(s).toLowerCase()).join(' ');
  const tipParts = [];
  if (f.first_seen_jst !== '-') tipParts.push('First: ' + f.first_seen_jst);
  if (f.last_seen_jst !== '-') tipParts.push('Last: ' + f.last_seen_jst);
  if (f.min_alt_baro !== '-' || f.max_alt_baro !== '-')
    tipParts.push(`Alt: ${f.min_alt_baro}–${f.max_alt_baro} ft`);
  tipParts.push(`${f.samples} samples`);
  const tip = tipParts.join(' · ');
  const regCell = f.registration !== '-'
    ? `<a href="https://www.flightradar24.com/data/aircraft/${encodeURIComponent(String(f.registration).toLowerCase())}" target="_blank" rel="noreferrer">${esc(f.registration)}</a>`
    : '—';
  return `
  <div class="flight${extra ? ' extra' : ''}" data-search="${esc(hay)}" title="${esc(tip)}">
    <div class="icao"><a href="/aircraft/${esc(f.icao)}/">${esc(f.icao)}</a></div>
    <div class="flight-no">${esc(f.flight !== '-' ? f.flight : '—')}</div>
    <div class="reg">${regCell}</div>
    <div class="type">${esc(f.aircraft_type !== '-' ? f.aircraft_type : '—')}</div>
    <div class="route"><span>${fromC}</span><span class="arrow">►</span><span>${toC}</span></div>
    <div class="alt">
      <div class="bar"><div style="width:${altPct.toFixed(1)}%; background:${altC || 'transparent'}"></div></div>
      <div class="alt-label" style="color:${altC || 'var(--x-muted)'}">${altLbl}</div>
    </div>
    <div class="last">${esc(lastTime(f.last_seen_jst))}</div>
  </div>`;
}

function render(data) {
  // Stats
  document.getElementById('s-today').textContent = data.count;
  document.getElementById('s-ops').textContent = data.operators.length;
  let peakAlt = 0;
  for (const r of data.rows) {
    const v = nVal(r.max_alt_baro);
    if (v != null && Number(v) > peakAlt) peakAlt = Number(v);
  }
  document.getElementById('s-peak').textContent = peakAlt ? Math.round(peakAlt/1000) + 'k' : '—';
  const routes = new Set();
  for (const r of data.rows) {
    if (r.from_airport !== '-' && r.to_airport !== '-')
      routes.add(r.from_airport + '→' + r.to_airport);
  }
  document.getElementById('s-routes').textContent = routes.size;

  // Recent contacts (latest 8 by last_seen — API 已 sort)
  const rcGrid = document.getElementById('rc-grid');
  const recent = data.rows.slice(0, 8);
  document.getElementById('rc-count').textContent = recent.length + ' TRACKS';
  rcGrid.innerHTML = recent.map(f => {
    const altMax = nVal(f.max_alt_baro);
    const altPct = altMax != null ? Math.min(100, Number(altMax)/45000*100) : 0;
    const altC = altColor(altMax);
    const altLbl = altLabel(altMax);
    const fromC = airportCode(f.from_airport);
    const toC = airportCode(f.to_airport);
    const regCell = f.registration !== '-'
      ? `<a href="https://www.flightradar24.com/data/aircraft/${encodeURIComponent(String(f.registration).toLowerCase())}" target="_blank" rel="noreferrer">${esc(f.registration)}</a>`
      : '—';
    return `
    <div class="flight">
      <div class="icao"><a href="/aircraft/${esc(f.icao)}/">${esc(f.icao)}</a></div>
      <div class="op-name">${esc(f.operator !== '-' ? f.operator : '—')}</div>
      <div class="flight-no">${esc(f.flight !== '-' ? f.flight : '—')}</div>
      <div class="reg">${regCell}</div>
      <div class="type">${esc(f.aircraft_type !== '-' ? f.aircraft_type : '—')}</div>
      <div class="route"><span>${fromC}</span><span class="arrow">►</span><span>${toC}</span></div>
      <div class="alt">
        <div class="bar"><div style="width:${altPct.toFixed(1)}%; background:${altC || 'transparent'}"></div></div>
        <div class="alt-label" style="color:${altC || 'var(--x-muted)'}">${altLbl}</div>
      </div>
      <div class="last">${esc(lastTime(f.last_seen_jst))}</div>
    </div>`;
  }).join('');

  // Group by operator
  const groups = new Map();
  for (const r of data.rows) {
    const op = r.operator === '-' ? '(UNKNOWN)' : r.operator;
    if (!groups.has(op)) groups.set(op, { operator:op, country:r.country, flights:[], samples:0 });
    const g = groups.get(op);
    g.flights.push(r);
    g.samples += Number(r.samples || 0);
    if (r.country !== '-' && (g.country === '-' || !g.country)) g.country = r.country;
  }
  const sorted = [...groups.values()].sort((a, b) => b.flights.length - a.flights.length);

  const root = document.getElementById('groups');
  if (!sorted.length) {
    root.innerHTML = `<div class="empty">${esc(T.no_data || '冇資料')}</div>`;
    return;
  }
  root.innerHTML = sorted.map(g => `
    <div class="group">
      <div class="group-hdr">
        <div class="left">
          <span class="op"><span class="diamond">◆</span>${esc(g.operator)}</span>
          <span class="country">${esc(g.country !== '-' ? g.country : '')}</span>
        </div>
        <div class="meta">
          <span>SEEN ${g.samples}×</span>
          <span>${g.flights.length} TRACKS</span>
        </div>
      </div>
      <div class="group-body">
        <div class="flight-cols">
          <div>ICAO</div><div>FLIGHT</div><div>REG</div><div>TYPE</div><div>ROUTE</div><div>ALTITUDE</div><div>LAST</div>
        </div>
        ${g.flights.slice(0, 10).map(f => flightRow(f)).join('')}
        ${g.flights.length > 10 ? `
          ${g.flights.slice(10).map(f => flightRow(f, true)).join('')}
          <button type="button" class="more-btn">${esc((T.home_show_all || '▼ +{n}').replace('{n}', g.flights.length - 10))}</button>
        ` : ''}
      </div>
    </div>
  `).join('');

  // Cascading reveal as group scrolls into view
  const io = new IntersectionObserver(entries => {
    entries.forEach(e => {
      if (e.isIntersecting) { e.target.classList.add('in'); io.unobserve(e.target); }
    });
  }, { root:container, threshold:0.15 });
  document.querySelectorAll('.group').forEach(el => io.observe(el));
}
load();
