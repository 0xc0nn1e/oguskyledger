import html
import json
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

HTML = '''<!doctype html>
<html lang="zh-Hant">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>plane-history</title>
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, sans-serif; margin: 24px; background:#111827; color:#f9fafb; }
    .controls { display:flex; gap:12px; flex-wrap:wrap; align-items:end; margin-bottom:16px; }
    label { display:flex; flex-direction:column; gap:6px; font-size:14px; }
    input, select, button { padding:8px 10px; border-radius:8px; border:1px solid #374151; background:#1f2937; color:#f9fafb; }
    button { cursor:pointer; }
    table { width:100%; border-collapse:collapse; font-size:13px; background:#111827; }
    th, td { border-bottom:1px solid #374151; padding:8px 6px; text-align:left; }
    th { position:sticky; top:0; background:#1f2937; }
    .meta { margin-bottom:12px; color:#d1d5db; }
    .wrap { overflow:auto; max-height:75vh; border:1px solid #374151; border-radius:12px; }
    .topbar { display:flex; justify-content:space-between; align-items:center; margin-bottom:8px; }
    .nav a, .nav span { color:#93c5fd; text-decoration:none; margin-left:12px; font-size:14px; }
    .nav form { display:inline; margin:0; }
    .nav button { background:none; border:none; color:#93c5fd; padding:0; cursor:pointer; font-size:14px; margin-left:12px; }
  </style>
</head>
<body>
  <div class="topbar">
    <h1 style="margin:0">plane-history</h1>
    <div class="nav" id="nav"></div>
  </div>
  <div class="controls">
    <label>日期
      <input type="date" id="day">
    </label>
    <label>Sort
      <select id="sort">
        <option value="last_seen">last_seen</option>
        <option value="country">country</option>
        <option value="operator">operator</option>
        <option value="type">type</option>
      </select>
    </label>
    <label>Country
      <select id="countryFilter">
        <option value="">all</option>
      </select>
    </label>
    <label>Operator
      <select id="operatorFilter">
        <option value="">all</option>
      </select>
    </label>
    <label>Type
      <select id="typeFilter">
        <option value="">all</option>
      </select>
    </label>
    <button id="load">更新</button>
  </div>
  <div class="meta" id="meta">loading...</div>
  <div class="wrap">
    <table>
      <thead>
        <tr>
          <th>ICAO</th><th>FLIGHT</th><th>OPERATOR</th><th>REG</th><th>TYPE</th><th>COUNTRY</th><th>CAT</th><th>ALT_MIN</th><th>ALT_MAX</th><th>SAMPLES</th><th>FIRST_SEEN</th><th>LAST_SEEN</th>
        </tr>
      </thead>
      <tbody id="rows"></tbody>
    </table>
  </div>
  <script>
    const day = document.getElementById('day');
    const sort = document.getElementById('sort');
    const rows = document.getElementById('rows');
    const meta = document.getElementById('meta');
    const loadBtn = document.getElementById('load');
    const countryFilter = document.getElementById('countryFilter');
    const operatorFilter = document.getElementById('operatorFilter');
    const typeFilter = document.getElementById('typeFilter');

    function esc(v) {
      return String(v ?? '-').replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;');
    }

    async function load() {
      const qs = new URLSearchParams({ day: day.value, sort: sort.value, country: countryFilter.value, operator: operatorFilter.value, type: typeFilter.value });
      const res = await fetch('/api/today?' + qs.toString());
      const data = await res.json();
      meta.textContent = `Day: ${data.day} | Aircraft: ${data.count} | Sort: ${data.sort}`;
      if (countryFilter.options.length <= 1) {
        data.countries.forEach(v => countryFilter.insertAdjacentHTML('beforeend', `<option value="${v}">${v}</option>`));
      }
      if (operatorFilter.options.length <= 1) {
        data.operators.forEach(v => operatorFilter.insertAdjacentHTML('beforeend', `<option value="${v}">${v}</option>`));
      }
      if (typeFilter.options.length <= 1) {
        data.types.forEach(v => typeFilter.insertAdjacentHTML('beforeend', `<option value="${v}">${v}</option>`));
      }
      rows.innerHTML = data.rows.map(r => `
        <tr>
          <td>${esc(r.icao)}</td>
          <td>${esc(r.flight)}</td>
          <td>${esc(r.operator)}</td>
          <td>${r.registration !== '-' ? `<a href="https://www.flightradar24.com/data/aircraft/${encodeURIComponent(r.registration.toLowerCase())}" target="_blank" rel="noreferrer" style="color:#93c5fd">${esc(r.registration)}</a>` : '-'}</td>
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

    async function renderNav() {
      const nav = document.getElementById('nav');
      try {
        const me = await (await fetch('/api/me')).json();
        if (me.username) {
          nav.innerHTML = `<span>👤 ${esc(me.username)}</span>
            <a href="/account">改密碼</a>
            <form method="post" action="/logout"><button type="submit">登出</button></form>`;
        } else {
          nav.innerHTML = `<a href="/login">登入</a>`;
        }
      } catch (e) {
        nav.innerHTML = `<a href="/login">登入</a>`;
      }
    }

    const today = new Date();
    const yyyy = today.getFullYear();
    const mm = String(today.getMonth() + 1).padStart(2, '0');
    const dd = String(today.getDate()).padStart(2, '0');
    day.value = `${yyyy}-${mm}-${dd}`;
    loadBtn.addEventListener('click', load);
    sort.addEventListener('change', load);
    day.addEventListener('change', load);
    countryFilter.addEventListener('change', load);
    operatorFilter.addEventListener('change', load);
    typeFilter.addEventListener('change', load);
    renderNav();
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


def query_rows(day_str, sort_key, country_filter='', operator_filter='', type_filter=''):
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
            'category': r['category'] or '-',
            'min_alt_baro': int(r['min_alt_baro']) if r['min_alt_baro'] is not None else '-',
            'max_alt_baro': int(r['max_alt_baro']) if r['max_alt_baro'] is not None else '-',
            'samples': r['samples'],
            'first_seen_jst': fmt_ts(r['first_seen']),
            'last_seen_jst': fmt_ts(r['last_seen']),
        })
    conn.close()
    return rows


LOGIN_PAGE = '''<!doctype html>
<html lang="zh-Hant"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>登入 · plane-history</title>
<style>
  body { font-family:-apple-system,BlinkMacSystemFont,sans-serif; background:#111827; color:#f9fafb; margin:0; display:flex; min-height:100vh; align-items:center; justify-content:center; }
  .card { background:#1f2937; padding:32px; border-radius:12px; min-width:300px; }
  h1 { margin:0 0 24px; font-size:20px; }
  label { display:block; margin-bottom:12px; font-size:14px; }
  input { width:100%; box-sizing:border-box; padding:10px; border-radius:8px; border:1px solid #374151; background:#111827; color:#f9fafb; margin-top:6px; }
  button { width:100%; padding:10px; border-radius:8px; border:none; background:#2563eb; color:white; cursor:pointer; font-size:14px; }
  .err { color:#fca5a5; font-size:13px; margin-bottom:12px; }
  .back { display:block; text-align:center; margin-top:16px; color:#93c5fd; font-size:13px; }
</style></head><body>
<div class="card">
  <h1>登入 plane-history</h1>
  {ERR}
  <form method="post" action="/login">
    <input type="hidden" name="next" value="{NEXT}">
    <label>Username<input name="username" autocomplete="username" required autofocus></label>
    <label>密碼<input name="password" type="password" autocomplete="current-password" required></label>
    <button type="submit">登入</button>
  </form>
  <a class="back" href="/">← 返首頁</a>
</div></body></html>'''


ACCOUNT_PAGE = '''<!doctype html>
<html lang="zh-Hant"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>改密碼 · plane-history</title>
<style>
  body { font-family:-apple-system,BlinkMacSystemFont,sans-serif; background:#111827; color:#f9fafb; margin:0; display:flex; min-height:100vh; align-items:center; justify-content:center; }
  .card { background:#1f2937; padding:32px; border-radius:12px; min-width:320px; }
  h1 { margin:0 0 8px; font-size:20px; }
  .who { color:#9ca3af; font-size:13px; margin-bottom:20px; }
  label { display:block; margin-bottom:12px; font-size:14px; }
  input { width:100%; box-sizing:border-box; padding:10px; border-radius:8px; border:1px solid #374151; background:#111827; color:#f9fafb; margin-top:6px; }
  button { width:100%; padding:10px; border-radius:8px; border:none; background:#2563eb; color:white; cursor:pointer; font-size:14px; }
  .err { color:#fca5a5; font-size:13px; margin-bottom:12px; }
  .ok { color:#86efac; font-size:13px; margin-bottom:12px; }
  .back { display:block; text-align:center; margin-top:16px; color:#93c5fd; font-size:13px; }
</style></head><body>
<div class="card">
  <h1>改密碼</h1>
  <div class="who">👤 {USER}</div>
  {MSG}
  <form method="post" action="/account/password">
    <label>而家嘅密碼<input name="current" type="password" autocomplete="current-password" required autofocus></label>
    <label>新密碼<input name="new" type="password" autocomplete="new-password" required minlength="6"></label>
    <label>再入一次<input name="confirm" type="password" autocomplete="new-password" required minlength="6"></label>
    <button type="submit">更新密碼</button>
  </form>
  <a class="back" href="/">← 返首頁</a>
</div></body></html>'''


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


def _render_login(error='', next_path='/'):
    err_html = f'<div class="err">{html.escape(error)}</div>' if error else ''
    return LOGIN_PAGE.replace('{ERR}', err_html).replace('{NEXT}', html.escape(next_path))


def _render_account(user, msg='', ok=False):
    if msg:
        cls = 'ok' if ok else 'err'
        msg_html = f'<div class="{cls}">{html.escape(msg)}</div>'
    else:
        msg_html = ''
    return ACCOUNT_PAGE.replace('{USER}', html.escape(user)).replace('{MSG}', msg_html)


def _safe_next(value):
    # 只接受本地 path，避免 open redirect。
    if value and value.startswith('/') and not value.startswith('//'):
        return value
    return '/'


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == '/':
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(HTML.encode('utf-8'))
            return
        if parsed.path == '/api/me':
            user = _current_user(self)
            _send_simple(self, 200, json.dumps({'username': user}, ensure_ascii=False),
                         content_type='application/json; charset=utf-8')
            return
        if parsed.path == '/login':
            qs = parse_qs(parsed.query)
            next_path = _safe_next(qs.get('next', ['/'])[0])
            _send_simple(self, 200, _render_login(next_path=next_path))
            return
        if parsed.path == '/account':
            user = _current_user(self)
            if not user:
                _redirect(self, '/login?next=/account')
                return
            _send_simple(self, 200, _render_account(user))
            return
        if parsed.path == '/api/today':
            qs = parse_qs(parsed.query)
            day = qs.get('day', [datetime.now(JST).strftime('%Y-%m-%d')])[0]
            sort = qs.get('sort', ['last_seen'])[0]
            country_filter = qs.get('country', [''])[0]
            operator_filter = qs.get('operator', [''])[0]
            type_filter = qs.get('type', [''])[0]
            rows = query_rows(day, sort, country_filter, operator_filter, type_filter)
            all_rows = query_rows(day, sort)
            countries = sorted({r['country'] for r in all_rows if r['country'] != '-'})
            operators = sorted({r['operator'] for r in all_rows if r['operator'] != '-'})
            types = sorted({r['aircraft_type'] for r in all_rows if r['aircraft_type'] != '-'})
            payload = {
                'day': day,
                'sort': sort,
                'count': len(rows),
                'countries': countries,
                'operators': operators,
                'types': types,
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
        if parsed.path == '/login':
            form = _read_form(self)
            username = (form.get('username') or '').strip()
            password = form.get('password') or ''
            next_path = _safe_next(form.get('next', '/'))
            if not username or not password or not auth.authenticate(username, password):
                _send_simple(self, 200, _render_login(error='Username 或密碼錯誤', next_path=next_path))
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
                _send_simple(self, 200, _render_account(user, msg='而家嘅密碼錯'))
                return
            if new != confirm:
                _send_simple(self, 200, _render_account(user, msg='兩次新密碼唔一樣'))
                return
            if len(new) < 6:
                _send_simple(self, 200, _render_account(user, msg='新密碼至少 6 個字'))
                return
            auth.set_password(user, new)
            _send_simple(self, 200, _render_account(user, msg='✓ 密碼已更新', ok=True))
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
