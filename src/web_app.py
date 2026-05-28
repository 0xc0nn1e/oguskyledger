import html
import json
import re
from datetime import date, datetime, timedelta, timezone
from http import cookies as http_cookies
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import auth
from db import connect, dict_cursor

HOST = '0.0.0.0'
PORT = 8765
JST = timezone(timedelta(hours=9))
ALLOWED_SORTS = {
    'last_seen': 'last_seen DESC',
    'country': 'country ASC, operator ASC, last_seen DESC',
    'operator': 'operator ASC, country ASC, last_seen DESC',
    'type': 'aircraft_type ASC, operator ASC, last_seen DESC',
}

# i18n（JP default / HK / EN）。Country / Operator 嘅資料本身入 DB 用中文，唔翻譯。
LANGS = ('jp', 'hk', 'en')
DEFAULT_LANG = 'jp'
HTML_LANG_ATTR = {'jp': 'ja', 'hk': 'zh-HK', 'en': 'en'}

STRINGS = {
    'jp': {
        'site_title': '航空レーダー · plane-history',
        'details_title': '詳細 · plane-history',
        'login_title': 'ログイン · plane-history',
        'account_title': 'パスワード変更 · plane-history',
        'nav_details': '詳細',
        'nav_home': '← トップ',
        'nav_login': 'ログイン',
        'nav_logout': 'ログアウト',
        'nav_account': 'アカウント',
        'loading': '読み込み中...',
        'no_data': '// 本日データなし',
        'cta_details': '▸  詳細ビューを開く  ▸',
        'lead_template': '{day} JST · {total}機 · {ops}社',
        'aircraft_unit': 'AIRCRAFT',
        'lbl_date': '日付',
        'lbl_sort': 'ソート',
        'lbl_country': '国',
        'lbl_operator': '運航会社',
        'lbl_type': '機種',
        'lbl_from': '出発',
        'lbl_to': '到着',
        'lbl_all': 'すべて',
        'btn_update': '更新',
        'meta_template': 'Day: {day} | Aircraft: {count} | Sort: {sort}',
        'login_heading': 'ログイン',
        'lbl_username': 'ユーザー名',
        'lbl_password': 'パスワード',
        'btn_login': 'ログイン',
        'err_login': 'ユーザー名またはパスワードが違います',
        'link_back_home': '← トップに戻る',
        'account_heading': 'パスワード変更',
        'lbl_current_pw': '現在のパスワード',
        'lbl_new_pw': '新しいパスワード',
        'lbl_confirm_pw': 'もう一度入力',
        'btn_update_pw': 'パスワードを更新',
        'err_current_wrong': '現在のパスワードが違います',
        'err_pw_mismatch': '新しいパスワードが一致しません',
        'err_pw_short': 'パスワードは6文字以上必要です',
        'ok_pw_updated': '✓ パスワードを更新しました',
        'search_placeholder': '/ で検索',
    },
    'hk': {
        'site_title': '航空雷達 · plane-history',
        'details_title': '詳細 · plane-history',
        'login_title': '登入 · plane-history',
        'account_title': '改密碼 · plane-history',
        'nav_details': '詳細',
        'nav_home': '← 首頁',
        'nav_login': '登入',
        'nav_logout': '登出',
        'nav_account': '改密碼',
        'loading': '載入中...',
        'no_data': '// 今日未有資料',
        'cta_details': '▸  開詳細表  ▸',
        'lead_template': '{day} JST · {total} 架機 · {ops} 個營運商',
        'aircraft_unit': 'AIRCRAFT',
        'lbl_date': '日期',
        'lbl_sort': '排序',
        'lbl_country': '國家',
        'lbl_operator': '營運商',
        'lbl_type': '機型',
        'lbl_from': '由',
        'lbl_to': '去',
        'lbl_all': '全部',
        'btn_update': '更新',
        'meta_template': 'Day: {day} | Aircraft: {count} | Sort: {sort}',
        'login_heading': '登入 plane-history',
        'lbl_username': 'Username',
        'lbl_password': '密碼',
        'btn_login': '登入',
        'err_login': 'Username 或密碼錯誤',
        'link_back_home': '← 返首頁',
        'account_heading': '改密碼',
        'lbl_current_pw': '而家嘅密碼',
        'lbl_new_pw': '新密碼',
        'lbl_confirm_pw': '再入一次',
        'btn_update_pw': '更新密碼',
        'err_current_wrong': '而家嘅密碼錯',
        'err_pw_mismatch': '兩次新密碼唔一樣',
        'err_pw_short': '新密碼至少 6 個字',
        'ok_pw_updated': '✓ 密碼已更新',
        'search_placeholder': '/ 搜尋',
    },
    'en': {
        'site_title': 'Aviation Radar · plane-history',
        'details_title': 'Details · plane-history',
        'login_title': 'Sign in · plane-history',
        'account_title': 'Change password · plane-history',
        'nav_details': 'DETAILS',
        'nav_home': '← HOME',
        'nav_login': 'SIGN IN',
        'nav_logout': 'SIGN OUT',
        'nav_account': 'ACCOUNT',
        'loading': 'loading...',
        'no_data': '// no data today',
        'cta_details': '▸  OPEN DETAILED VIEW  ▸',
        'lead_template': '{day} JST · {total} aircraft · {ops} operators',
        'aircraft_unit': 'AIRCRAFT',
        'lbl_date': 'Date',
        'lbl_sort': 'Sort',
        'lbl_country': 'Country',
        'lbl_operator': 'Operator',
        'lbl_type': 'Type',
        'lbl_from': 'From',
        'lbl_to': 'To',
        'lbl_all': 'all',
        'btn_update': 'Update',
        'meta_template': 'Day: {day} | Aircraft: {count} | Sort: {sort}',
        'login_heading': 'Sign in to plane-history',
        'lbl_username': 'Username',
        'lbl_password': 'Password',
        'btn_login': 'Sign in',
        'err_login': 'Wrong username or password',
        'link_back_home': '← Back to home',
        'account_heading': 'Change password',
        'lbl_current_pw': 'Current password',
        'lbl_new_pw': 'New password',
        'lbl_confirm_pw': 'Confirm new password',
        'btn_update_pw': 'Update password',
        'err_current_wrong': 'Current password is wrong',
        'err_pw_mismatch': 'New passwords do not match',
        'err_pw_short': 'Password must be at least 6 characters',
        'ok_pw_updated': '✓ Password updated',
        'search_placeholder': '/ to search',
    },
}


def _render(template, lang):
    s = STRINGS[lang]
    def repl(m):
        return s.get(m.group(1), m.group(0))
    out = re.sub(r'\{\{T_([a-z_]+)\}\}', repl, template)
    out = out.replace('{{LANG}}', lang)
    out = out.replace('{{HTML_LANG}}', HTML_LANG_ATTR[lang])
    out = out.replace('{{T_JSDICT}}', json.dumps(s, ensure_ascii=False))
    return out

FAVICON_SVG = '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">
  <rect width="32" height="32" rx="3" fill="#050a0d"/>
  <circle cx="16" cy="16" r="13" fill="none" stroke="#1f5a4a" stroke-width="0.8"/>
  <circle cx="16" cy="16" r="9"  fill="none" stroke="#1f5a4a" stroke-width="0.8"/>
  <circle cx="16" cy="16" r="5"  fill="none" stroke="#1f5a4a" stroke-width="0.8"/>
  <line x1="3"  y1="16" x2="29" y2="16" stroke="#1f5a4a" stroke-width="0.5" opacity="0.6"/>
  <line x1="16" y1="3"  x2="16" y2="29" stroke="#1f5a4a" stroke-width="0.5" opacity="0.6"/>
  <line x1="16" y1="16" x2="29" y2="16" stroke="#7fffd4" stroke-width="1.5" opacity="0.85"/>
  <circle cx="16" cy="16" r="1.8" fill="#7fffd4"/>
  <circle cx="22" cy="10" r="1.4" fill="#f5d96f" opacity="0.85"/>
  <circle cx="9"  cy="20" r="1"   fill="#f5d96f" opacity="0.5"/>
</svg>'''

DETAILS_HTML = '''<!doctype html>
<html lang="{{HTML_LANG}}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{{T_details_title}}</title>
  <link rel="icon" type="image/svg+xml" href="/favicon.svg">
  <style>
    :root {
      --bg: #050a0d;
      --mint: #7fffd4;
      --mint-light: #aafff0;
      --amber: #f5d96f;
      --muted: #4a8a7a;
      --x-muted: #3a6a5a;
      --card: rgba(15,31,34,0.7);
      --card-body: rgba(10,20,22,0.7);
      --hdr-bar: rgba(15,31,34,0.85);
      --border: 0.5px solid rgba(127,255,212,0.15);
    }
    * { box-sizing: border-box; }
    html, body { margin:0; padding:0; height:100%;
      background: var(--bg); color: var(--mint);
      font-family: 'SF Mono', 'Menlo', 'Courier New', monospace;
      -webkit-font-smoothing: antialiased;
    }
    body { overflow: hidden; }

    #radar { position: fixed; inset:0; z-index:0; width:100vw; height:100vh; }
    .bg-vignette {
      position: fixed; inset:0; z-index:1; pointer-events:none;
      background: radial-gradient(ellipse at center, transparent 35%, rgba(5,10,13,0.85) 95%);
    }

    .container {
      position: relative; z-index: 2;
      height: 100vh; overflow-y: auto; overflow-x: hidden;
      scrollbar-width: thin; scrollbar-color: var(--x-muted) transparent;
    }
    .container::-webkit-scrollbar { width: 6px; }
    .container::-webkit-scrollbar-thumb { background: rgba(127,255,212,0.15); border-radius: 3px; }
    .inner { max-width: 1400px; margin: 0 auto; padding: 24px 32px 60px; }

    header.page-hdr { padding-bottom: 14px; margin-bottom: 18px;
      border-bottom: 1px solid rgba(127,255,212,0.15); }
    .hdr-row { display:flex; align-items:center; justify-content:space-between; gap:16px; }
    .hdr-row.top { font-size:10px; letter-spacing:3px; color: var(--muted); text-transform: uppercase; }
    .hdr-row.top .dot { color: var(--mint); animation: blink 2s infinite; margin-right:4px; }
    @keyframes blink { 50% { opacity: 0.35 } }
    .hdr-row.main { margin: 6px 0 4px; }
    .hdr-row.main .title { font-size: 22px; letter-spacing: 1px; color: var(--mint); font-weight: 500; margin: 0; }
    .hdr-row.main .title a { color: inherit; text-decoration: none; }
    .hdr-row.main .title a:hover { color: var(--mint-light); }
    .hdr-row.main .clock { font-size: 16px; color: var(--mint); letter-spacing: 1px; }
    .hdr-row.sub { font-size:10px; letter-spacing:2px; color: var(--x-muted); }
    .hdr-row.sub .coords { text-transform: uppercase; }

    .tools { display:flex; gap:6px; align-items:center; }
    .tools .nav a, .tools .nav button {
      background: rgba(15,31,34,0.6); color: var(--mint);
      border: var(--border); border-radius: 4px;
      font: inherit; font-size: 10px; letter-spacing: 1.5px;
      padding: 6px 10px; outline: none; cursor: pointer;
      text-decoration: none;
    }
    .tools .nav a:hover, .tools .nav button:hover { color: var(--mint); border-color: var(--mint); }
    .nav { display:flex; gap:4px; align-items:center; }
    .nav form { display:inline; margin:0; }
    .lang-switch { display:inline-flex; gap:2px; margin-right:4px; }
    .lang-switch a {
      color: var(--muted); text-decoration:none; font-size:10px;
      padding: 5px 8px; border: var(--border); border-radius: 4px;
      letter-spacing: 0.1em; background: rgba(15,31,34,0.6);
    }
    .lang-switch a.on { color: var(--mint); border-color: var(--mint); }

    .controls {
      display:flex; gap:8px; flex-wrap:wrap; align-items:flex-end;
      margin-bottom: 14px;
      padding: 12px 14px;
      background: var(--card); border: var(--border); border-radius: 4px;
    }
    .controls label {
      display:flex; flex-direction:column; gap:4px;
      font-size: 9px; letter-spacing: 1.5px; color: var(--muted); text-transform: uppercase;
    }
    .controls input, .controls select {
      background: rgba(10,20,22,0.8); color: var(--mint);
      border: var(--border); border-radius: 4px;
      font: inherit; font-size: 11px; padding: 5px 8px; outline: none;
    }
    .controls input[type="date"] { color-scheme: dark; }
    .controls input:focus, .controls select:focus { border-color: var(--mint); }
    .controls button {
      background: rgba(127,255,212,0.08); color: var(--mint);
      border: var(--border); border-radius: 4px;
      font: inherit; font-size: 10px; letter-spacing: 1.5px;
      padding: 6px 14px; cursor: pointer; align-self: flex-end;
      text-transform: uppercase;
    }
    .controls button:hover { background: rgba(127,255,212,0.15); }

    .meta {
      font-size: 10px; letter-spacing: 1.5px; color: var(--muted);
      text-transform: uppercase; margin-bottom: 10px;
    }

    .wrap {
      overflow: auto;
      border: var(--border); border-radius: 4px;
      background: var(--card-body);
      max-height: calc(100vh - 280px);
    }
    .wrap::-webkit-scrollbar { width: 6px; height: 6px; }
    .wrap::-webkit-scrollbar-thumb { background: rgba(127,255,212,0.15); border-radius: 3px; }

    table { width:100%; border-collapse:collapse; font-size:11px; }
    th {
      position:sticky; top:0;
      background: var(--hdr-bar); backdrop-filter: blur(8px);
      font-size: 9px; letter-spacing: 1.5px; color: var(--x-muted);
      text-transform: uppercase; padding: 8px 8px;
      border-bottom: 0.5px solid rgba(127,255,212,0.1);
      white-space: nowrap;
    }
    td {
      padding: 7px 8px; color: var(--mint);
      border-bottom: 0.5px solid rgba(127,255,212,0.05);
      white-space: nowrap;
    }
    tr:last-child td { border-bottom: 0; }
    tr:hover td { background: rgba(127,255,212,0.02); }
    td a { color: var(--mint-light); text-decoration: none; border-bottom: 0.5px dotted rgba(170,255,240,0.4); }
    td a:hover { color: var(--mint); }

    .page-footer {
      margin-top: 36px; padding-top: 22px;
      border-top: var(--border);
      text-align: center;
      font-size: 9px; letter-spacing: 3px; color: var(--x-muted);
      text-transform: uppercase;
    }
    .loading { font-size: 11px; color: var(--muted); letter-spacing: 1.5px; padding: 40px; text-align: center; }
  </style>
</head>
<body>
  <canvas id="radar"></canvas>
  <div class="bg-vignette"></div>
  <div class="container" id="container">
    <div class="inner">
      <header class="page-hdr">
        <div class="hdr-row top">
          <span><span class="dot">◉</span> LIVE · ADS-B · HOME RX</span>
          <span id="date">— — —</span>
        </div>
        <div class="hdr-row main">
          <h1 class="title">尾久 SKYLEDGER · TOKYO</h1>
          <span class="clock" id="clock">--:--:--</span>
        </div>
        <div class="hdr-row sub">
          <span class="coords">Powered by connie.hk</span>
          <div class="tools">
            <div class="nav" id="nav"></div>
          </div>
        </div>
      </header>

      <div class="controls">
        <label>{{T_lbl_date}}
          <input type="date" id="day">
        </label>
        <label>{{T_lbl_sort}}
          <select id="sort">
            <option value="last_seen">last_seen</option>
            <option value="country">country</option>
            <option value="operator">operator</option>
            <option value="type">type</option>
          </select>
        </label>
        <label>{{T_lbl_country}}
          <select id="countryFilter">
            <option value="">{{T_lbl_all}}</option>
          </select>
        </label>
        <label>{{T_lbl_operator}}
          <select id="operatorFilter">
            <option value="">{{T_lbl_all}}</option>
          </select>
        </label>
        <label>{{T_lbl_type}}
          <select id="typeFilter">
            <option value="">{{T_lbl_all}}</option>
          </select>
        </label>
        <label>{{T_lbl_from}}
          <select id="fromFilter">
            <option value="">{{T_lbl_all}}</option>
          </select>
        </label>
        <label>{{T_lbl_to}}
          <select id="toFilter">
            <option value="">{{T_lbl_all}}</option>
          </select>
        </label>
        <button id="load">{{T_btn_update}}</button>
      </div>
      <div class="meta" id="meta">{{T_loading}}</div>
      <div class="wrap">
        <table>
          <thead>
            <tr>
              <th>ICAO</th><th>FLIGHT</th><th>FROM</th><th>TO</th><th>OPERATOR</th><th>REG</th><th>TYPE</th><th>COUNTRY</th><th>CAT</th><th>ALT_MIN</th><th>ALT_MAX</th><th>SAMPLES</th><th>FIRST_SEEN</th><th>LAST_SEEN</th>
            </tr>
          </thead>
          <tbody id="rows"></tbody>
        </table>
      </div>
      <footer class="page-footer">尾久 SKYLEDGER · TOKYO<br><span style="color:var(--x-muted);font-size:8px;letter-spacing:2px">Powered by connie.hk</span></footer>
    </div>
  </div>

  <script type="module">
    import * as THREE from 'https://unpkg.com/three@0.160.0/build/three.module.js';

    const T = {{T_JSDICT}};
    const LANG = "{{LANG}}";
    function setLang(l) {
      document.cookie = `lang=${l}; Path=/; Max-Age=31536000; SameSite=Lax`;
      location.reload();
    }
    window.setLang = setLang;

    // ===== Three.js radar =====
    const MINT = 0x7fffd4, AMBER = 0xf5d96f, RING = 0x1f5a4a;
    const canvas = document.getElementById('radar');
    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(45, innerWidth/innerHeight, 0.1, 200);
    camera.position.set(0, 8, 14); camera.lookAt(0, 0, 0);
    const renderer = new THREE.WebGLRenderer({ canvas, alpha: true, antialias: true });
    renderer.setSize(innerWidth, innerHeight);
    renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
    for (const r of [2,4,6,8,10]) {
      const ring = new THREE.Mesh(
        new THREE.RingGeometry(r-0.01, r+0.01, 96),
        new THREE.MeshBasicMaterial({ color: RING, transparent: true, opacity: 0.5, side: THREE.DoubleSide })
      );
      ring.rotation.x = -Math.PI/2; scene.add(ring);
    }
    scene.add(new THREE.LineSegments(
      new THREE.BufferGeometry().setFromPoints([
        new THREE.Vector3(-10,0,0), new THREE.Vector3(10,0,0),
        new THREE.Vector3(0,0,-10), new THREE.Vector3(0,0,10),
      ]),
      new THREE.LineBasicMaterial({ color: RING, transparent: true, opacity: 0.35 })
    ));
    const sweepGroup = new THREE.Group();
    sweepGroup.add(new THREE.Line(
      new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(0,0,0), new THREE.Vector3(10,0,0)]),
      new THREE.LineBasicMaterial({ color: MINT, transparent: true, opacity: 0.7 })
    ));
    const wedge = new THREE.Mesh(
      new THREE.CircleGeometry(10, 48, -Math.PI/4, Math.PI/4),
      new THREE.MeshBasicMaterial({ color: MINT, transparent: true, opacity: 0.08, side: THREE.DoubleSide })
    );
    wedge.rotation.x = -Math.PI/2; sweepGroup.add(wedge); scene.add(sweepGroup);
    const blips = [];
    for (let i = 0; i < 14; i++) {
      const angle = Math.random()*Math.PI*2, dist = 2+Math.random()*8, y = 0.3+Math.random()*2.0;
      const mat = new THREE.MeshBasicMaterial({ color: AMBER, transparent: true, opacity: 0.4 });
      const blip = new THREE.Mesh(new THREE.SphereGeometry(0.12, 12, 12), mat);
      blip.position.set(Math.cos(angle)*dist, y, Math.sin(angle)*dist);
      const trail = new THREE.Line(
        new THREE.BufferGeometry().setFromPoints([blip.position.clone(), blip.position.clone()]),
        new THREE.LineBasicMaterial({ color: AMBER, transparent: true, opacity: 0.25 })
      );
      scene.add(blip); scene.add(trail);
      blips.push({ mesh: blip, trail, angle, dist, y, drift: (Math.random()-0.5)*0.003, prev: blip.position.clone() });
    }
    addEventListener('resize', () => {
      camera.aspect = innerWidth/innerHeight; camera.updateProjectionMatrix();
      renderer.setSize(innerWidth, innerHeight);
    });
    const cont = document.getElementById('container');
    let scrollFactor = 0;
    cont.addEventListener('scroll', () => {
      const max = cont.scrollHeight - cont.clientHeight;
      scrollFactor = max > 0 ? cont.scrollTop / max : 0;
    });
    function lerp(a,b,t) { return a+(b-a)*t; }
    let sweepAngle = 0, running = true, lookYCurrent = 0;
    document.addEventListener('visibilitychange', () => { running = !document.hidden; if (running) animate(); });
    function animate() {
      if (!running) return;
      sweepAngle += 0.012; sweepGroup.rotation.y = sweepAngle;
      const sx = Math.cos(sweepAngle), sz = -Math.sin(sweepAngle);
      blips.forEach(b => {
        b.angle += b.drift; b.prev.copy(b.mesh.position);
        b.mesh.position.x = Math.cos(b.angle)*b.dist;
        b.mesh.position.z = Math.sin(b.angle)*b.dist;
        b.mesh.position.y = b.y;
        b.trail.geometry.setFromPoints([b.prev, b.mesh.position]);
        const mag = Math.hypot(b.mesh.position.x, b.mesh.position.z)||1;
        const dot = (sx*b.mesh.position.x+sz*b.mesh.position.z)/mag;
        const intensity = Math.max(0, dot);
        b.mesh.scale.setScalar(0.4+intensity*0.6);
        b.mesh.material.opacity = 0.25+intensity*0.75;
      });
      camera.position.y = lerp(camera.position.y, lerp(8,5,scrollFactor), 0.06);
      camera.position.z = lerp(camera.position.z, lerp(14,10,scrollFactor), 0.06);
      lookYCurrent = lerp(lookYCurrent, lerp(0,-0.3,scrollFactor), 0.06);
      camera.lookAt(0, lookYCurrent, 0);
      renderer.render(scene, camera);
      requestAnimationFrame(animate);
    }
    animate();

    // ===== Clock / date =====
    function pad(n) { return String(n).padStart(2, '0'); }
    function getJST() { return new Date(Date.now() + 9*3600*1000); }
    function updateClock() {
      const j = getJST();
      document.getElementById('clock').textContent =
        `${pad(j.getUTCHours())}:${pad(j.getUTCMinutes())}:${pad(j.getUTCSeconds())} JPT`;
    }
    function updateDate() {
      const j = getJST();
      const MONTHS = ['JAN','FEB','MAR','APR','MAY','JUN','JUL','AUG','SEP','OCT','NOV','DEC'];
      document.getElementById('date').textContent =
        `${pad(j.getUTCDate())} ${MONTHS[j.getUTCMonth()]} ${j.getUTCFullYear()}`;
    }
    updateClock(); updateDate();
    setInterval(() => { updateClock(); updateDate(); }, 1000);

    // ===== Helpers =====
    function esc(v) { return String(v??'-').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;'); }

    // ===== Data =====
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

    async function load() {
      const qs = new URLSearchParams({ day: day.value, sort: sort.value, country: countryFilter.value, operator: operatorFilter.value, type: typeFilter.value, from: fromFilter.value, to: toFilter.value });
      const res = await fetch('/api/today?' + qs.toString());
      const data = await res.json();
      meta.textContent = T.meta_template
        .replace('{day}', data.day).replace('{count}', data.count).replace('{sort}', data.sort);
      if (countryFilter.options.length <= 1)
        data.countries.forEach(v => countryFilter.insertAdjacentHTML('beforeend', `<option value="${v}">${v}</option>`));
      if (operatorFilter.options.length <= 1)
        data.operators.forEach(v => operatorFilter.insertAdjacentHTML('beforeend', `<option value="${v}">${v}</option>`));
      if (typeFilter.options.length <= 1)
        data.types.forEach(v => typeFilter.insertAdjacentHTML('beforeend', `<option value="${v}">${v}</option>`));
      if (fromFilter.options.length <= 1)
        data.from_airports.forEach(v => fromFilter.insertAdjacentHTML('beforeend', `<option value="${v}">${v}</option>`));
      if (toFilter.options.length <= 1)
        data.to_airports.forEach(v => toFilter.insertAdjacentHTML('beforeend', `<option value="${v}">${v}</option>`));
      rowsEl.innerHTML = data.rows.map(r => `
        <tr>
          <td>${esc(r.icao)}</td>
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
        </tr>`).join('');
    }

    function langSwitchHTML() {
      const labels = { jp: 'JP', hk: 'HK', en: 'EN' };
      return '<span class="lang-switch">' +
        ['jp','hk','en'].map(l =>
          `<a href="#" onclick="setLang('${l}');return false" class="${l===LANG?'on':''}">${labels[l]}</a>`
        ).join('') + '</span>';
    }
    async function renderNav() {
      const nav = document.getElementById('nav');
      const ls = langSwitchHTML();
      try {
        const me = await (await fetch('/api/me')).json();
        if (me.username) {
          nav.innerHTML = ls + `<span style="font-size:10px;letter-spacing:1px;color:var(--muted)">👤 ${esc(me.username)}</span>
            <a href="/account">${esc(T.nav_account)}</a>
            <form method="post" action="/logout"><button type="submit">${esc(T.nav_logout)}</button></form>`;
        } else {
          nav.innerHTML = ls + `<a href="/login">${esc(T.nav_login)}</a>`;
        }
      } catch { nav.innerHTML = ls + `<a href="/login">${esc(T.nav_login)}</a>`; }
    }

    const todayJST = getJST();
    day.value = `${todayJST.getUTCFullYear()}-${pad(todayJST.getUTCMonth()+1)}-${pad(todayJST.getUTCDate())}`;
    loadBtn.addEventListener('click', load);
    sort.addEventListener('change', load);
    day.addEventListener('change', load);
    countryFilter.addEventListener('change', load);
    operatorFilter.addEventListener('change', load);
    typeFilter.addEventListener('change', load);
    fromFilter.addEventListener('change', load);
    toFilter.addEventListener('change', load);
    renderNav();
    load();
  </script>
</body>
</html>
'''


HOME_HTML = '''<!doctype html>
<html lang="{{HTML_LANG}}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{{T_site_title}}</title>
  <link rel="icon" type="image/svg+xml" href="/favicon.svg">
  <style>
    :root {
      --bg: #050a0d;
      --mint: #7fffd4;
      --mint-light: #aafff0;
      --amber: #f5d96f;
      --muted: #4a8a7a;
      --x-muted: #3a6a5a;
      --coral: #ff9966;
      --card: rgba(15,31,34,0.7);
      --card-body: rgba(10,20,22,0.7);
      --hdr-bar: rgba(15,31,34,0.85);
      --border: 0.5px solid rgba(127,255,212,0.15);
      --row-div: 0.5px solid rgba(127,255,212,0.05);
    }
    * { box-sizing: border-box; }
    html, body { margin:0; padding:0; height:100%;
      background: var(--bg); color: var(--mint);
      font-family: 'SF Mono', 'Menlo', 'Courier New', monospace;
      -webkit-font-smoothing: antialiased;
    }
    body { overflow: hidden; }

    #radar { position: fixed; inset:0; z-index:0; width:100vw; height:100vh; }
    .bg-vignette {
      position: fixed; inset:0; z-index:1; pointer-events:none;
      background: radial-gradient(ellipse at center, transparent 35%, rgba(5,10,13,0.85) 95%);
    }

    .container {
      position: relative; z-index: 2;
      height: 100vh; overflow-y: auto; overflow-x: hidden;
      scrollbar-width: thin; scrollbar-color: var(--x-muted) transparent;
    }
    .container::-webkit-scrollbar { width: 6px; }
    .container::-webkit-scrollbar-thumb { background: rgba(127,255,212,0.15); border-radius: 3px; }
    .inner { max-width: 1320px; margin: 0 auto; padding: 24px 32px 60px; }

    /* HEADER */
    header.page-hdr { padding-bottom: 14px; margin-bottom: 18px;
      border-bottom: 1px solid rgba(127,255,212,0.15); }
    .hdr-row { display:flex; align-items:center; justify-content:space-between; gap:16px; }
    .hdr-row.top { font-size:10px; letter-spacing:3px; color: var(--muted); text-transform: uppercase; }
    .hdr-row.top .dot { color: var(--mint); animation: blink 2s infinite; margin-right:4px; }
    @keyframes blink { 50% { opacity: 0.35 } }
    .hdr-row.main { margin: 6px 0 4px; }
    .hdr-row.main .title {
      font-size: 22px; letter-spacing: 1px; color: var(--mint); font-weight: 500; margin: 0;
    }
    .hdr-row.main .clock { font-size: 16px; color: var(--mint); letter-spacing: 1px; }
    .hdr-row.sub { font-size:10px; letter-spacing:2px; color: var(--x-muted); }
    .hdr-row.sub .coords { text-transform: uppercase; }

    .tools { display:flex; gap:6px; align-items:center; }
    .tools input, .tools .nav a, .tools .nav button {
      background: rgba(15,31,34,0.6); color: var(--mint);
      border: var(--border); border-radius: 4px;
      font: inherit; font-size: 10px; letter-spacing: 1.5px;
      padding: 6px 10px; outline: none; cursor: pointer;
      text-decoration: none;
    }
    .tools input { letter-spacing: 0; min-width: 0; }
    .tools input[type="search"] { width: 130px; }
    .tools input[type="date"] { color-scheme: dark; }
    .tools input:focus { border-color: var(--mint); }
    .tools .nav a:hover, .tools .nav button:hover { color: var(--mint); border-color: var(--mint); }
    .nav { display:flex; gap:4px; align-items:center; }
    .nav form { display:inline; margin:0; }
    .lang-switch { display:inline-flex; gap:2px; margin-right:4px; }
    .lang-switch a { padding: 5px 8px; }
    .lang-switch a.on { color: var(--mint); border-color: var(--mint); }

    /* RECENT CONTACTS */
    .recent-contacts { margin-bottom: 14px; }
    .recent-contacts .flight-cols,
    .recent-contacts .flight {
      grid-template-columns: 60px 1fr 80px 70px 50px 110px 2fr 60px;
    }
    .recent-contacts .flight .op-name { color: var(--amber); font-size: 10px; letter-spacing: 0.5px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

    /* STATS */
    .stats { display:grid; grid-template-columns: repeat(4, 1fr); gap:8px; margin-bottom: 22px; }
    .stat {
      background: var(--card); backdrop-filter: blur(8px);
      border: var(--border); border-radius: 4px; padding: 10px 12px;
    }
    .stat .lbl { font-size:9px; letter-spacing:1.5px; color: var(--muted); margin-bottom: 4px; text-transform: uppercase; }
    .stat .val { font-size:20px; font-weight: 500; color: var(--mint); line-height: 1; }
    .stat .val.amber { color: var(--amber); }

    /* GROUPS */
    section.groups {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 14px;
      align-items: start;
    }
    .group {
      opacity: 0; transform: translateY(20px);
      transition: opacity 0.6s ease, transform 0.6s ease;
    }
    .group.in { opacity: 1; transform: translateY(0); }
    .group-hdr {
      background: var(--hdr-bar); backdrop-filter: blur(8px);
      border: var(--border); border-radius: 4px 4px 0 0;
      padding: 10px 14px;
      display: flex; justify-content: space-between; align-items: center;
      cursor: pointer; user-select: none;
      transition: background 0.15s;
    }
    .group-hdr:hover { background: rgba(15,31,34,0.95); }
    .group-hdr .left { display:flex; align-items: baseline; gap: 10px; }
    .group-hdr .op { font-size: 11px; letter-spacing: 2px; color: var(--amber); font-weight: 500; text-transform: uppercase; }
    .group-hdr .op .diamond { color: var(--amber); margin-right: 6px; }
    .group-hdr .country { font-size: 10px; color: var(--x-muted); letter-spacing: 1.5px; }
    .group-hdr .meta { font-size: 10px; color: var(--muted); letter-spacing: 1.5px; display: flex; gap: 16px; text-transform: uppercase; }
    .group.collapsed .group-body { display: none; }
    .group.collapsed .group-hdr { border-radius: 4px; border-bottom: var(--border); }

    .group-body {
      background: var(--card-body); backdrop-filter: blur(8px);
      border: var(--border); border-top: 0;
      border-radius: 0 0 4px 4px;
      padding: 0 14px 4px;
      overflow-x: auto;
    }
    .flight-cols, .flight {
      display: grid;
      grid-template-columns: 60px 80px 70px 50px 110px 1fr 60px;
      gap: 10px; align-items: center;
    }
    .flight-cols {
      font-size: 9px; letter-spacing: 1.5px; color: var(--x-muted);
      padding: 8px 0; border-bottom: 0.5px solid rgba(127,255,212,0.1);
      text-transform: uppercase;
    }
    .flight {
      font-size: 11px; padding: 7px 0;
      border-bottom: var(--row-div);
      border-left: 2px solid transparent;
      padding-left: 8px; margin-left: -10px;
      transition: border-color 0.15s, background 0.15s;
    }
    .flight:last-child { border-bottom: 0; }
    .flight:hover { border-left-color: var(--mint); background: rgba(127,255,212,0.02); }
    .flight .icao { color: var(--muted); }
    .flight .flight-no { color: var(--amber); font-weight: 500; }
    .flight .reg { color: var(--mint-light); }
    .flight .type { color: var(--mint); }
    .flight .route { color: var(--mint-light); display:flex; align-items:center; gap:6px; }
    .flight .route .arrow { color: var(--x-muted); }
    .flight .alt { display:flex; align-items:center; gap:8px; }
    .flight .alt .bar { flex:1; height: 3px; border-radius: 2px;
      background: rgba(127,255,212,0.08); position: relative; overflow: hidden; }
    .flight .alt .bar div { position:absolute; left:0; top:0; bottom:0; border-radius: 2px; }
    .flight .alt .alt-label { width: 32px; text-align: right; font-size: 11px; }
    .flight .last { color: var(--muted); font-size: 10px; text-align: right; }
    .flight.hidden { display: none; }

    .reg a { color: inherit; text-decoration: none; border-bottom: 0.5px dotted rgba(170,255,240,0.4); }
    .reg a:hover { color: var(--mint); }

    .page-footer {
      margin-top: 36px; padding-top: 22px;
      border-top: var(--border);
      text-align: center;
      font-size: 9px; letter-spacing: 3px; color: var(--x-muted);
      text-transform: uppercase;
    }
    .loading, .empty {
      font-size: 11px; color: var(--muted); letter-spacing: 1.5px;
      text-align: center; padding: 40px;
    }
    @media (max-width: 700px) {
      section.groups { grid-template-columns: 1fr; }
      .stats { grid-template-columns: repeat(2, 1fr); }
      .recent-contacts .flight-cols,
      .recent-contacts .flight { grid-template-columns: 55px 1fr 65px 55px; gap: 6px; }
      .recent-contacts .flight-cols div:nth-child(n+5),
      .recent-contacts .flight > div:nth-child(n+5) { display: none; }
      section.groups .group-body { padding: 0 10px 4px; }
      section.groups .flight-cols,
      section.groups .flight { grid-template-columns: 55px 1fr 65px 70px; gap: 6px; }
      section.groups .flight { padding-left: 6px; margin-left: -8px; }
      section.groups .flight-cols > div:nth-child(4),
      section.groups .flight-cols > div:nth-child(6),
      section.groups .flight-cols > div:nth-child(7),
      section.groups .flight > div:nth-child(4),
      section.groups .flight > div:nth-child(6),
      section.groups .flight > div:nth-child(7) { display: none; }
      .hdr-row { gap: 8px; }
      .hdr-row.top { font-size: 9px; letter-spacing: 1.5px; }
      .hdr-row.main { flex-wrap: wrap; }
      .hdr-row.main .title { font-size: 16px; letter-spacing: 0.5px; }
      .hdr-row.main .clock { font-size: 13px; }
      .hdr-row.sub .coords { display: none; }
      .tools .nav > span:not(.lang-switch) { display: none; }
      .hdr-row.sub { justify-content: flex-end; }
      .tools { justify-content: flex-end; gap: 4px; flex-wrap: wrap; }
      .tools input[type="search"] { width: 110px; flex: 0 1 auto; }
      .tools input[type="date"] { flex: 0 1 auto; }
      .tools .nav { justify-content: flex-end; gap: 4px; flex: 0 0 auto; }
      .tools .nav a, .tools .nav button { padding: 5px 8px; font-size: 10px; letter-spacing: 1px; }
      .inner { position: relative; padding-top: 44px; }
      .lang-switch {
        position: absolute; top: 12px; right: 28px; z-index: 5;
        margin: 0; gap: 4px;
        background: rgba(5,10,13,0.85); padding: 4px;
        border-radius: 4px;
      }
      .lang-switch a { padding: 5px 8px; font-size: 10px; }
      .group-hdr { align-items: flex-start; gap: 10px; }
      .group-hdr .left { flex-direction: column; align-items: flex-start; gap: 3px; min-width: 0; flex: 1; }
      .group-hdr .left .op { white-space: normal; word-break: break-word; line-height: 1.3; }
    }
  </style>
</head>
<body>
  <canvas id="radar"></canvas>
  <div class="bg-vignette"></div>

  <div class="container" id="container">
    <div class="inner">
      <header class="page-hdr">
        <div class="hdr-row top">
          <span><span class="dot">◉</span> LIVE · ADS-B · HOME RX</span>
          <span id="date">— — —</span>
        </div>
        <div class="hdr-row main">
          <h1 class="title">尾久 SKYLEDGER · TOKYO</h1>
          <span class="clock" id="clock">--:--:--</span>
        </div>
        <div class="hdr-row sub">
          <span class="coords">Powered by connie.hk</span>
          <div class="tools">
            <input type="search" id="search" placeholder="{{T_search_placeholder}}" autocomplete="off">
            <input type="date" id="datePicker">
            <div class="nav" id="nav"></div>
          </div>
        </div>
      </header>

      <section class="recent-contacts">
        <div class="group">
          <div class="group-hdr">
            <div class="left">
              <span class="op"><span class="dot" style="margin-right:6px">◉</span>RECENT CONTACTS</span>
            </div>
            <div class="meta"><span id="rc-count">—</span></div>
          </div>
          <div class="group-body">
            <div class="flight-cols">
              <div>ICAO</div><div>OPERATOR</div><div>FLIGHT</div><div>REG</div><div>TYPE</div><div>ROUTE</div><div>ALTITUDE</div><div>LAST</div>
            </div>
            <div id="rc-grid"></div>
          </div>
        </div>
      </section>

      <section class="stats">
        <div class="stat"><div class="lbl">TODAY</div><div class="val" id="s-today">—</div></div>
        <div class="stat"><div class="lbl">OPERATORS</div><div class="val" id="s-ops">—</div></div>
        <div class="stat"><div class="lbl">PEAK ALT</div><div class="val amber" id="s-peak">—</div></div>
        <div class="stat"><div class="lbl">ROUTES</div><div class="val" id="s-routes">—</div></div>
      </section>

      <section class="groups" id="groups">
        <div class="loading">{{T_loading}}</div>
      </section>

      <footer class="page-footer">尾久 SKYLEDGER · TOKYO<br><span style="color:var(--x-muted);font-size:8px;letter-spacing:2px">Powered by connie.hk</span></footer>
    </div>
  </div>

  <script type="module">
    import * as THREE from 'https://unpkg.com/three@0.160.0/build/three.module.js';

    const T = {{T_JSDICT}};
    const LANG = "{{LANG}}";
    function setLang(l) {
      document.cookie = `lang=${l}; Path=/; Max-Age=31536000; SameSite=Lax`;
      location.reload();
    }
    window.setLang = setLang;

    const MINT = 0x7fffd4;
    const AMBER = 0xf5d96f;
    const RING = 0x1f5a4a;

    // ===== Three.js radar =====
    const canvas = document.getElementById('radar');
    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(45, innerWidth/innerHeight, 0.1, 200);
    camera.position.set(0, 8, 14);
    camera.lookAt(0, 0, 0);
    const renderer = new THREE.WebGLRenderer({ canvas, alpha: true, antialias: true });
    renderer.setSize(innerWidth, innerHeight);
    renderer.setPixelRatio(Math.min(devicePixelRatio, 2));

    // Rings
    for (const r of [2, 4, 6, 8, 10]) {
      const ring = new THREE.Mesh(
        new THREE.RingGeometry(r - 0.01, r + 0.01, 96),
        new THREE.MeshBasicMaterial({ color: RING, transparent: true, opacity: 0.5, side: THREE.DoubleSide })
      );
      ring.rotation.x = -Math.PI / 2;
      scene.add(ring);
    }

    // Crosshair
    scene.add(new THREE.LineSegments(
      new THREE.BufferGeometry().setFromPoints([
        new THREE.Vector3(-10,0,0), new THREE.Vector3(10,0,0),
        new THREE.Vector3(0,0,-10), new THREE.Vector3(0,0,10),
      ]),
      new THREE.LineBasicMaterial({ color: RING, transparent: true, opacity: 0.35 })
    ));

    // Sweep group (line + wedge)
    const sweepGroup = new THREE.Group();
    const sweepLine = new THREE.Line(
      new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(0,0,0), new THREE.Vector3(10,0,0)]),
      new THREE.LineBasicMaterial({ color: MINT, transparent: true, opacity: 0.7 })
    );
    sweepGroup.add(sweepLine);
    const wedge = new THREE.Mesh(
      new THREE.CircleGeometry(10, 48, -Math.PI/4, Math.PI/4),
      new THREE.MeshBasicMaterial({ color: MINT, transparent: true, opacity: 0.08, side: THREE.DoubleSide })
    );
    wedge.rotation.x = -Math.PI / 2;
    sweepGroup.add(wedge);
    scene.add(sweepGroup);

    // Blips
    const blips = [];
    for (let i = 0; i < 14; i++) {
      const angle = Math.random() * Math.PI * 2;
      const dist = 2 + Math.random() * 8;
      const y = 0.3 + Math.random() * 2.0;
      const mat = new THREE.MeshBasicMaterial({ color: AMBER, transparent: true, opacity: 0.4 });
      const blip = new THREE.Mesh(new THREE.SphereGeometry(0.12, 12, 12), mat);
      blip.position.set(Math.cos(angle)*dist, y, Math.sin(angle)*dist);
      const trailGeom = new THREE.BufferGeometry().setFromPoints([blip.position.clone(), blip.position.clone()]);
      const trail = new THREE.Line(trailGeom, new THREE.LineBasicMaterial({ color: AMBER, transparent: true, opacity: 0.25 }));
      scene.add(blip); scene.add(trail);
      blips.push({ mesh: blip, trail, angle, dist, y, drift: (Math.random() - 0.5) * 0.003, prev: blip.position.clone() });
    }

    addEventListener('resize', () => {
      camera.aspect = innerWidth/innerHeight;
      camera.updateProjectionMatrix();
      renderer.setSize(innerWidth, innerHeight);
    });

    // Scroll-driven camera lerp
    const container = document.getElementById('container');
    let scrollFactor = 0;
    container.addEventListener('scroll', () => {
      const max = container.scrollHeight - container.clientHeight;
      scrollFactor = max > 0 ? container.scrollTop / max : 0;
    });

    function lerp(a, b, t) { return a + (b - a) * t; }

    let sweepAngle = 0;
    let running = true;
    let lookYCurrent = 0;
    document.addEventListener('visibilitychange', () => {
      running = !document.hidden;
      if (running) animate();
    });

    function animate() {
      if (!running) return;
      sweepAngle += 0.012;
      sweepGroup.rotation.y = sweepAngle;

      // Blip motion + pulse
      const sx = Math.cos(sweepAngle), sz = -Math.sin(sweepAngle);
      blips.forEach(b => {
        b.angle += b.drift;
        b.prev.copy(b.mesh.position);
        b.mesh.position.x = Math.cos(b.angle) * b.dist;
        b.mesh.position.z = Math.sin(b.angle) * b.dist;
        b.mesh.position.y = b.y;
        b.trail.geometry.setFromPoints([b.prev, b.mesh.position]);
        const mag = Math.hypot(b.mesh.position.x, b.mesh.position.z) || 1;
        const dot = (sx * b.mesh.position.x + sz * b.mesh.position.z) / mag;
        const intensity = Math.max(0, dot);
        const scale = 0.4 + intensity * 0.6;
        b.mesh.scale.setScalar(scale);
        b.mesh.material.opacity = 0.25 + intensity * 0.75;
      });

      // Camera lerp
      const targetY = lerp(8, 5, scrollFactor);
      const targetZ = lerp(14, 10, scrollFactor);
      const targetLookY = lerp(0, -0.3, scrollFactor);
      camera.position.y = lerp(camera.position.y, targetY, 0.06);
      camera.position.z = lerp(camera.position.z, targetZ, 0.06);
      lookYCurrent = lerp(lookYCurrent, targetLookY, 0.06);
      camera.lookAt(0, lookYCurrent, 0);

      renderer.render(scene, camera);
      requestAnimationFrame(animate);
    }
    animate();

    // ===== Clock / date =====
    function pad(n) { return String(n).padStart(2, '0'); }
    function getJST() {
      const now = new Date();
      return new Date(now.getTime() + 9 * 3600 * 1000);
    }
    function updateClock() {
      const j = getJST();
      document.getElementById('clock').textContent =
        `${pad(j.getUTCHours())}:${pad(j.getUTCMinutes())}:${pad(j.getUTCSeconds())} JPT`;
    }
    function updateDate() {
      const j = getJST();
      const MONTHS = ['JAN','FEB','MAR','APR','MAY','JUN','JUL','AUG','SEP','OCT','NOV','DEC'];
      document.getElementById('date').textContent =
        `${pad(j.getUTCDate())} ${MONTHS[j.getUTCMonth()]} ${j.getUTCFullYear()}`;
    }
    updateClock(); updateDate();
    setInterval(() => { updateClock(); updateDate(); }, 1000);

    // ===== Helpers =====
    function esc(v) { return String(v ?? '').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;'); }
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
      return Math.round(Number(ft) / 1000) + 'k';
    }
    function lastTime(jstStr) {
      if (!jstStr || jstStr === '-') return '—';
      const m = jstStr.match(/\d{4}-\d{2}-\d{2} (\d{2}:\d{2}:\d{2})/);
      return m ? m[1] : jstStr;
    }
    function n(v) { return (v === '-' || v == null) ? null : v; }

    // ===== Nav (lang switch + login state) =====
    function langSwitchHTML() {
      const labels = { jp: 'JP', hk: 'HK', en: 'EN' };
      return '<span class="lang-switch">' +
        ['jp','hk','en'].map(l =>
          `<a href="#" onclick="setLang('${l}');return false" class="${l===LANG?'on':''}">${labels[l]}</a>`
        ).join('') + '</span>';
    }
    async function renderNav() {
      const nav = document.getElementById('nav');
      const ls = langSwitchHTML();
      try {
        const me = await (await fetch('/api/me')).json();
        if (me.username) {
          nav.innerHTML = ls + `<a href="/details">${esc(T.nav_details)}</a><a href="/account">${esc(me.username)}</a>` +
            `<form method="post" action="/logout"><button type="submit">${esc(T.nav_logout)}</button></form>`;
        } else {
          nav.innerHTML = ls + `<a href="/details">${esc(T.nav_details)}</a><a href="/login">${esc(T.nav_login)}</a>`;
        }
      } catch { nav.innerHTML = ls + `<a href="/details">${esc(T.nav_details)}</a>`; }
    }
    renderNav();

    // ===== Date picker =====
    const todayStr = (() => {
      const j = getJST();
      return `${j.getUTCFullYear()}-${pad(j.getUTCMonth()+1)}-${pad(j.getUTCDate())}`;
    })();
    const datePicker = document.getElementById('datePicker');
    datePicker.value = todayStr;
    let currentDay = todayStr;
    datePicker.addEventListener('change', () => {
      currentDay = datePicker.value || todayStr;
      load();
    });

    // ===== Search =====
    const searchInput = document.getElementById('search');
    addEventListener('keydown', (e) => {
      if (e.key === '/' && document.activeElement !== searchInput
          && !['INPUT','TEXTAREA'].includes(document.activeElement?.tagName)) {
        e.preventDefault();
        searchInput.focus();
      } else if (e.key === 'Escape' && document.activeElement === searchInput) {
        searchInput.value = ''; applyFilter(); searchInput.blur();
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
        const visible = g.querySelectorAll('.flight:not(.hidden)').length > 0;
        g.style.display = (q && !visible) ? 'none' : '';
      });
    }

    // ===== Collapse =====
    document.addEventListener('click', (e) => {
      const hdr = e.target.closest('.group-hdr');
      if (hdr) hdr.parentElement.classList.toggle('collapsed');
    });

    // ===== Load + render =====
    async function load() {
      document.getElementById('groups').innerHTML = `<div class="loading">${esc(T.loading)}</div>`;
      const res = await fetch(`/api/today?day=${currentDay}`);
      const data = await res.json();
      render(data);
    }

    function render(data) {
      // Stats
      document.getElementById('s-today').textContent = data.count;
      document.getElementById('s-ops').textContent = data.operators.length;
      let peakAlt = 0;
      for (const r of data.rows) {
        const v = n(r.max_alt_baro);
        if (v != null && Number(v) > peakAlt) peakAlt = Number(v);
      }
      document.getElementById('s-peak').textContent = peakAlt ? Math.round(peakAlt / 1000) + 'k' : '—';
      const routes = new Set();
      for (const r of data.rows) {
        if (r.from_airport !== '-' && r.to_airport !== '-')
          routes.add(r.from_airport + '→' + r.to_airport);
      }
      document.getElementById('s-routes').textContent = routes.size;

      // Recent contacts (latest 8 by last_seen)
      const rcGrid = document.getElementById('rc-grid');
      const recent = data.rows.slice(0, 8);
      document.getElementById('rc-count').textContent = recent.length + ' TRACKS';
      rcGrid.innerHTML = recent.map(f => {
        const altMax = n(f.max_alt_baro);
        const altPct = altMax != null ? Math.min(100, Number(altMax) / 45000 * 100) : 0;
        const altC = altColor(altMax);
        const altLbl = altLabel(altMax);
        const fromC = airportCode(f.from_airport);
        const toC = airportCode(f.to_airport);
        const regCell = f.registration !== '-'
          ? `<a href="https://www.flightradar24.com/data/aircraft/${encodeURIComponent(String(f.registration).toLowerCase())}" target="_blank" rel="noreferrer">${esc(f.registration)}</a>`
          : '—';
        return `
        <div class="flight">
          <div class="icao">${esc(f.icao)}</div>
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
        if (!groups.has(op)) groups.set(op, { operator: op, country: r.country, flights: [], samples: 0 });
        const g = groups.get(op);
        g.flights.push(r);
        g.samples += Number(r.samples || 0);
        if (r.country !== '-' && (g.country === '-' || !g.country)) g.country = r.country;
      }
      const sorted = [...groups.values()].sort((a, b) => b.flights.length - a.flights.length);

      const root = document.getElementById('groups');
      if (!sorted.length) {
        root.innerHTML = `<div class="empty">${esc(T.no_data)}</div>`;
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
            ${g.flights.slice(0, 10).map(f => {
              const altMax = n(f.max_alt_baro);
              const altPct = altMax != null ? Math.min(100, Number(altMax) / 45000 * 100) : 0;
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
              <div class="flight" data-search="${esc(hay)}" title="${esc(tip)}">
                <div class="icao">${esc(f.icao)}</div>
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
            }).join('')}
          </div>
        </div>
      `).join('');

      // Cascading reveal
      const io = new IntersectionObserver(entries => {
        entries.forEach(e => {
          if (e.isIntersecting) { e.target.classList.add('in'); io.unobserve(e.target); }
        });
      }, { root: container, threshold: 0.15 });
      document.querySelectorAll('.group').forEach(el => io.observe(el));
    }
    load();
  </script>
</body>
</html>
'''


def fmt_ts(ts):
    if not ts:
        return '-'
    dt = datetime.fromisoformat(ts)
    return dt.astimezone(JST).strftime('%Y-%m-%d %H:%M:%S JST')


def jst_day_utc_bounds(day_str):
    # JST day [00:00, 24:00) 對應 UTC (day-1) 15:00:00 至 day 15:00:00。
    # seen_at 存 ISO UTC 字串（e.g. "2026-05-27T09:34:18.100311+00:00"），可以做字串範圍比較。
    d = date.fromisoformat(day_str)
    start = (datetime.combine(d, datetime.min.time()) - timedelta(hours=9)).strftime('%Y-%m-%dT%H:%M:%S+00:00')
    end = (datetime.combine(d, datetime.min.time()) + timedelta(hours=15)).strftime('%Y-%m-%dT%H:%M:%S+00:00')
    return start, end


def query_rows(day_str, sort_key, country_filter='', operator_filter='', type_filter='',
               from_filter='', to_filter=''):
    order_by = ALLOWED_SORTS.get(sort_key, ALLOWED_SORTS['last_seen'])
    start_utc, end_utc = jst_day_utc_bounds(day_str)
    conn = connect()
    cur = dict_cursor(conn)
    conditions = ["s.seen_at >= %s", "s.seen_at < %s"]
    params = [start_utc, end_utc]
    if country_filter:
        conditions.append("COALESCE(NULLIF(TRIM(c.country), ''), '-') = %s")
        params.append(country_filter)
    if operator_filter:
        conditions.append("COALESCE(NULLIF(TRIM(c.operator), ''), '-') = %s")
        params.append(operator_filter)
    if type_filter:
        conditions.append("COALESCE(NULLIF(TRIM(c.aircraft_type), ''), '-') = %s")
        params.append(type_filter)
    if from_filter:
        conditions.append("COALESCE(NULLIF(TRIM(c.from_airport), ''), '-') = %s")
        params.append(from_filter)
    if to_filter:
        conditions.append("COALESCE(NULLIF(TRIM(c.to_airport), ''), '-') = %s")
        params.append(to_filter)
    where_clause = ' AND '.join(conditions)
    cur.execute(
        f'''
        SELECT
          s.icao,
          COALESCE(MAX(NULLIF(TRIM(s.flight), '')), '') AS flight,
          COALESCE(MAX(NULLIF(TRIM(s.category), '')), '') AS category,
          COALESCE(MAX(NULLIF(TRIM(c.registration), '')), '') AS registration,
          COALESCE(MAX(NULLIF(TRIM(c.country), '')), '') AS country,
          COALESCE(MAX(NULLIF(TRIM(c.operator), '')), '') AS operator,
          COALESCE(MAX(NULLIF(TRIM(c.aircraft_type), '')), '') AS aircraft_type,
          COALESCE(MAX(NULLIF(TRIM(c.from_airport), '')), '') AS from_airport,
          COALESCE(MAX(NULLIF(TRIM(c.to_airport), '')), '') AS to_airport,
          MIN(s.seen_at) AS first_seen,
          MAX(s.seen_at) AS last_seen,
          MIN(CASE WHEN s.alt_baro IS NOT NULL THEN s.alt_baro END) AS min_alt_baro,
          MAX(CASE WHEN s.alt_baro IS NOT NULL THEN s.alt_baro END) AS max_alt_baro,
          COUNT(*) AS samples
        FROM sightings_raw s
        LEFT JOIN aircraft_registry_cache c ON c.icao = s.icao
        WHERE {where_clause}
        GROUP BY s.icao
        ORDER BY {order_by}
        ''',
        params
    )
    rows = []
    for r in cur.fetchall():
        rows.append({
            'icao': r['icao'],
            'flight': r['flight'] or '-',
            'operator': r['operator'] or '-',
            'registration': r['registration'] or '-',
            'country': r['country'] or '-',
            'aircraft_type': r['aircraft_type'] or '-',
            'from_airport': r['from_airport'] or '-',
            'to_airport': r['to_airport'] or '-',
            'category': r['category'] or '-',
            'min_alt_baro': int(r['min_alt_baro']) if r['min_alt_baro'] is not None else '-',
            'max_alt_baro': int(r['max_alt_baro']) if r['max_alt_baro'] is not None else '-',
            'samples': r['samples'],
            'first_seen_jst': fmt_ts(r['first_seen']),
            'last_seen_jst': fmt_ts(r['last_seen']),
        })
    conn.close()
    return rows


def query_summary(day_str):
    start_utc, end_utc = jst_day_utc_bounds(day_str)
    conn = connect()
    cur = dict_cursor(conn)
    cur.execute(
        '''
        SELECT
          COALESCE(NULLIF(TRIM(c.operator), ''), '(unknown)') AS operator,
          COALESCE(NULLIF(TRIM(c.operator_country), ''), '') AS country,
          COUNT(DISTINCT s.icao) AS cnt
        FROM sightings_raw s
        LEFT JOIN aircraft_registry_cache c ON c.icao = s.icao
        WHERE s.seen_at >= %s AND s.seen_at < %s
        GROUP BY
          COALESCE(NULLIF(TRIM(c.operator), ''), '(unknown)'),
          COALESCE(NULLIF(TRIM(c.operator_country), ''), '')
        ORDER BY cnt DESC, operator ASC
        ''',
        (start_utc, end_utc),
    )
    operators = [
        {'operator': r['operator'], 'country': r['country'], 'count': r['cnt']}
        for r in cur.fetchall()
    ]
    cur.execute(
        'SELECT COUNT(DISTINCT icao) AS t FROM sightings_raw WHERE seen_at >= %s AND seen_at < %s',
        (start_utc, end_utc),
    )
    total = cur.fetchone()['t']
    conn.close()
    return {
        'day': day_str,
        'total_aircraft': total,
        'operators': operators,
    }


_AUTH_LANG_SWITCH = '''<div class="lang-switch">
  <a href="#" onclick="setLang('jp');return false" class="{CL_JP}">JP</a>
  <a href="#" onclick="setLang('hk');return false" class="{CL_HK}">HK</a>
  <a href="#" onclick="setLang('en');return false" class="{CL_EN}">EN</a>
</div>
<script>
function setLang(l) {
  document.cookie = `lang=${l}; Path=/; Max-Age=31536000; SameSite=Lax`;
  location.reload();
}
</script>'''


LOGIN_PAGE = '''<!doctype html>
<html lang="{{HTML_LANG}}"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{{T_login_title}}</title>
<link rel="icon" type="image/svg+xml" href="/favicon.svg">
<style>
  :root { --bg:#050a0d; --mint:#7fffd4; --mint-light:#aafff0; --amber:#f5d96f; --muted:#4a8a7a; --x-muted:#3a6a5a; --card:rgba(15,31,34,0.85); --border:0.5px solid rgba(127,255,212,0.15); }
  *{ box-sizing:border-box; }
  html,body { margin:0; padding:0; height:100%; background:var(--bg); color:var(--mint); font-family:'SF Mono','Menlo','Courier New',monospace; -webkit-font-smoothing:antialiased; overflow:hidden; }
  #radar { position:fixed; inset:0; z-index:0; width:100vw; height:100vh; }
  .bg-vignette { position:fixed; inset:0; z-index:1; pointer-events:none; background:radial-gradient(ellipse at center, transparent 35%, rgba(5,10,13,0.85) 95%); }
  .wrap { position:relative; z-index:2; display:flex; flex-direction:column; min-height:100vh; align-items:center; justify-content:center; }
  .lang-switch { position:fixed; top:16px; right:16px; display:flex; gap:4px; z-index:3; }
  .lang-switch a { color:var(--muted); text-decoration:none; font-size:10px; padding:5px 8px; border:var(--border); border-radius:4px; letter-spacing:0.1em; background:rgba(15,31,34,0.6); }
  .lang-switch a.on { color:var(--mint); border-color:var(--mint); }
  .card { background:var(--card); backdrop-filter:blur(12px); border:var(--border); border-radius:4px; padding:32px 36px; width:320px; }
  .card-top { font-size:9px; letter-spacing:3px; color:var(--muted); text-transform:uppercase; margin-bottom:20px; }
  .card-top .dot { color:var(--mint); animation:blink 2s infinite; margin-right:4px; }
  @keyframes blink { 50%{opacity:0.35} }
  h1 { margin:0 0 24px; font-size:16px; letter-spacing:1px; color:var(--mint); font-weight:500; }
  label { display:block; margin-bottom:14px; font-size:9px; letter-spacing:1.5px; color:var(--muted); text-transform:uppercase; }
  input { display:block; width:100%; margin-top:5px; padding:8px 10px; background:rgba(5,10,13,0.8); color:var(--mint); border:var(--border); border-radius:4px; font:inherit; font-size:12px; outline:none; }
  input:focus { border-color:var(--mint); }
  button[type=submit] { width:100%; margin-top:8px; padding:9px; background:rgba(127,255,212,0.08); color:var(--mint); border:var(--border); border-radius:4px; font:inherit; font-size:10px; letter-spacing:2px; text-transform:uppercase; cursor:pointer; }
  button[type=submit]:hover { background:rgba(127,255,212,0.16); }
  .err { font-size:10px; letter-spacing:1px; color:#ff9966; margin-bottom:12px; }
  .back { display:block; text-align:center; margin-top:16px; color:var(--x-muted); font-size:10px; letter-spacing:1.5px; text-decoration:none; text-transform:uppercase; }
  .back:hover { color:var(--mint); }
</style></head>
<body>
<canvas id="radar"></canvas>
<div class="bg-vignette"></div>
<div class="wrap">
  {LANG_SWITCH}
  <div class="card">
    <div class="card-top"><span class="dot">◉</span> 尾久 SKYLEDGER</div>
    <h1>{{T_login_heading}}</h1>
    {ERR}
    <form method="post" action="/login">
      <input type="hidden" name="next" value="{NEXT}">
      <label>{{T_lbl_username}}<input name="username" autocomplete="username" required autofocus></label>
      <label>{{T_lbl_password}}<input name="password" type="password" autocomplete="current-password" required></label>
      <button type="submit">{{T_btn_login}}</button>
    </form>
    <a class="back" href="/">{{T_link_back_home}}</a>
  </div>
</div>
<script type="module">
  import * as THREE from 'https://unpkg.com/three@0.160.0/build/three.module.js';
  const MINT=0x7fffd4,AMBER=0xf5d96f,RING=0x1f5a4a;
  const canvas=document.getElementById('radar');
  const scene=new THREE.Scene();
  const camera=new THREE.PerspectiveCamera(45,innerWidth/innerHeight,0.1,200);
  camera.position.set(0,8,14); camera.lookAt(0,0,0);
  const renderer=new THREE.WebGLRenderer({canvas,alpha:true,antialias:true});
  renderer.setSize(innerWidth,innerHeight); renderer.setPixelRatio(Math.min(devicePixelRatio,2));
  for(const r of[2,4,6,8,10]){const ring=new THREE.Mesh(new THREE.RingGeometry(r-.01,r+.01,96),new THREE.MeshBasicMaterial({color:RING,transparent:true,opacity:.5,side:THREE.DoubleSide}));ring.rotation.x=-Math.PI/2;scene.add(ring);}
  scene.add(new THREE.LineSegments(new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(-10,0,0),new THREE.Vector3(10,0,0),new THREE.Vector3(0,0,-10),new THREE.Vector3(0,0,10)]),new THREE.LineBasicMaterial({color:RING,transparent:true,opacity:.35})));
  const sg=new THREE.Group();
  sg.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(0,0,0),new THREE.Vector3(10,0,0)]),new THREE.LineBasicMaterial({color:MINT,transparent:true,opacity:.7})));
  const w=new THREE.Mesh(new THREE.CircleGeometry(10,48,-Math.PI/4,Math.PI/4),new THREE.MeshBasicMaterial({color:MINT,transparent:true,opacity:.08,side:THREE.DoubleSide}));w.rotation.x=-Math.PI/2;sg.add(w);scene.add(sg);
  const blips=[];
  for(let i=0;i<14;i++){const a=Math.random()*Math.PI*2,d=2+Math.random()*8,y=.3+Math.random()*2;const mat=new THREE.MeshBasicMaterial({color:AMBER,transparent:true,opacity:.4});const b=new THREE.Mesh(new THREE.SphereGeometry(.12,12,12),mat);b.position.set(Math.cos(a)*d,y,Math.sin(a)*d);const tr=new THREE.Line(new THREE.BufferGeometry().setFromPoints([b.position.clone(),b.position.clone()]),new THREE.LineBasicMaterial({color:AMBER,transparent:true,opacity:.25}));scene.add(b);scene.add(tr);blips.push({mesh:b,trail:tr,angle:a,dist:d,y,drift:(Math.random()-.5)*.003,prev:b.position.clone()});}
  addEventListener('resize',()=>{camera.aspect=innerWidth/innerHeight;camera.updateProjectionMatrix();renderer.setSize(innerWidth,innerHeight);});
  let sa=0,run=true;
  document.addEventListener('visibilitychange',()=>{run=!document.hidden;if(run)go();});
  function go(){if(!run)return;sa+=.012;sg.rotation.y=sa;const sx=Math.cos(sa),sz=-Math.sin(sa);blips.forEach(b=>{b.angle+=b.drift;b.prev.copy(b.mesh.position);b.mesh.position.x=Math.cos(b.angle)*b.dist;b.mesh.position.z=Math.sin(b.angle)*b.dist;b.mesh.position.y=b.y;b.trail.geometry.setFromPoints([b.prev,b.mesh.position]);const mag=Math.hypot(b.mesh.position.x,b.mesh.position.z)||1;const dot=(sx*b.mesh.position.x+sz*b.mesh.position.z)/mag;const i=Math.max(0,dot);b.mesh.scale.setScalar(.4+i*.6);b.mesh.material.opacity=.25+i*.75;});renderer.render(scene,camera);requestAnimationFrame(go);}
  go();
</script>
</body></html>'''


ACCOUNT_PAGE = '''<!doctype html>
<html lang="{{HTML_LANG}}"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{{T_account_title}}</title>
<link rel="icon" type="image/svg+xml" href="/favicon.svg">
<style>
  :root { --bg:#050a0d; --mint:#7fffd4; --mint-light:#aafff0; --amber:#f5d96f; --muted:#4a8a7a; --x-muted:#3a6a5a; --card:rgba(15,31,34,0.85); --border:0.5px solid rgba(127,255,212,0.15); }
  *{ box-sizing:border-box; }
  html,body { margin:0; padding:0; height:100%; background:var(--bg); color:var(--mint); font-family:'SF Mono','Menlo','Courier New',monospace; -webkit-font-smoothing:antialiased; overflow:hidden; }
  #radar { position:fixed; inset:0; z-index:0; width:100vw; height:100vh; }
  .bg-vignette { position:fixed; inset:0; z-index:1; pointer-events:none; background:radial-gradient(ellipse at center, transparent 35%, rgba(5,10,13,0.85) 95%); }
  .wrap { position:relative; z-index:2; display:flex; flex-direction:column; min-height:100vh; align-items:center; justify-content:center; }
  .lang-switch { position:fixed; top:16px; right:16px; display:flex; gap:4px; z-index:3; }
  .lang-switch a { color:var(--muted); text-decoration:none; font-size:10px; padding:5px 8px; border:var(--border); border-radius:4px; letter-spacing:0.1em; background:rgba(15,31,34,0.6); }
  .lang-switch a.on { color:var(--mint); border-color:var(--mint); }
  .card { background:var(--card); backdrop-filter:blur(12px); border:var(--border); border-radius:4px; padding:32px 36px; width:340px; }
  .card-top { font-size:9px; letter-spacing:3px; color:var(--muted); text-transform:uppercase; margin-bottom:20px; }
  .card-top .dot { color:var(--mint); animation:blink 2s infinite; margin-right:4px; }
  @keyframes blink { 50%{opacity:0.35} }
  h1 { margin:0 0 6px; font-size:16px; letter-spacing:1px; color:var(--mint); font-weight:500; }
  .who { font-size:10px; letter-spacing:1px; color:var(--muted); margin-bottom:20px; }
  label { display:block; margin-bottom:14px; font-size:9px; letter-spacing:1.5px; color:var(--muted); text-transform:uppercase; }
  input { display:block; width:100%; margin-top:5px; padding:8px 10px; background:rgba(5,10,13,0.8); color:var(--mint); border:var(--border); border-radius:4px; font:inherit; font-size:12px; outline:none; }
  input:focus { border-color:var(--mint); }
  button[type=submit] { width:100%; margin-top:8px; padding:9px; background:rgba(127,255,212,0.08); color:var(--mint); border:var(--border); border-radius:4px; font:inherit; font-size:10px; letter-spacing:2px; text-transform:uppercase; cursor:pointer; }
  button[type=submit]:hover { background:rgba(127,255,212,0.16); }
  .err { font-size:10px; letter-spacing:1px; color:#ff9966; margin-bottom:12px; }
  .ok  { font-size:10px; letter-spacing:1px; color:var(--mint-light); margin-bottom:12px; }
  .back { display:block; text-align:center; margin-top:16px; color:var(--x-muted); font-size:10px; letter-spacing:1.5px; text-decoration:none; text-transform:uppercase; }
  .back:hover { color:var(--mint); }
</style></head>
<body>
<canvas id="radar"></canvas>
<div class="bg-vignette"></div>
<div class="wrap">
  {LANG_SWITCH}
  <div class="card">
    <div class="card-top"><span class="dot">◉</span> 尾久 SKYLEDGER</div>
    <h1>{{T_account_heading}}</h1>
    <div class="who">◆ {USER}</div>
    {MSG}
    <form method="post" action="/account/password">
      <label>{{T_lbl_current_pw}}<input name="current" type="password" autocomplete="current-password" required autofocus></label>
      <label>{{T_lbl_new_pw}}<input name="new" type="password" autocomplete="new-password" required minlength="6"></label>
      <label>{{T_lbl_confirm_pw}}<input name="confirm" type="password" autocomplete="new-password" required minlength="6"></label>
      <button type="submit">{{T_btn_update_pw}}</button>
    </form>
    <a class="back" href="/">{{T_link_back_home}}</a>
  </div>
</div>
<script type="module">
  import * as THREE from 'https://unpkg.com/three@0.160.0/build/three.module.js';
  const MINT=0x7fffd4,AMBER=0xf5d96f,RING=0x1f5a4a;
  const canvas=document.getElementById('radar');
  const scene=new THREE.Scene();
  const camera=new THREE.PerspectiveCamera(45,innerWidth/innerHeight,0.1,200);
  camera.position.set(0,8,14); camera.lookAt(0,0,0);
  const renderer=new THREE.WebGLRenderer({canvas,alpha:true,antialias:true});
  renderer.setSize(innerWidth,innerHeight); renderer.setPixelRatio(Math.min(devicePixelRatio,2));
  for(const r of[2,4,6,8,10]){const ring=new THREE.Mesh(new THREE.RingGeometry(r-.01,r+.01,96),new THREE.MeshBasicMaterial({color:RING,transparent:true,opacity:.5,side:THREE.DoubleSide}));ring.rotation.x=-Math.PI/2;scene.add(ring);}
  scene.add(new THREE.LineSegments(new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(-10,0,0),new THREE.Vector3(10,0,0),new THREE.Vector3(0,0,-10),new THREE.Vector3(0,0,10)]),new THREE.LineBasicMaterial({color:RING,transparent:true,opacity:.35})));
  const sg=new THREE.Group();
  sg.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(0,0,0),new THREE.Vector3(10,0,0)]),new THREE.LineBasicMaterial({color:MINT,transparent:true,opacity:.7})));
  const w=new THREE.Mesh(new THREE.CircleGeometry(10,48,-Math.PI/4,Math.PI/4),new THREE.MeshBasicMaterial({color:MINT,transparent:true,opacity:.08,side:THREE.DoubleSide}));w.rotation.x=-Math.PI/2;sg.add(w);scene.add(sg);
  const blips=[];
  for(let i=0;i<14;i++){const a=Math.random()*Math.PI*2,d=2+Math.random()*8,y=.3+Math.random()*2;const mat=new THREE.MeshBasicMaterial({color:AMBER,transparent:true,opacity:.4});const b=new THREE.Mesh(new THREE.SphereGeometry(.12,12,12),mat);b.position.set(Math.cos(a)*d,y,Math.sin(a)*d);const tr=new THREE.Line(new THREE.BufferGeometry().setFromPoints([b.position.clone(),b.position.clone()]),new THREE.LineBasicMaterial({color:AMBER,transparent:true,opacity:.25}));scene.add(b);scene.add(tr);blips.push({mesh:b,trail:tr,angle:a,dist:d,y,drift:(Math.random()-.5)*.003,prev:b.position.clone()});}
  addEventListener('resize',()=>{camera.aspect=innerWidth/innerHeight;camera.updateProjectionMatrix();renderer.setSize(innerWidth,innerHeight);});
  let sa=0,run=true;
  document.addEventListener('visibilitychange',()=>{run=!document.hidden;if(run)go();});
  function go(){if(!run)return;sa+=.012;sg.rotation.y=sa;const sx=Math.cos(sa),sz=-Math.sin(sa);blips.forEach(b=>{b.angle+=b.drift;b.prev.copy(b.mesh.position);b.mesh.position.x=Math.cos(b.angle)*b.dist;b.mesh.position.z=Math.sin(b.angle)*b.dist;b.mesh.position.y=b.y;b.trail.geometry.setFromPoints([b.prev,b.mesh.position]);const mag=Math.hypot(b.mesh.position.x,b.mesh.position.z)||1;const dot=(sx*b.mesh.position.x+sz*b.mesh.position.z)/mag;const i=Math.max(0,dot);b.mesh.scale.setScalar(.4+i*.6);b.mesh.material.opacity=.25+i*.75;});renderer.render(scene,camera);requestAnimationFrame(go);}
  go();
</script>
</body></html>'''


def _parse_cookie(header_value):
    if not header_value:
        return {}
    c = http_cookies.SimpleCookie()
    try:
        c.load(header_value)
    except http_cookies.CookieError:
        return {}
    return {k: m.value for k, m in c.items()}


def _read_form(handler):
    length = int(handler.headers.get('Content-Length') or 0)
    if not length:
        return {}
    body = handler.rfile.read(length).decode('utf-8', errors='replace')
    return {k: v[0] for k, v in parse_qs(body, keep_blank_values=True).items()}


def _current_user(handler):
    token = _parse_cookie(handler.headers.get('Cookie')).get(auth.COOKIE_NAME)
    return auth.lookup_session(token) if token else None


def _send_simple(handler, status, body, content_type='text/html; charset=utf-8', extra_headers=None):
    if isinstance(body, str):
        body = body.encode('utf-8')
    handler.send_response(status)
    handler.send_header('Content-Type', content_type)
    handler.send_header('Content-Length', str(len(body)))
    if extra_headers:
        for k, v in extra_headers:
            handler.send_header(k, v)
    handler.end_headers()
    handler.wfile.write(body)


def _redirect(handler, location, extra_headers=None):
    handler.send_response(303)
    handler.send_header('Location', location)
    if extra_headers:
        for k, v in extra_headers:
            handler.send_header(k, v)
    handler.send_header('Content-Length', '0')
    handler.end_headers()


def _session_cookie_header(token, expires_utc):
    # SameSite=Lax: cross-site form POST 唔會帶 cookie，CSRF 基本擋到。
    # 冇 Secure（LAN-only HTTP）。
    return (
        'Set-Cookie',
        f"{auth.COOKIE_NAME}={token}; HttpOnly; SameSite=Lax; Path=/; "
        f"Expires={expires_utc.strftime('%a, %d %b %Y %H:%M:%S GMT')}",
    )


def _clear_session_cookie_header():
    return (
        'Set-Cookie',
        f"{auth.COOKIE_NAME}=; HttpOnly; SameSite=Lax; Path=/; "
        "Expires=Thu, 01 Jan 1970 00:00:00 GMT",
    )


def _get_lang(handler):
    lang = _parse_cookie(handler.headers.get('Cookie')).get('lang', '')
    return lang if lang in LANGS else DEFAULT_LANG


def _lang_switch_html(lang):
    return (_AUTH_LANG_SWITCH
            .replace('{CL_JP}', 'on' if lang == 'jp' else '')
            .replace('{CL_HK}', 'on' if lang == 'hk' else '')
            .replace('{CL_EN}', 'on' if lang == 'en' else ''))


def _render_login(lang, error='', next_path='/'):
    err_html = f'<div class="err">{html.escape(error)}</div>' if error else ''
    page = _render(LOGIN_PAGE, lang)
    return (page
            .replace('{LANG_SWITCH}', _lang_switch_html(lang))
            .replace('{ERR}', err_html)
            .replace('{NEXT}', html.escape(next_path)))


def _render_account(lang, user, msg='', ok=False):
    if msg:
        cls = 'ok' if ok else 'err'
        msg_html = f'<div class="{cls}">{html.escape(msg)}</div>'
    else:
        msg_html = ''
    page = _render(ACCOUNT_PAGE, lang)
    return (page
            .replace('{LANG_SWITCH}', _lang_switch_html(lang))
            .replace('{USER}', html.escape(user))
            .replace('{MSG}', msg_html))


def _safe_next(value):
    # 只接受本地 path，避免 open redirect。
    if value and value.startswith('/') and not value.startswith('//'):
        return value
    return '/'


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        lang = _get_lang(self)
        if parsed.path == '/':
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(_render(HOME_HTML, lang).encode('utf-8'))
            return
        if parsed.path == '/favicon.svg':
            self.send_response(200)
            self.send_header('Content-Type', 'image/svg+xml')
            self.send_header('Cache-Control', 'max-age=86400')
            self.end_headers()
            self.wfile.write(FAVICON_SVG.encode('utf-8'))
            return
        if parsed.path == '/details':
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(_render(DETAILS_HTML, lang).encode('utf-8'))
            return
        if parsed.path == '/api/summary':
            qs = parse_qs(parsed.query)
            day = qs.get('day', [datetime.now(JST).strftime('%Y-%m-%d')])[0]
            payload = query_summary(day)
            body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if parsed.path == '/api/me':
            user = _current_user(self)
            _send_simple(self, 200, json.dumps({'username': user}, ensure_ascii=False),
                         content_type='application/json; charset=utf-8')
            return
        if parsed.path == '/login':
            qs = parse_qs(parsed.query)
            next_path = _safe_next(qs.get('next', ['/'])[0])
            _send_simple(self, 200, _render_login(lang, next_path=next_path))
            return
        if parsed.path == '/account':
            user = _current_user(self)
            if not user:
                _redirect(self, '/login?next=/account')
                return
            _send_simple(self, 200, _render_account(lang, user))
            return
        if parsed.path == '/api/today':
            qs = parse_qs(parsed.query)
            day = qs.get('day', [datetime.now(JST).strftime('%Y-%m-%d')])[0]
            sort = qs.get('sort', ['last_seen'])[0]
            country_filter = qs.get('country', [''])[0]
            operator_filter = qs.get('operator', [''])[0]
            type_filter = qs.get('type', [''])[0]
            from_filter = qs.get('from', [''])[0]
            to_filter = qs.get('to', [''])[0]
            rows = query_rows(day, sort, country_filter, operator_filter, type_filter,
                              from_filter, to_filter)
            all_rows = query_rows(day, sort)
            countries = sorted({r['country'] for r in all_rows if r['country'] != '-'})
            operators = sorted({r['operator'] for r in all_rows if r['operator'] != '-'})
            types = sorted({r['aircraft_type'] for r in all_rows if r['aircraft_type'] != '-'})
            from_airports = sorted({r['from_airport'] for r in all_rows if r['from_airport'] != '-'})
            to_airports = sorted({r['to_airport'] for r in all_rows if r['to_airport'] != '-'})
            payload = {
                'day': day,
                'sort': sort,
                'count': len(rows),
                'countries': countries,
                'operators': operators,
                'types': types,
                'from_airports': from_airports,
                'to_airports': to_airports,
                'rows': rows,
            }
            body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_response(404)
        self.end_headers()

    def do_POST(self):
        parsed = urlparse(self.path)
        lang = _get_lang(self)
        s = STRINGS[lang]
        if parsed.path == '/login':
            form = _read_form(self)
            username = (form.get('username') or '').strip()
            password = form.get('password') or ''
            next_path = _safe_next(form.get('next', '/'))
            if not username or not password or not auth.authenticate(username, password):
                _send_simple(self, 200, _render_login(lang, error=s['err_login'], next_path=next_path))
                return
            token, expires = auth.create_session(username)
            _redirect(self, next_path, extra_headers=[_session_cookie_header(token, expires)])
            return
        if parsed.path == '/logout':
            token = _parse_cookie(self.headers.get('Cookie')).get(auth.COOKIE_NAME)
            auth.delete_session(token)
            _redirect(self, '/', extra_headers=[_clear_session_cookie_header()])
            return
        if parsed.path == '/account/password':
            user = _current_user(self)
            if not user:
                _redirect(self, '/login?next=/account')
                return
            form = _read_form(self)
            current = form.get('current') or ''
            new = form.get('new') or ''
            confirm = form.get('confirm') or ''
            if not auth.authenticate(user, current):
                _send_simple(self, 200, _render_account(lang, user, msg=s['err_current_wrong']))
                return
            if new != confirm:
                _send_simple(self, 200, _render_account(lang, user, msg=s['err_pw_mismatch']))
                return
            if len(new) < 6:
                _send_simple(self, 200, _render_account(lang, user, msg=s['err_pw_short']))
                return
            auth.set_password(user, new)
            _send_simple(self, 200, _render_account(lang, user, msg=s['ok_pw_updated'], ok=True))
            return
        self.send_response(404)
        self.end_headers()

    def log_message(self, format, *args):
        return


def serve():
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f'plane-history web app: http://{HOST}:{PORT}', flush=True)
    server.serve_forever()


if __name__ == '__main__':
    serve()
