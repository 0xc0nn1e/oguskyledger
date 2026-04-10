import json
import sqlite3
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG = json.loads((BASE_DIR / 'src' / 'config.json').read_text())
DB_PATH = BASE_DIR / CONFIG['db']['path']
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
  </style>
</head>
<body>
  <h1>plane-history</h1>
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


def query_rows(day_str, sort_key, country_filter='', operator_filter='', type_filter=''):
    order_by = ALLOWED_SORTS.get(sort_key, ALLOWED_SORTS['last_seen'])
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    conditions = ["date(s.seen_at, '+9 hours') = ?"]
    params = [day_str]
    if country_filter:
        conditions.append("COALESCE(NULLIF(TRIM(c.country), ''), '-') = ?")
        params.append(country_filter)
    if operator_filter:
        conditions.append("COALESCE(NULLIF(TRIM(c.operator), ''), '-') = ?")
        params.append(operator_filter)
    if type_filter:
        conditions.append("COALESCE(NULLIF(TRIM(c.aircraft_type), ''), '-') = ?")
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


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == '/':
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(HTML.encode('utf-8'))
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

    def log_message(self, format, *args):
        return


if __name__ == '__main__':
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f'plane-history web app: http://{HOST}:{PORT}', flush=True)
    server.serve_forever()
