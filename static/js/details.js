// /details page JS — 由舊 DETAILS_HTML inline <script type="module"> 抽出。
// Three.js radar 背景（fancier than stats：有 blips + 滾動聯動 camera）+ 控制 dropdown + 表格 load。
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

// 14 個 blip（用 amber 標假飛機 + trail）
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

// scroll 越落，camera 越壓低（plane 視角）。
// base.html 框架嘅 .container 係 scroll viewport。
const cont = document.querySelector('.container');
let scrollFactor = 0;
if (cont) {
  cont.addEventListener('scroll', () => {
    const max = cont.scrollHeight - cont.clientHeight;
    scrollFactor = max > 0 ? cont.scrollTop / max : 0;
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

// ===== ICAO ADS-B category emoji（同 aircraft.js 一致） =====
function categoryIcon(code) {
  if (!code) return '';
  const c = String(code).trim().toUpperCase();
  if (c === 'A7') return '🚁';
  if (c === 'B1') return '🪁';
  if (c === 'B2' || c === 'B6') return '🎈';
  if (c.startsWith('C')) return '🚗';
  return '';
}

// ===== 表格 + 控制 =====

const day = document.getElementById('day');
const sort = document.getElementById('sort');
const rowsEl = document.getElementById('rows');
const meta = document.getElementById('meta');
const loadBtn = document.getElementById('load');
const countryFilter = document.getElementById('countryFilter');
const operatorFilter = document.getElementById('operatorFilter');
const typeFilter = document.getElementById('typeFilter');
const fromFilter = document.getElementById('fromFilter');
const toFilter = document.getElementById('toFilter');

function dateParts(value) {
  const [year, month, date] = value.split('-').map(Number);
  return { year, month, date };
}
function dateString(year, month, date) {
  return `${year}-${pad(month)}-${pad(date)}`;
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
// calendar label i18n——template 入面係英文 fallback，呢度按語言填（同 home.js 一致）
if (T.cal_weekdays) {
  const wd = T.cal_weekdays.split(',');
  document.querySelectorAll('.calendar-weekdays span').forEach((el, i) => { if (wd[i]) el.textContent = wd[i]; });
}
if (T.cal_today) calendarToday.textContent = T.cal_today;
if (T.cal_aria_choose) calendarPopover.setAttribute('aria-label', T.cal_aria_choose);
if (T.cal_aria_prev) calendarPrev.setAttribute('aria-label', T.cal_aria_prev);
if (T.cal_aria_next) calendarNext.setAttribute('aria-label', T.cal_aria_next);
const todayJST = new Date(Date.now() + 9*3600*1000);
const todayStr = dateString(todayJST.getUTCFullYear(), todayJST.getUTCMonth()+1, todayJST.getUTCDate());
let calendarView = { ...dateParts(todayStr) };

function setCalendarOpen(open) {
  dateControl.classList.toggle('open', open);
  calendarPopover.hidden = !open;
  datePicker.setAttribute('aria-expanded', String(open));
  if (open) renderCalendar();
}
function selectDay(value) {
  day.value = value;
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
    let cellDate = i - firstWeekday + 1;
    let otherMonth = false;
    if (cellDate < 1) {
      otherMonth = true;
      cellMonth -= 1;
      if (cellMonth < 1) { cellMonth = 12; cellYear -= 1; }
      cellDate = prevMonthDays + cellDate;
    } else if (cellDate > daysInMonth) {
      otherMonth = true;
      cellDate -= daysInMonth;
      cellMonth += 1;
      if (cellMonth > 12) { cellMonth = 1; cellYear += 1; }
    }
    const value = dateString(cellYear, cellMonth, cellDate);
    const classes = ['calendar-day'];
    if (otherMonth) classes.push('other-month');
    if (value === todayStr) classes.push('today');
    if (value === day.value) classes.push('selected');
    cells.push(`<button type="button" class="${classes.join(' ')}" data-date="${value}"${value > todayStr ? ' disabled' : ''}>${cellDate}</button>`);
  }
  calendarDays.innerHTML = cells.join('');
  const today = dateParts(todayStr);
  calendarNext.disabled = year > today.year || (year === today.year && month >= today.month);
}

let _loadSeq = 0;
async function load() {
  // 快手連換日期 / filter 時，遲返嚟嘅舊 response 唔可以覆寫新嗰個
  const seq = ++_loadSeq;
  const qs = new URLSearchParams({
    day: day.value, sort: sort.value,
    country: countryFilter.value, operator: operatorFilter.value, type: typeFilter.value,
    from: fromFilter.value, to: toFilter.value,
  });
  const res = await fetch('/api/today?' + qs.toString());
  const data = await res.json();
  if (seq !== _loadSeq) return;
  meta.textContent = (T.meta_template || '{day} · {count} · {sort}')
    .replace('{day}', data.day).replace('{count}', data.count).replace('{sort}', data.sort);

  // 每次都 rebuild dropdown options，但 keep 現有 selection 如果 list 仲有
  function refillSelect(el, values) {
    const cur = el.value;
    while (el.options.length > 1) el.remove(1);
    values.forEach(v => el.insertAdjacentHTML('beforeend', `<option value="${esc(v)}">${esc(v)}</option>`));
    el.value = values.includes(cur) ? cur : '';
  }
  refillSelect(countryFilter, data.countries);
  refillSelect(operatorFilter, data.operators);
  refillSelect(typeFilter, data.types);
  refillSelect(fromFilter, data.from_airports);
  refillSelect(toFilter, data.to_airports);

  rowsEl.innerHTML = data.rows.map(r => {
    const ic = categoryIcon(r.category);
    return `
    <tr>
      <td>${ic ? ic + ' ' : ''}<a class="ac-link" href="/aircraft/${esc(r.icao)}/">${esc(r.icao)}</a></td>
      <td>${esc(r.flight)}</td>
      <td>${esc(r.from_airport)}</td>
      <td>${esc(r.to_airport)}</td>
      <td>${esc(r.operator)}</td>
      <td>${r.registration !== '-' ? `<a href="https://www.flightradar24.com/data/aircraft/${encodeURIComponent(r.registration.toLowerCase())}" target="_blank" rel="noreferrer">${esc(r.registration)}</a>` : '-'}</td>
      <td>${esc(r.aircraft_type)}</td>
      <td>${esc(r.country)}</td>
      <td>${esc(r.category)}</td>
      <td>${esc(r.min_alt_baro)}</td>
      <td>${esc(r.max_alt_baro)}</td>
      <td>${esc(r.samples)}</td>
      <td>${esc(r.first_seen_jst)}</td>
      <td>${esc(r.last_seen_jst)}</td>
    </tr>`;
  }).join('');
}

// 預設今日（JST）
day.value = todayStr;
dateValue.textContent = displayDate(todayStr);

loadBtn.addEventListener('click', load);
sort.addEventListener('change', load);
countryFilter.addEventListener('change', load);
operatorFilter.addEventListener('change', load);
typeFilter.addEventListener('change', load);
fromFilter.addEventListener('change', load);
toFilter.addEventListener('change', load);
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
  const selected = e.target.closest('.calendar-day:not(:disabled)');
  if (selected) selectDay(selected.dataset.date);
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

load();
// 表頭 click 排序（thead 靜態，attach 一次即可；同 sort dropdown 並存）
makeSortable(rowsEl.closest('table'));
