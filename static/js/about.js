// /about page JS — 由舊 ABOUT_HTML inline <script> 抽出。
// fetch /api/about 每 5 秒更新 receiver / feed health + Three.js radar 背景。

import * as THREE from 'https://unpkg.com/three@0.160.0/build/three.module.js';

// ===== format helpers =====

function relTime(secs) {
  if (secs == null) return '—';
  let n, u;
  if (secs < 60) { n = secs; u = T.about_unit_sec; }
  else if (secs < 3600) { n = Math.floor(secs/60); u = T.about_unit_min; }
  else if (secs < 86400) { n = Math.floor(secs/3600); u = T.about_unit_hr; }
  else { n = Math.floor(secs/86400); u = T.about_unit_day; }
  return (T.about_ago_fmt || '{n} {u}前').replace('{n}', n).replace('{u}', u);
}

function uptimeFmt(secs) {
  const d = Math.floor(secs/86400);
  const h = Math.floor((secs%86400)/3600);
  const m = Math.floor((secs%3600)/60);
  if (d > 0) return `${d}d ${pad(h)}h`;
  if (h > 0) return `${h}h ${pad(m)}m`;
  return `${m}m`;
}

function setFeed(id, cls, txt) {
  const el = document.getElementById(id);
  if (el) el.className = 'feed ' + cls;
  const tx = document.getElementById(id + '-txt');
  if (tx) tx.textContent = txt;
}

// ===== load + render =====

async function loadAbout() {
  let r = null;
  try { r = await (await fetch('/api/about')).json(); } catch (e) { r = null; }
  const ok = !!r;
  if (ok) {
    document.getElementById('ab-receiver').textContent = r.receiver;
    document.getElementById('ab-source').textContent = r.source;
    document.getElementById('ab-uptime').textContent = uptimeFmt(r.uptime_secs);
    document.getElementById('ab-last').textContent = relTime(r.last_update_secs);
    setFeed('ab-feed', r.feed_health, T['about_feed_' + r.feed_health] || r.feed_health);
  } else {
    setFeed('ab-feed', 'down', 'error');
  }
  // System Health 個 panel：頁面攞到 data 即係 API + DB 都 ok
  setFeed('hl-api', ok ? 'ok' : 'down', ok ? 'OK' : 'DOWN');
  setFeed('hl-db', ok ? 'ok' : 'down', ok ? 'OK' : 'DOWN');
  document.getElementById('hl-last').textContent = ok ? relTime(r.last_update_secs) : '—';
  document.getElementById('hl-records').textContent =
    (ok && r.records_today != null) ? r.records_today : '—';
}
loadAbout();
setInterval(loadAbout, 5000);

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
wedge.rotation.x = -Math.PI/2;
sweepGroup.add(wedge);
scene.add(sweepGroup);
addEventListener('resize', () => {
  camera.aspect = innerWidth/innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(innerWidth, innerHeight);
});
function animate() {
  sweepGroup.rotation.y -= 0.012;
  renderer.render(scene, camera);
  requestAnimationFrame(animate);
}
animate();
