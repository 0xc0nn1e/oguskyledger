import html
import json
import re
import urllib.request
from datetime import date, datetime, timedelta, timezone
from http import cookies as http_cookies
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import auth
from db import connect, dict_cursor

HOST = '0.0.0.0'
PORT = 8765
JST = timezone(timedelta(hours=9))
# process 起身時間（supervisor 每次拉返起會 reset），/about 用嚟計 uptime
_BOOT_AT = datetime.now(timezone.utc)

# tar1090 aircraft.json URL（由 config 讀，/api/live 即時抓嚟畀地圖）
try:
    _SOURCE_URL = json.loads(
        (Path(__file__).resolve().parent / 'config.json').read_text()
    )['source']['aircraft_json_url']
except Exception:
    _SOURCE_URL = None
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
        'nav_stats': '統計',
        'nav_home': '← トップ',
        'nav_login': 'ログイン',
        'nav_logout': 'ログアウト',
        'nav_account': 'アカウント',
        'stats_title': '統計 · plane-history',
        'stats_hdr_7d_hist': '直近7日 · 便数推移',
        'stats_hdr_24h_hist': '直近24時間 · 時間帯別便数 (JST)',
        'stats_hdr_7d_types': '直近7日 · 機種 TOP 10',
        'stats_hdr_7d_ops': '直近7日 · 運航会社 TOP 10',
        'stats_hdr_7d_from': '直近7日 · 出発空港 TOP 10',
        'stats_hdr_7d_to': '直近7日 · 到着空港 TOP 10',
        'stats_hdr_db_total': '全DB · 累計便数',
        'stats_hdr_db_types': '全DB · 機種数',
        'stats_hdr_peak_alt': '全DB · 最高高度',
        'stats_hdr_busiest_hour': '全DB · 繁忙時間帯 (JST)',
        'stats_col_aircraft': '便数',
        'stats_col_rank': '順位',
        'nav_about': '概要',
        'about_title': 'About · plane-history',
        'about_hdr_receiver': '受信機ステータス',
        'about_hdr_project': 'このプロジェクト',
        'about_hdr_arch': 'アーキテクチャ',
        'about_lbl_receiver': '受信機',
        'about_lbl_source': 'ソース',
        'about_lbl_uptime': '稼働時間',
        'about_lbl_last_update': '最終受信',
        'about_lbl_feed': 'フィード状態',
        'about_feed_ok': 'OK · 正常',
        'about_feed_stale': '遅延',
        'about_feed_down': '停止',
        'about_ago_fmt': '{n}{u}前',
        'about_unit_sec': '秒',
        'about_unit_min': '分',
        'about_unit_hr': '時間',
        'about_unit_day': '日',
        'about_desc': '自宅に設置したADS-B受信機から航空機データを取得し、MySQLに履歴を保存したうえで、Python（標準ライブラリの http.server）によるAPIとWebダッシュボードで可視化しています。',
        'home_subtitle': '東京・尾久の自宅受信機で取得した航空機データを記録・可視化する個人開発プロジェクトです。',
        'stats_note': 'これらの統計は MySQL に保存された過去の航空機コンタクトから算出しています。',
        'details_note': '運航会社・機種・航路・国・高度レンジで過去の航空機コンタクトを検索・絞り込みできます。',
        'about_hdr_stack': '技術スタック',
        'about_hdr_health': 'システムヘルス',
        'about_stack_frontend': 'フロントエンド',
        'about_stack_backend': 'バックエンド',
        'about_stack_db': 'データベース',
        'about_stack_receiver': '受信機',
        'about_stack_deploy': 'デプロイ',
        'about_stack_notify': '通知',
        'about_lbl_api': 'API',
        'about_lbl_db': 'データベース',
        'about_lbl_records_today': '本日の記録数',
        'nav_map': 'マップ',
        'map_title': 'ライブマップ · plane-history',
        'map_hdr': 'ライブマップ · 受信中',
        'map_unit': '機',
        'map_note': '受信機が今この瞬間に捉えている航空機を、速度と進路から滑らかに移動表示しています（tar1090 ライブ）。',
        'map_empty': '// 測位情報のある航空機が今ありません',
        'map_loading': '読み込み中...',
        'map_alt': '高度',
        'map_spd': '速度',
        'map_reg': 'レジ',
        'map_type': '機種',
        'map_op': '運航会社',
        'map_country': '国籍',
        'map_route': '区間',
        'map_vs': '昇降率',
        'map_hdg': '進路',
        'map_fr24': 'FR24 で見る',
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
        'nav_stats': '統計',
        'nav_home': '← 首頁',
        'nav_login': '登入',
        'nav_logout': '登出',
        'nav_account': '改密碼',
        'stats_title': '統計 · plane-history',
        'stats_hdr_7d_hist': '近 7 日 · 每日班次',
        'stats_hdr_24h_hist': '近 24 小時 · 每小時班次 (JST)',
        'stats_hdr_7d_types': '近 7 日 · 機型 TOP 10',
        'stats_hdr_7d_ops': '近 7 日 · 航空公司 TOP 10',
        'stats_hdr_7d_from': '近 7 日 · 出發地 TOP 10',
        'stats_hdr_7d_to': '近 7 日 · 目的地 TOP 10',
        'stats_hdr_db_total': '全 DB · 累計班次',
        'stats_hdr_db_types': '全 DB · 機型總數',
        'stats_hdr_peak_alt': '全 DB · 最高高度',
        'stats_hdr_busiest_hour': '全 DB · 最繁忙時段 (JST)',
        'stats_col_aircraft': '班次',
        'stats_col_rank': '排名',
        'nav_about': '關於',
        'about_title': '關於 · plane-history',
        'about_hdr_receiver': '接收機狀態',
        'about_hdr_project': '關於呢個 project',
        'about_hdr_arch': '系統架構',
        'about_lbl_receiver': '接收機',
        'about_lbl_source': '來源',
        'about_lbl_uptime': '運行時間',
        'about_lbl_last_update': '最後收到',
        'about_lbl_feed': 'Feed 狀態',
        'about_feed_ok': 'OK · 正常',
        'about_feed_stale': '延遲',
        'about_feed_down': '停咗',
        'about_ago_fmt': '{n} {u}前',
        'about_unit_sec': '秒',
        'about_unit_min': '分',
        'about_unit_hr': '小時',
        'about_unit_day': '日',
        'about_desc': '呢個 project 由自己 host 嘅 ADS-B 接收機收集飛機數據，將歷史接觸記錄存入 MySQL，再透過 Python（stdlib http.server）後端 API 同 Web dashboard 將近期飛機活動視覺化。',
        'home_subtitle': '由東京尾久自宅接收機收集飛機數據、記錄同視覺化嘅個人 project。',
        'stats_note': '呢啲統計係由 MySQL 入面儲存嘅歷史飛機接觸記錄計出嚟。',
        'details_note': '可以按航空公司、機型、航線、國家同高度範圍搜尋同篩選歷史飛機接觸記錄。',
        'about_hdr_stack': '技術 Stack',
        'about_hdr_health': '系統健康',
        'about_stack_frontend': '前端',
        'about_stack_backend': '後端',
        'about_stack_db': '資料庫',
        'about_stack_receiver': '接收機',
        'about_stack_deploy': '部署',
        'about_stack_notify': '通知',
        'about_lbl_api': 'API',
        'about_lbl_db': '資料庫',
        'about_lbl_records_today': '今日記錄數',
        'nav_map': '地圖',
        'map_title': '即時地圖 · plane-history',
        'map_hdr': '即時地圖 · 接收中',
        'map_unit': '架',
        'map_note': '顯示接收機而家即時捉到嘅飛機，按速度同航向平滑移動（tar1090 live）。',
        'map_empty': '// 而家冇有定位嘅飛機',
        'map_loading': '載入中...',
        'map_alt': '高度',
        'map_spd': '速度',
        'map_reg': '機牌',
        'map_type': '機型',
        'map_op': '航空公司',
        'map_country': '註冊國',
        'map_route': '航線',
        'map_vs': '升降率',
        'map_hdg': '航向',
        'map_fr24': 'FR24 詳情',
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
        'nav_stats': 'STATS',
        'nav_home': '← HOME',
        'nav_login': 'SIGN IN',
        'nav_logout': 'SIGN OUT',
        'nav_account': 'ACCOUNT',
        'stats_title': 'Stats · plane-history',
        'stats_hdr_7d_hist': '7-DAY · DAILY FLIGHTS',
        'stats_hdr_24h_hist': 'LAST 24H · FLIGHTS BY HOUR (JST)',
        'stats_hdr_7d_types': '7-DAY · TOP 10 TYPES',
        'stats_hdr_7d_ops': '7-DAY · TOP 10 OPERATORS',
        'stats_hdr_7d_from': '7-DAY · TOP 10 FROM',
        'stats_hdr_7d_to': '7-DAY · TOP 10 TO',
        'stats_hdr_db_total': 'ALL-TIME · TOTAL FLIGHTS',
        'stats_hdr_db_types': 'ALL-TIME · TOTAL TYPES',
        'stats_hdr_peak_alt': 'ALL-TIME · PEAK ALT',
        'stats_hdr_busiest_hour': 'ALL-TIME · BUSIEST HOUR (JST)',
        'stats_col_aircraft': 'FLIGHTS',
        'stats_col_rank': '#',
        'nav_about': 'ABOUT',
        'about_title': 'About · plane-history',
        'about_hdr_receiver': 'RECEIVER STATUS',
        'about_hdr_project': 'ABOUT THIS PROJECT',
        'about_hdr_arch': 'ARCHITECTURE',
        'about_lbl_receiver': 'Receiver',
        'about_lbl_source': 'Source',
        'about_lbl_uptime': 'Uptime',
        'about_lbl_last_update': 'Last aircraft update',
        'about_lbl_feed': 'Feed health',
        'about_feed_ok': 'OK',
        'about_feed_stale': 'DELAYED',
        'about_feed_down': 'DOWN',
        'about_ago_fmt': '{n} {u} ago',
        'about_unit_sec': 'sec',
        'about_unit_min': 'min',
        'about_unit_hr': 'hr',
        'about_unit_day': 'day',
        'about_desc': 'This project collects ADS-B aircraft data from a self-hosted receiver, stores historical contacts in MySQL, and visualizes recent aircraft activity through a Python backend (stdlib http.server) and web dashboard.',
        'home_subtitle': 'Personal ADS-B flight data dashboard powered by a self-hosted receiver in Oku, Tokyo.',
        'stats_note': 'These statistics are calculated from historical aircraft contacts stored in MySQL.',
        'details_note': 'Search and filter historical aircraft contacts by operator, aircraft type, route, country and altitude range.',
        'about_hdr_stack': 'TECH STACK',
        'about_hdr_health': 'SYSTEM HEALTH',
        'about_stack_frontend': 'Frontend',
        'about_stack_backend': 'Backend',
        'about_stack_db': 'Database',
        'about_stack_receiver': 'Receiver',
        'about_stack_deploy': 'Deployment',
        'about_stack_notify': 'Notification',
        'about_lbl_api': 'API',
        'about_lbl_db': 'Database',
        'about_lbl_records_today': 'Records today',
        'nav_map': 'MAP',
        'map_title': 'Live Map · plane-history',
        'map_hdr': 'LIVE MAP · NOW SCANNING',
        'map_unit': 'aircraft',
        'map_note': 'Aircraft currently picked up by the receiver, animated smoothly from speed and heading (tar1090 live).',
        'map_empty': '// no aircraft with position right now',
        'map_loading': 'loading...',
        'map_alt': 'ALT',
        'map_spd': 'SPD',
        'map_reg': 'REG',
        'map_type': 'TYPE',
        'map_op': 'OPERATOR',
        'map_country': 'COUNTRY',
        'map_route': 'ROUTE',
        'map_vs': 'V/S',
        'map_hdg': 'HDG',
        'map_fr24': 'VIEW ON FR24',
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
    out = re.sub(r'\{\{T_([a-z0-9_]+)\}\}', repl, template)
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
      height: 100vh; height: 100dvh; overflow-y: auto; overflow-x: hidden;
      scrollbar-width: thin; scrollbar-color: var(--x-muted) transparent;
    }
    .container::-webkit-scrollbar { width: 6px; }
    .container::-webkit-scrollbar-thumb { background: rgba(127,255,212,0.15); border-radius: 3px; }
    .inner { max-width: 1400px; margin: 0 auto; padding: 24px 32px calc(80px + env(safe-area-inset-bottom)); }

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

    .page-subtitle { margin:0 0 16px; font-size:12px; line-height:1.7;
      letter-spacing:0.5px; color:var(--muted); max-width:760px; }
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
    @media (max-width: 700px) {
      .inner { position: relative; padding: 44px 16px calc(100px + env(safe-area-inset-bottom)); }
      .hdr-row { gap: 8px; }
      .hdr-row.top { font-size: 9px; letter-spacing: 1.5px; }
      .hdr-row.main { flex-wrap: wrap; }
      .hdr-row.main .title { font-size: 16px; letter-spacing: 0.5px; }
      .hdr-row.main .clock { font-size: 13px; }
      .hdr-row.sub .coords { display: none; }
      .hdr-row.sub { justify-content: flex-end; }
      .tools .nav > span:not(.lang-switch) { display: none; }
      .tools { justify-content: flex-end; gap: 4px; flex-wrap: wrap; }
      .tools .nav { justify-content: flex-end; gap: 4px; }
      .tools .nav a, .tools .nav button { padding: 5px 8px; font-size: 10px; letter-spacing: 1px; }
      .lang-switch {
        position: absolute; top: 12px; right: 12px; z-index: 5;
        margin: 0; gap: 4px;
        background: rgba(5,10,13,0.85); padding: 4px;
        border-radius: 4px;
      }
      .lang-switch a { padding: 5px 8px; font-size: 10px; }
      .controls { padding: 10px; gap: 6px; }
      .controls label { font-size: 8px; }
      .wrap { max-height: none; overflow-y: visible; overflow-x: auto; }
      th, td { padding: 6px 6px; font-size: 10px; }
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
            <div class="nav" id="nav"></div>
          </div>
        </div>
      </header>

      <p class="page-subtitle">{{T_details_note}}</p>

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
      const back = `<a href="/">${esc(T.link_back_home)}</a>`;
      try {
        const me = await (await fetch('/api/me')).json();
        if (me.username) {
          nav.innerHTML = back + ls + `<span style="font-size:10px;letter-spacing:1px;color:var(--muted)">👤 ${esc(me.username)}</span>
            <a href="/account">${esc(T.nav_account)}</a>
            <form method="post" action="/logout"><button type="submit">${esc(T.nav_logout)}</button></form>`;
        } else {
          nav.innerHTML = back + ls + `<a href="/login">${esc(T.nav_login)}</a>`;
        }
      } catch { nav.innerHTML = back + ls + `<a href="/login">${esc(T.nav_login)}</a>`; }
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
      height: 100vh; height: 100dvh; overflow-y: auto; overflow-x: hidden;
      scrollbar-width: thin; scrollbar-color: var(--x-muted) transparent;
    }
    .container::-webkit-scrollbar { width: 6px; }
    .container::-webkit-scrollbar-thumb { background: rgba(127,255,212,0.15); border-radius: 3px; }
    .inner { max-width: 1320px; margin: 0 auto; padding: 24px 32px calc(80px + env(safe-area-inset-bottom)); }

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
    .page-subtitle { margin: 0 0 18px; font-size: 12px; line-height: 1.7;
      letter-spacing: 0.5px; color: var(--muted); max-width: 720px; }
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
      .inner { position: relative; padding: 44px 16px calc(100px + env(safe-area-inset-bottom)); }
      .lang-switch {
        position: absolute; top: 12px; right: 12px; z-index: 5;
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

      <p class="page-subtitle">{{T_home_subtitle}}</p>

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
      const links = `<a href="/map">${esc(T.nav_map)}</a><a href="/stats">${esc(T.nav_stats)}</a><a href="/details">${esc(T.nav_details)}</a><a href="/about">${esc(T.nav_about)}</a>`;
      try {
        const me = await (await fetch('/api/me')).json();
        if (me.username) {
          nav.innerHTML = ls + links + `<a href="/account">${esc(me.username)}</a>` +
            `<form method="post" action="/logout"><button type="submit">${esc(T.nav_logout)}</button></form>`;
        } else {
          nav.innerHTML = ls + links + `<a href="/login">${esc(T.nav_login)}</a>`;
        }
      } catch { nav.innerHTML = ls + links; }
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


def query_stats():
    today_jst = datetime.now(JST).date()
    start_day = today_jst - timedelta(days=6)

    conn = connect()
    cur = dict_cursor(conn)

    days = [(start_day + timedelta(days=i)).isoformat() for i in range(7)]
    histogram = []
    for d in days:
        cur.execute(
            'SELECT COUNT(*) AS t FROM aircraft_passes WHERE pass_date = %s',
            (d,),
        )
        histogram.append({'day': d, 'count': cur.fetchone()['t']})

    start_date = start_day.isoformat()
    end_date = today_jst.isoformat()

    def top10(col, from_passes=False):
        # operator 喺 passes 表自己有；type/from/to 要 JOIN registry
        if from_passes:
            cur.execute(
                f'''
                SELECT COALESCE(NULLIF(TRIM(p.{col}), ''), '(unknown)') AS k,
                       COUNT(*) AS cnt
                FROM aircraft_passes p
                WHERE p.pass_date >= %s AND p.pass_date <= %s
                GROUP BY COALESCE(NULLIF(TRIM(p.{col}), ''), '(unknown)')
                ORDER BY cnt DESC, k ASC
                LIMIT 10
                ''',
                (start_date, end_date),
            )
        else:
            cur.execute(
                f'''
                SELECT COALESCE(NULLIF(TRIM(c.{col}), ''), '(unknown)') AS k,
                       COUNT(*) AS cnt
                FROM aircraft_passes p
                LEFT JOIN aircraft_registry_cache c ON c.icao = p.icao
                WHERE p.pass_date >= %s AND p.pass_date <= %s
                GROUP BY COALESCE(NULLIF(TRIM(c.{col}), ''), '(unknown)')
                ORDER BY cnt DESC, k ASC
                LIMIT 10
                ''',
                (start_date, end_date),
            )
        return [{'name': r['k'], 'count': r['cnt']} for r in cur.fetchall()]

    top_types = top10('aircraft_type')
    top_ops = top10('operator', from_passes=True)
    top_from = top10('from_airport')
    top_to = top10('to_airport')

    cur.execute('SELECT COUNT(*) AS t FROM aircraft_passes')
    db_total = cur.fetchone()['t']

    cur.execute(
        '''SELECT COUNT(DISTINCT TRIM(aircraft_type)) AS t
           FROM aircraft_registry_cache
           WHERE aircraft_type IS NOT NULL AND TRIM(aircraft_type) <> ''
        '''
    )
    db_types = cur.fetchone()['t']

    # 最高高度（全 DB），順手帶返係邊班機飛到
    cur.execute(
        '''SELECT max_alt_baro AS alt, flight
           FROM aircraft_passes
           WHERE max_alt_baro IS NOT NULL
           ORDER BY max_alt_baro DESC
           LIMIT 1'''
    )
    row = cur.fetchone()
    peak_alt = {'alt': row['alt'], 'flight': row['flight']} if row else None

    # 最繁忙時段：first_seen（UTC）+9 小時轉 JST，按小時 group
    cur.execute(
        '''SELECT HOUR(DATE_ADD(
                     STR_TO_DATE(SUBSTRING(first_seen, 1, 19), '%Y-%m-%dT%H:%i:%s'),
                     INTERVAL 9 HOUR)) AS hr,
                  COUNT(*) AS cnt
           FROM aircraft_passes
           GROUP BY hr
           ORDER BY cnt DESC, hr ASC
           LIMIT 1'''
    )
    row = cur.fetchone()
    busiest_hour = (
        {'hour': row['hr'], 'count': row['cnt']}
        if row and row['hr'] is not None else None
    )

    # 近 24 小時（rolling window）每個鐘頭嘅便数推移，
    # oldest → newest 排，最後一條 = 而家所在嘅鐘頭（前端會 highlight）
    now_utc = datetime.now(timezone.utc)
    window_start = now_utc - timedelta(hours=24)
    cur.execute(
        'SELECT first_seen FROM aircraft_passes WHERE first_seen >= %s',
        (window_start.isoformat(),),
    )
    cur_hour = now_utc.astimezone(JST).replace(minute=0, second=0, microsecond=0)
    starts = [cur_hour - timedelta(hours=23 - i) for i in range(24)]
    counts = {s: 0 for s in starts}
    for r in cur.fetchall():
        try:
            slot = (datetime.fromisoformat(r['first_seen'])
                    .astimezone(JST)
                    .replace(minute=0, second=0, microsecond=0))
        except (ValueError, TypeError):
            continue
        if slot in counts:
            counts[slot] += 1
    hourly = [
        {'hour': s.hour, 'count': counts[s], 'current': (s == cur_hour)}
        for s in starts
    ]

    conn.close()
    return {
        'histogram': histogram,
        'top_types': top_types,
        'top_ops': top_ops,
        'top_from': top_from,
        'top_to': top_to,
        'db_total': db_total,
        'db_types': db_types,
        'peak_alt': peak_alt,
        'busiest_hour': busiest_hour,
        'hourly': hourly,
    }


def _receiver_snapshot():
    """共用：最後一筆 sample 幾耐之前（秒）同今日 pass 數。會 raise 如果 DB connect 唔到。"""
    conn = connect()
    cur = dict_cursor(conn)
    cur.execute('SELECT MAX(seen_at) AS ts FROM sightings_raw')
    row = cur.fetchone()
    today_jst = datetime.now(JST).strftime('%Y-%m-%d')
    cur.execute('SELECT COUNT(*) AS c FROM aircraft_passes WHERE pass_date = %s', (today_jst,))
    records_today = cur.fetchone()['c']
    conn.close()

    last_secs = None
    if row and row['ts']:
        try:
            last_dt = datetime.fromisoformat(row['ts'])
            last_secs = max(0, int((datetime.now(timezone.utc) - last_dt).total_seconds()))
        except ValueError:
            last_secs = None
    return last_secs, records_today


def _feed_health(last_secs):
    # pipeline 每 60 秒 run 一次，180 秒內當正常、900 秒內當遲、再耐就當停
    if last_secs is None:
        return 'down'
    if last_secs <= 180:
        return 'ok'
    if last_secs <= 900:
        return 'stale'
    return 'down'


def query_about():
    # 接收機 / feed 健康狀態，畀 /about 頁顯示
    last_secs, records_today = _receiver_snapshot()
    uptime_secs = (datetime.now(timezone.utc) - _BOOT_AT).total_seconds()
    return {
        'receiver': 'Oku Home RX',
        'source': 'Pi / dump1090 / readsb',
        'uptime_secs': int(uptime_secs),
        'last_update_secs': last_secs,
        'feed_health': _feed_health(last_secs),
        'records_today': records_today,
    }


def query_health():
    """畀 /api/health 用嘅 monitoring endpoint。回 (payload, http_status)。"""
    db_ok = True
    last_secs = None
    records_today = None
    try:
        last_secs, records_today = _receiver_snapshot()
    except Exception:
        db_ok = False

    receiver = _feed_health(last_secs) if db_ok else 'down'
    # 服務本身健唔健康 = API 起到 + DB 連到。Receiver 遲/停當 degraded，唔當 503。
    healthy = db_ok
    payload = {
        'status': 'ok' if healthy else 'error',
        'api': 'ok',
        'db': 'ok' if db_ok else 'down',
        'receiver': receiver,
        'receiver_last_seen_secs': last_secs,
        'records_today': records_today,
        'uptime_secs': int((datetime.now(timezone.utc) - _BOOT_AT).total_seconds()),
    }
    return payload, (200 if healthy else 503)


def query_live():
    # server 端即時抓 tar1090 aircraft.json，trim 返有定位嘅機畀地圖
    if not _SOURCE_URL:
        return {'aircraft': [], 'error': 'no source url', 'count_pos': 0, 'count_total': 0}
    try:
        with urllib.request.urlopen(_SOURCE_URL, timeout=8) as resp:
            payload = json.loads(resp.read().decode('utf-8'))
    except Exception as e:
        return {'aircraft': [], 'error': str(e), 'count_pos': 0, 'count_total': 0}

    raw = payload.get('aircraft', []) or []
    out = []
    for a in raw:
        lat, lon = a.get('lat'), a.get('lon')
        if lat is None or lon is None:
            continue
        alt = a.get('alt_baro')
        if isinstance(alt, str):  # tar1090 落地會送 "ground"
            alt = None
        rate = a.get('baro_rate')
        if rate is None:
            rate = a.get('geom_rate')
        out.append({
            'hex': (a.get('hex') or '').strip().lower(),
            'flight': (a.get('flight') or '').strip() or None,
            'lat': lat,
            'lon': lon,
            'alt': alt,
            'rate': rate,
            'track': a.get('track'),
            'gs': a.get('gs'),
        })

    # 由 registry cache 補返機牌 / 機型 / 公司 / 國家 / 航線，click 個 popup 用
    def _clean(v):
        v = (v or '').strip() if isinstance(v, str) else None
        return v if v and v.lower() != 'n/a' else None
    hexes = [o['hex'] for o in out if o['hex']]
    if hexes:
        try:
            conn = connect()
            cur = dict_cursor(conn)
            ph = ','.join(['%s'] * len(hexes))
            cur.execute(
                f'''SELECT icao, registration, country, aircraft_type, operator, from_airport, to_airport
                    FROM aircraft_registry_cache WHERE icao IN ({ph})''',
                hexes,
            )
            reg = {r['icao']: r for r in cur.fetchall()}
            conn.close()
            for o in out:
                m = reg.get(o['hex'])
                if m:
                    o['reg'] = _clean(m.get('registration'))
                    o['type'] = _clean(m.get('aircraft_type'))
                    o['operator'] = _clean(m.get('operator'))
                    o['country'] = _clean(m.get('country'))
                    o['from'] = _clean(m.get('from_airport'))
                    o['to'] = _clean(m.get('to_airport'))
        except Exception:
            pass

    return {
        'aircraft': out,
        'count_pos': len(out),
        'count_total': len(raw),
        'now': payload.get('now'),
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


STATS_HTML = '''<!doctype html>
<html lang="{{HTML_LANG}}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{{T_stats_title}}</title>
  <link rel="icon" type="image/svg+xml" href="/favicon.svg">
  <style>
    :root {
      --bg:#050a0d; --mint:#7fffd4; --mint-light:#aafff0; --amber:#f5d96f;
      --muted:#4a8a7a; --x-muted:#3a6a5a;
      --card:rgba(15,31,34,0.7); --card-body:rgba(10,20,22,0.7);
      --hdr-bar:rgba(15,31,34,0.85);
      --border:0.5px solid rgba(127,255,212,0.15);
      --row-div:0.5px solid rgba(127,255,212,0.05);
    }
    * { box-sizing: border-box; }
    html, body { margin:0; padding:0; height:100%;
      background: var(--bg); color: var(--mint);
      font-family:'SF Mono','Menlo','Courier New',monospace;
      -webkit-font-smoothing:antialiased;
    }
    body { overflow:hidden; }
    #radar { position:fixed; inset:0; z-index:0; width:100vw; height:100vh; }
    .bg-vignette { position:fixed; inset:0; z-index:1; pointer-events:none;
      background: radial-gradient(ellipse at center, transparent 35%, rgba(5,10,13,0.85) 95%); }

    .container { position:relative; z-index:2; height:100vh; height:100dvh;
      overflow-y:auto; overflow-x:hidden;
      scrollbar-width:thin; scrollbar-color:var(--x-muted) transparent; }
    .container::-webkit-scrollbar { width:6px; }
    .container::-webkit-scrollbar-thumb { background:rgba(127,255,212,0.15); border-radius:3px; }
    .inner { max-width:1320px; margin:0 auto;
      padding: 24px 32px calc(80px + env(safe-area-inset-bottom)); }

    header.page-hdr { padding-bottom:14px; margin-bottom:18px;
      border-bottom:1px solid rgba(127,255,212,0.15); }
    .hdr-row { display:flex; align-items:center; justify-content:space-between; gap:16px; }
    .hdr-row.top { font-size:10px; letter-spacing:3px; color:var(--muted); text-transform:uppercase; }
    .hdr-row.top .dot { color:var(--mint); animation:blink 2s infinite; margin-right:4px; }
    @keyframes blink { 50% { opacity:0.35 } }
    .hdr-row.main { margin:6px 0 4px; }
    .hdr-row.main .title { font-size:22px; letter-spacing:1px; color:var(--mint); font-weight:500; margin:0; }
    .hdr-row.main .title a { color:inherit; text-decoration:none; }
    .hdr-row.main .clock { font-size:16px; color:var(--mint); letter-spacing:1px; }
    .hdr-row.sub { font-size:10px; letter-spacing:2px; color:var(--x-muted); }
    .hdr-row.sub .coords { text-transform:uppercase; }
    .tools { display:flex; gap:6px; align-items:center; }
    .tools .nav a, .tools .nav button {
      background:rgba(15,31,34,0.6); color:var(--mint);
      border:var(--border); border-radius:4px;
      font:inherit; font-size:10px; letter-spacing:1.5px;
      padding:6px 10px; outline:none; cursor:pointer;
      text-decoration:none;
    }
    .tools .nav a:hover, .tools .nav button:hover { color:var(--mint); border-color:var(--mint); }
    .nav { display:flex; gap:4px; align-items:center; }
    .nav form { display:inline; margin:0; }
    .lang-switch { display:inline-flex; gap:2px; margin-right:4px; }
    .lang-switch a { color:var(--muted); text-decoration:none; font-size:10px;
      padding:5px 8px; border:var(--border); border-radius:4px;
      letter-spacing:0.1em; background:rgba(15,31,34,0.6); }
    .lang-switch a.on { color:var(--mint); border-color:var(--mint); }

    .page-subtitle { margin:0 0 18px; font-size:12px; line-height:1.7;
      letter-spacing:0.5px; color:var(--muted); max-width:720px; }
    .summary { display:grid; grid-template-columns:repeat(2, 1fr); gap:12px; margin-bottom:18px; }
    .stat-big {
      background:var(--card); backdrop-filter:blur(8px);
      border:var(--border); border-radius:4px; padding:16px 18px;
    }
    .stat-big .lbl { font-size:10px; letter-spacing:2px; color:var(--muted);
      margin-bottom:8px; text-transform:uppercase; }
    .stat-big .val { font-size:32px; font-weight:500; color:var(--mint); line-height:1;
      letter-spacing:1px; }
    .stat-big .sub { font-size:10px; letter-spacing:1px; color:var(--x-muted);
      margin-top:7px; min-height:11px; }

    section.panel { margin-bottom:18px; }
    .panel-hdr {
      background:var(--hdr-bar); backdrop-filter:blur(8px);
      border:var(--border); border-radius:4px 4px 0 0;
      padding:10px 14px; font-size:11px; letter-spacing:2px;
      color:var(--amber); text-transform:uppercase;
    }
    .panel-hdr .diamond { color:var(--amber); margin-right:6px; }
    .panel-body {
      background:var(--card-body); backdrop-filter:blur(8px);
      border:var(--border); border-top:0;
      border-radius:0 0 4px 4px;
      padding:14px;
    }

    /* histogram */
    .hist { display:grid; grid-template-columns:repeat(7, 1fr); gap:8px; align-items:end; }
    .hist .bar-wrap { display:flex; flex-direction:column; align-items:center; gap:6px; }
    .hist .bar-area { width:100%; height:140px; display:flex; align-items:flex-end; }
    .hist .bar {
      width:100%; min-height:2px; border-radius:2px 2px 0 0;
      background:linear-gradient(180deg, var(--mint) 0%, rgba(127,255,212,0.35) 100%);
    }
    .hist .day { font-size:9px; letter-spacing:1px; color:var(--x-muted); text-transform:uppercase; }
    .hist .val { font-size:11px; color:var(--mint); }
    .hist24 { grid-template-columns:repeat(24, 1fr); gap:2px; }
    .hist24 .bar-wrap { gap:4px; }
    .hist24 .bar-area { height:110px; }
    .hist24 .val { font-size:8px; letter-spacing:0; }
    .hist24 .day { font-size:8px; letter-spacing:0; }
    /* 而家所在嗰個鐘頭：轉琥珀色 */
    .hist24 .bar.now { background:linear-gradient(180deg, var(--amber) 0%, rgba(245,217,111,0.35) 100%); }
    .hist24 .bar-wrap.now .day, .hist24 .bar-wrap.now .val { color:var(--amber); }

    /* top-10 lists */
    .row-2col { display:grid; grid-template-columns:1fr 1fr; gap:14px; }
    .row-2col section.panel { margin-bottom:0; }
    .top10 { display:flex; flex-direction:column; }
    .top10 .row {
      display:grid; grid-template-columns:24px 1fr 60px;
      gap:10px; align-items:center;
      padding:7px 0; font-size:11px;
      border-bottom:var(--row-div);
    }
    .top10 .row:last-child { border-bottom:0; }
    .top10 .rank { color:var(--x-muted); font-size:10px; text-align:right; }
    .top10 .name { color:var(--mint-light); overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
    .top10 .cnt { color:var(--amber); text-align:right; }
    .top10 .cols {
      display:grid; grid-template-columns:24px 1fr 60px;
      gap:10px;
      font-size:9px; letter-spacing:1.5px; color:var(--x-muted);
      padding:6px 0; border-bottom:0.5px solid rgba(127,255,212,0.1);
      text-transform:uppercase;
    }
    .top10 .cols .r { text-align:right; }
    .top10 .cols .c { text-align:right; }

    .loading { font-size:11px; color:var(--muted); letter-spacing:1.5px; padding:24px; text-align:center; }

    .page-footer { margin-top:36px; padding-top:22px;
      border-top:var(--border); text-align:center;
      font-size:9px; letter-spacing:3px; color:var(--x-muted); text-transform:uppercase; }

    @media (max-width:700px) {
      .inner { position:relative; padding:44px 16px calc(100px + env(safe-area-inset-bottom)); }
      .hdr-row.top { font-size:9px; letter-spacing:1.5px; }
      .hdr-row.main { flex-wrap:wrap; }
      .hdr-row.main .title { font-size:16px; letter-spacing:0.5px; }
      .hdr-row.main .clock { font-size:13px; }
      .hdr-row.sub .coords { display:none; }
      .hdr-row.sub { justify-content:flex-end; }
      .tools .nav > span:not(.lang-switch) { display:none; }
      .tools { justify-content:flex-end; gap:4px; flex-wrap:wrap; }
      .tools .nav { justify-content:flex-end; gap:4px; }
      .tools .nav a, .tools .nav button { padding:5px 8px; font-size:10px; letter-spacing:1px; }
      .lang-switch {
        position:absolute; top:12px; right:12px; z-index:5;
        margin:0; gap:4px;
        background:rgba(5,10,13,0.85); padding:4px; border-radius:4px;
      }
      .lang-switch a { padding:5px 8px; font-size:10px; }
      .row-2col { grid-template-columns:1fr; }
      .stat-big .val { font-size:24px; }
      .hist .bar-area { height:100px; }
      .hist .day { font-size:8px; letter-spacing:0; }
      .hist24 .val { display:none; }
      .hist24 .bar-area { height:80px; }
    }
  </style>
</head>
<body>
  <canvas id="radar"></canvas>
  <div class="bg-vignette"></div>
  <div class="container">
    <div class="inner">
      <header class="page-hdr">
        <div class="hdr-row top">
          <span><span class="dot">◉</span> LIVE · ADS-B · HOME RX</span>
          <span id="date">— — —</span>
        </div>
        <div class="hdr-row main">
          <h1 class="title"><a href="/">尾久 SKYLEDGER · TOKYO</a></h1>
          <span class="clock" id="clock">--:--:--</span>
        </div>
        <div class="hdr-row sub">
          <span class="coords">Powered by connie.hk</span>
          <div class="tools"><div class="nav" id="nav"></div></div>
        </div>
      </header>

      <p class="page-subtitle">{{T_stats_note}}</p>

      <section class="summary">
        <div class="stat-big">
          <div class="lbl">{{T_stats_hdr_db_total}}</div>
          <div class="val" id="db-total">—</div>
        </div>
        <div class="stat-big">
          <div class="lbl">{{T_stats_hdr_db_types}}</div>
          <div class="val" id="db-types">—</div>
        </div>
        <div class="stat-big">
          <div class="lbl">{{T_stats_hdr_peak_alt}}</div>
          <div class="val" id="peak-alt">—</div>
          <div class="sub" id="peak-alt-sub"></div>
        </div>
        <div class="stat-big">
          <div class="lbl">{{T_stats_hdr_busiest_hour}}</div>
          <div class="val" id="busiest-hour">—</div>
          <div class="sub" id="busiest-hour-sub"></div>
        </div>
      </section>

      <section class="panel">
        <div class="panel-hdr"><span class="diamond">◆</span>{{T_stats_hdr_7d_hist}}</div>
        <div class="panel-body">
          <div class="hist" id="hist"><div class="loading">{{T_loading}}</div></div>
        </div>
      </section>

      <section class="panel">
        <div class="panel-hdr"><span class="diamond">◆</span>{{T_stats_hdr_24h_hist}}</div>
        <div class="panel-body">
          <div class="hist hist24" id="hist24"><div class="loading">{{T_loading}}</div></div>
        </div>
      </section>

      <div class="row-2col">
        <section class="panel">
          <div class="panel-hdr"><span class="diamond">◆</span>{{T_stats_hdr_7d_types}}</div>
          <div class="panel-body"><div class="top10" id="top-types"><div class="loading">{{T_loading}}</div></div></div>
        </section>
        <section class="panel">
          <div class="panel-hdr"><span class="diamond">◆</span>{{T_stats_hdr_7d_ops}}</div>
          <div class="panel-body"><div class="top10" id="top-ops"><div class="loading">{{T_loading}}</div></div></div>
        </section>
        <section class="panel">
          <div class="panel-hdr"><span class="diamond">◆</span>{{T_stats_hdr_7d_from}}</div>
          <div class="panel-body"><div class="top10" id="top-from"><div class="loading">{{T_loading}}</div></div></div>
        </section>
        <section class="panel">
          <div class="panel-hdr"><span class="diamond">◆</span>{{T_stats_hdr_7d_to}}</div>
          <div class="panel-body"><div class="top10" id="top-to"><div class="loading">{{T_loading}}</div></div></div>
        </section>
      </div>

      <footer class="page-footer">尾久 SKYLEDGER · TOKYO<br><span style="color:var(--x-muted);font-size:8px;letter-spacing:2px">Powered by connie.hk</span></footer>
    </div>
  </div>

  <script type="module">
    import * as THREE from 'https://unpkg.com/three@0.160.0/build/three.module.js';
    const T = {{T_JSDICT}};
    const LANG = '{{LANG}}';
    const pad = n => String(n).padStart(2, '0');
    const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

    function getJST() { const n = new Date(); return new Date(n.getTime() + 9*3600*1000); }
    function updateClock() {
      const j = getJST();
      document.getElementById('clock').textContent =
        `${pad(j.getUTCHours())}:${pad(j.getUTCMinutes())}:${pad(j.getUTCSeconds())} JPT`;
      const wd = ['SUN','MON','TUE','WED','THU','FRI','SAT'][j.getUTCDay()];
      document.getElementById('date').textContent =
        `${j.getUTCFullYear()}.${pad(j.getUTCMonth()+1)}.${pad(j.getUTCDate())} · ${wd}`;
    }
    setInterval(updateClock, 1000); updateClock();

    function setLang(l) {
      document.cookie = `lang=${l}; Path=/; Max-Age=31536000; SameSite=Lax`;
      location.reload();
    }
    window.setLang = setLang;

    function langSwitchHTML() {
      const labels = { jp:'JP', hk:'HK', en:'EN' };
      return '<span class="lang-switch">' +
        ['jp','hk','en'].map(l =>
          `<a href="#" onclick="setLang('${l}');return false" class="${l===LANG?'on':''}">${labels[l]}</a>`
        ).join('') + '</span>';
    }
    async function renderNav() {
      const nav = document.getElementById('nav');
      const ls = langSwitchHTML();
      const back = `<a href="/">${esc(T.link_back_home)}</a>`;
      try {
        const me = await (await fetch('/api/me')).json();
        if (me.username) {
          nav.innerHTML = back + ls +
            `<span style="font-size:10px;letter-spacing:1px;color:var(--muted)">👤 ${esc(me.username)}</span>` +
            `<a href="/account">${esc(T.nav_account)}</a>` +
            `<form method="post" action="/logout"><button type="submit">${esc(T.nav_logout)}</button></form>`;
        } else {
          nav.innerHTML = back + ls + `<a href="/login">${esc(T.nav_login)}</a>`;
        }
      } catch { nav.innerHTML = back + ls + `<a href="/login">${esc(T.nav_login)}</a>`; }
    }
    renderNav();

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

    function renderHist(hist) {
      const el = document.getElementById('hist');
      if (!hist || !hist.length) { el.innerHTML = '<div class="loading">— —</div>'; return; }
      const max = Math.max(1, ...hist.map(h => h.count));
      el.innerHTML = hist.map(h => {
        const pct = (h.count / max * 100).toFixed(1);
        const md = h.day.slice(5);
        return `<div class="bar-wrap">
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
        // 每條 bar 都標鐘頭刻度，唔會走位；個數放 title tooltip
        const valTxt = h.count ? h.count : '';
        const now = h.current ? ' now' : '';
        return `<div class="bar-wrap${now}" title="${pad(h.hour)}:00 · ${h.count}">
          <div class="val">${valTxt}</div>
          <div class="bar-area"><div class="bar${now}" style="height:${pct}%"></div></div>
          <div class="day">${pad(h.hour)}</div>
        </div>`;
      }).join('');
    }

    async function load() {
      try {
        const r = await (await fetch('/api/stats')).json();
        document.getElementById('db-total').textContent = r.db_total;
        document.getElementById('db-types').textContent = r.db_types;
        if (r.peak_alt && r.peak_alt.alt != null) {
          document.getElementById('peak-alt').textContent = Math.round(r.peak_alt.alt).toLocaleString() + ' ft';
          const fl = r.peak_alt.flight ? r.peak_alt.flight.trim() : '';
          document.getElementById('peak-alt-sub').textContent = fl ? '✈ ' + fl : '';
        }
        if (r.busiest_hour && r.busiest_hour.hour != null) {
          const h = r.busiest_hour.hour;
          document.getElementById('busiest-hour').textContent = pad(h) + ':00–' + pad((h + 1) % 24) + ':00';
          document.getElementById('busiest-hour-sub').textContent = r.busiest_hour.count + ' ' + T.stats_col_aircraft;
        }
        renderHist(r.histogram);
        renderHist24(r.hourly);
        renderTop('top-types', r.top_types);
        renderTop('top-ops', r.top_ops);
        renderTop('top-from', r.top_from);
        renderTop('top-to', r.top_to);
      } catch (e) {
        document.getElementById('hist').innerHTML = '<div class="loading">error: ' + esc(String(e)) + '</div>';
      }
    }
    load();

    // ===== radar background =====
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
  </script>
</body>
</html>'''


ABOUT_HTML = '''<!doctype html>
<html lang="{{HTML_LANG}}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{{T_about_title}}</title>
  <link rel="icon" type="image/svg+xml" href="/favicon.svg">
  <style>
    :root {
      --bg:#050a0d; --mint:#7fffd4; --mint-light:#aafff0; --amber:#f5d96f;
      --muted:#4a8a7a; --x-muted:#3a6a5a; --warn:#ff7a59; --warn-light:#ff9a80;
      --card:rgba(15,31,34,0.7); --card-body:rgba(10,20,22,0.7);
      --hdr-bar:rgba(15,31,34,0.85);
      --border:0.5px solid rgba(127,255,212,0.15);
      --row-div:0.5px solid rgba(127,255,212,0.05);
    }
    * { box-sizing: border-box; }
    html, body { margin:0; padding:0; height:100%;
      background: var(--bg); color: var(--mint);
      font-family:'SF Mono','Menlo','Courier New',monospace;
      -webkit-font-smoothing:antialiased;
    }
    body { overflow:hidden; }
    #radar { position:fixed; inset:0; z-index:0; width:100vw; height:100vh; }
    .bg-vignette { position:fixed; inset:0; z-index:1; pointer-events:none;
      background: radial-gradient(ellipse at center, transparent 35%, rgba(5,10,13,0.85) 95%); }

    .container { position:relative; z-index:2; height:100vh; height:100dvh;
      overflow-y:auto; overflow-x:hidden;
      scrollbar-width:thin; scrollbar-color:var(--x-muted) transparent; }
    .container::-webkit-scrollbar { width:6px; }
    .container::-webkit-scrollbar-thumb { background:rgba(127,255,212,0.15); border-radius:3px; }
    .inner { max-width:1320px; margin:0 auto;
      padding: 24px 32px calc(80px + env(safe-area-inset-bottom)); }

    header.page-hdr { padding-bottom:14px; margin-bottom:18px;
      border-bottom:1px solid rgba(127,255,212,0.15); }
    .hdr-row { display:flex; align-items:center; justify-content:space-between; gap:16px; }
    .hdr-row.top { font-size:10px; letter-spacing:3px; color:var(--muted); text-transform:uppercase; }
    .hdr-row.top .dot { color:var(--mint); animation:blink 2s infinite; margin-right:4px; }
    @keyframes blink { 50% { opacity:0.35 } }
    .hdr-row.main { margin:6px 0 4px; }
    .hdr-row.main .title { font-size:22px; letter-spacing:1px; color:var(--mint); font-weight:500; margin:0; }
    .hdr-row.main .title a { color:inherit; text-decoration:none; }
    .hdr-row.main .clock { font-size:16px; color:var(--mint); letter-spacing:1px; }
    .hdr-row.sub { font-size:10px; letter-spacing:2px; color:var(--x-muted); }
    .hdr-row.sub .coords { text-transform:uppercase; }
    .tools { display:flex; gap:6px; align-items:center; }
    .tools .nav a, .tools .nav button {
      background:rgba(15,31,34,0.6); color:var(--mint);
      border:var(--border); border-radius:4px;
      font:inherit; font-size:10px; letter-spacing:1.5px;
      padding:6px 10px; outline:none; cursor:pointer; text-decoration:none;
    }
    .tools .nav a:hover, .tools .nav button:hover { color:var(--mint); border-color:var(--mint); }
    .nav { display:flex; gap:4px; align-items:center; }
    .nav form { display:inline; margin:0; }
    .lang-switch { display:inline-flex; gap:2px; margin-right:4px; }
    .lang-switch a { color:var(--muted); text-decoration:none; font-size:10px;
      padding:5px 8px; border:var(--border); border-radius:4px;
      letter-spacing:0.1em; background:rgba(15,31,34,0.6); }
    .lang-switch a.on { color:var(--mint); border-color:var(--mint); }

    section.panel { margin-bottom:18px; }
    .panel-hdr {
      background:var(--hdr-bar); backdrop-filter:blur(8px);
      border:var(--border); border-radius:4px 4px 0 0;
      padding:10px 14px; font-size:11px; letter-spacing:2px;
      color:var(--amber); text-transform:uppercase;
    }
    .panel-hdr .diamond { color:var(--amber); margin-right:6px; }
    .panel-body {
      background:var(--card-body); backdrop-filter:blur(8px);
      border:var(--border); border-top:0;
      border-radius:0 0 4px 4px; padding:14px 16px;
    }

    .about-grid { display:grid; grid-template-columns:1fr 1fr; gap:18px; align-items:start; }
    .about-grid section.panel { margin-bottom:18px; }

    /* receiver key-value */
    .kv { display:flex; flex-direction:column; }
    .kv .row { display:grid; grid-template-columns:150px 1fr; gap:12px;
      padding:10px 0; border-bottom:var(--row-div); font-size:12px; align-items:center; }
    .kv .row:last-child { border-bottom:0; }
    .kv .k { color:var(--muted); font-size:10px; letter-spacing:1.5px; text-transform:uppercase; }
    .kv .v { color:var(--mint-light); letter-spacing:0.5px; }
    .feed { display:inline-flex; align-items:center; gap:8px; letter-spacing:1.5px; }
    .feed .dot { width:8px; height:8px; border-radius:50%; display:inline-block; background:var(--x-muted); }
    .feed.ok { color:var(--mint); }
    .feed.ok .dot { background:var(--mint); box-shadow:0 0 8px var(--mint); animation:blink 2s infinite; }
    .feed.stale { color:var(--amber); }
    .feed.stale .dot { background:var(--amber); box-shadow:0 0 8px var(--amber); }
    .feed.down { color:var(--warn-light); }
    .feed.down .dot { background:var(--warn); box-shadow:0 0 8px var(--warn); }

    /* project description */
    .desc { font-size:13px; line-height:1.95; color:var(--mint-light); letter-spacing:0.4px; margin:2px 0 0; }
    .tags { display:flex; flex-wrap:wrap; gap:7px; margin-top:18px; }
    .tags span { font-size:10px; letter-spacing:1px; color:var(--mint);
      border:var(--border); border-radius:999px; padding:5px 11px;
      background:rgba(127,255,212,0.06); }

    /* architecture diagram */
    .arch { margin:0; overflow-x:auto; font-size:12.5px; line-height:1.5;
      color:var(--mint); white-space:pre; letter-spacing:0;
      font-family:'SF Mono','Menlo','Courier New',monospace; }

    .page-footer { margin-top:36px; padding-top:22px;
      border-top:var(--border); text-align:center;
      font-size:9px; letter-spacing:3px; color:var(--x-muted); text-transform:uppercase; }

    @media (max-width:700px) {
      .inner { position:relative; padding:44px 16px calc(100px + env(safe-area-inset-bottom)); }
      .hdr-row.top { font-size:9px; letter-spacing:1.5px; }
      .hdr-row.main { flex-wrap:wrap; }
      .hdr-row.main .title { font-size:16px; letter-spacing:0.5px; }
      .hdr-row.main .clock { font-size:13px; }
      .hdr-row.sub .coords { display:none; }
      .hdr-row.sub { justify-content:flex-end; }
      .tools { justify-content:flex-end; gap:4px; flex-wrap:wrap; }
      .tools .nav { justify-content:flex-end; gap:4px; }
      .tools .nav a, .tools .nav button { padding:5px 8px; font-size:10px; letter-spacing:1px; }
      .lang-switch {
        position:absolute; top:12px; right:12px; z-index:5; margin:0; gap:4px;
        background:rgba(5,10,13,0.85); padding:4px; border-radius:4px;
      }
      .lang-switch a { padding:5px 8px; font-size:10px; }
      .about-grid { grid-template-columns:1fr; gap:0; }
      .kv .row { grid-template-columns:120px 1fr; }
      .arch { font-size:10px; line-height:1.45; }
    }
  </style>
</head>
<body>
  <canvas id="radar"></canvas>
  <div class="bg-vignette"></div>
  <div class="container">
    <div class="inner">
      <header class="page-hdr">
        <div class="hdr-row top">
          <span><span class="dot">◉</span> LIVE · ADS-B · HOME RX</span>
          <span id="date">— — —</span>
        </div>
        <div class="hdr-row main">
          <h1 class="title"><a href="/">尾久 SKYLEDGER · TOKYO</a></h1>
          <span class="clock" id="clock">--:--:--</span>
        </div>
        <div class="hdr-row sub">
          <span class="coords">Powered by connie.hk</span>
          <div class="tools"><div class="nav" id="nav"></div></div>
        </div>
      </header>

      <div class="about-grid">
        <section class="panel">
          <div class="panel-hdr"><span class="diamond">◆</span>{{T_about_hdr_receiver}}</div>
          <div class="panel-body">
            <div class="kv">
              <div class="row"><div class="k">{{T_about_lbl_receiver}}</div><div class="v" id="ab-receiver">—</div></div>
              <div class="row"><div class="k">{{T_about_lbl_source}}</div><div class="v" id="ab-source">—</div></div>
              <div class="row"><div class="k">{{T_about_lbl_uptime}}</div><div class="v" id="ab-uptime">—</div></div>
              <div class="row"><div class="k">{{T_about_lbl_last_update}}</div><div class="v" id="ab-last">—</div></div>
              <div class="row"><div class="k">{{T_about_lbl_feed}}</div><div class="v"><span class="feed" id="ab-feed"><span class="dot"></span><span id="ab-feed-txt">—</span></span></div></div>
            </div>
          </div>
        </section>
        <section class="panel">
          <div class="panel-hdr"><span class="diamond">◆</span>{{T_about_hdr_project}}</div>
          <div class="panel-body">
            <p class="desc">{{T_about_desc}}</p>
            <div class="tags">
              <span>self-hosted</span><span>data ingestion</span><span>API</span><span>MySQL</span><span>dashboard</span><span>monitoring</span><span>real-time</span>
            </div>
          </div>
        </section>
      </div>

      <div class="about-grid">
        <section class="panel">
          <div class="panel-hdr"><span class="diamond">◆</span>{{T_about_hdr_health}}</div>
          <div class="panel-body">
            <div class="kv">
              <div class="row"><div class="k">{{T_about_lbl_api}}</div><div class="v"><span class="feed" id="hl-api"><span class="dot"></span><span id="hl-api-txt">—</span></span></div></div>
              <div class="row"><div class="k">{{T_about_lbl_db}}</div><div class="v"><span class="feed" id="hl-db"><span class="dot"></span><span id="hl-db-txt">—</span></span></div></div>
              <div class="row"><div class="k">{{T_about_lbl_last_update}}</div><div class="v" id="hl-last">—</div></div>
              <div class="row"><div class="k">{{T_about_lbl_records_today}}</div><div class="v" id="hl-records">—</div></div>
            </div>
          </div>
        </section>
        <section class="panel">
          <div class="panel-hdr"><span class="diamond">◆</span>{{T_about_hdr_stack}}</div>
          <div class="panel-body">
            <div class="kv">
              <div class="row"><div class="k">{{T_about_stack_frontend}}</div><div class="v">HTML / CSS / JavaScript</div></div>
              <div class="row"><div class="k">{{T_about_stack_backend}}</div><div class="v">Python http.server API</div></div>
              <div class="row"><div class="k">{{T_about_stack_db}}</div><div class="v">MySQL</div></div>
              <div class="row"><div class="k">{{T_about_stack_receiver}}</div><div class="v">Raspberry Pi 5B + dump1090 / readsb / tar1090</div></div>
              <div class="row"><div class="k">{{T_about_stack_deploy}}</div><div class="v">self-hosted server + HTTPS</div></div>
              <div class="row"><div class="k">{{T_about_stack_notify}}</div><div class="v">Telegram / LINE push</div></div>
            </div>
          </div>
        </section>
      </div>

      <section class="panel">
        <div class="panel-hdr"><span class="diamond">◆</span>{{T_about_hdr_arch}}</div>
        <div class="panel-body">
<pre class="arch">       (( o ))  ANTENNA · 1090 MHz
           │
           ▼
   ┌──────────────────────────┐
   │ Raspberry Pi 5B          │
   │ dump1090 / readsb        │
   │ tar1090  →  JSON feed    │
   └──────────────────────────┘
           │   HTTP poll · 60s
           ▼
   ┌──────────────────────────┐
   │ Ingest / API  (Python)   │
   │ stdlib http.server       │
   │ enrich → build_passes    │
   └──────────────────────────┘
           │
           ├──────────────►  MySQL  · history
           │
           ├──────────────►  Push   · Telegram / LINE
           │
           ▼
   ┌──────────────────────────┐
   │ Web dashboard            │
   │ / · /stats · /about      │
   └──────────────────────────┘</pre>
        </div>
      </section>

      <footer class="page-footer">尾久 SKYLEDGER · TOKYO<br><span style="color:var(--x-muted);font-size:8px;letter-spacing:2px">Powered by connie.hk</span></footer>
    </div>
  </div>

  <script type="module">
    import * as THREE from 'https://unpkg.com/three@0.160.0/build/three.module.js';
    const T = {{T_JSDICT}};
    const LANG = '{{LANG}}';
    const pad = n => String(n).padStart(2, '0');
    const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

    function getJST() { const n = new Date(); return new Date(n.getTime() + 9*3600*1000); }
    function updateClock() {
      const j = getJST();
      document.getElementById('clock').textContent =
        `${pad(j.getUTCHours())}:${pad(j.getUTCMinutes())}:${pad(j.getUTCSeconds())} JPT`;
      const wd = ['SUN','MON','TUE','WED','THU','FRI','SAT'][j.getUTCDay()];
      document.getElementById('date').textContent =
        `${j.getUTCFullYear()}.${pad(j.getUTCMonth()+1)}.${pad(j.getUTCDate())} · ${wd}`;
    }
    setInterval(updateClock, 1000); updateClock();

    function setLang(l) {
      document.cookie = `lang=${l}; Path=/; Max-Age=31536000; SameSite=Lax`;
      location.reload();
    }
    window.setLang = setLang;

    function langSwitchHTML() {
      const labels = { jp:'JP', hk:'HK', en:'EN' };
      return '<span class="lang-switch">' +
        ['jp','hk','en'].map(l =>
          `<a href="#" onclick="setLang('${l}');return false" class="${l===LANG?'on':''}">${labels[l]}</a>`
        ).join('') + '</span>';
    }
    async function renderNav() {
      const nav = document.getElementById('nav');
      const ls = langSwitchHTML();
      const links = `<a href="/">${esc(T.link_back_home)}</a><a href="/map">${esc(T.nav_map)}</a><a href="/stats">${esc(T.nav_stats)}</a><a href="/details">${esc(T.nav_details)}</a>`;
      try {
        const me = await (await fetch('/api/me')).json();
        if (me.username) {
          nav.innerHTML = ls + links +
            `<span style="font-size:10px;letter-spacing:1px;color:var(--muted)">👤 ${esc(me.username)}</span>` +
            `<a href="/account">${esc(T.nav_account)}</a>` +
            `<form method="post" action="/logout"><button type="submit">${esc(T.nav_logout)}</button></form>`;
        } else {
          nav.innerHTML = ls + links + `<a href="/login">${esc(T.nav_login)}</a>`;
        }
      } catch { nav.innerHTML = ls + links + `<a href="/login">${esc(T.nav_login)}</a>`; }
    }
    renderNav();

    function relTime(secs) {
      if (secs == null) return '—';
      let n, u;
      if (secs < 60) { n = secs; u = T.about_unit_sec; }
      else if (secs < 3600) { n = Math.floor(secs/60); u = T.about_unit_min; }
      else if (secs < 86400) { n = Math.floor(secs/3600); u = T.about_unit_hr; }
      else { n = Math.floor(secs/86400); u = T.about_unit_day; }
      return T.about_ago_fmt.replace('{n}', n).replace('{u}', u);
    }
    function uptimeFmt(secs) {
      const d = Math.floor(secs/86400), h = Math.floor((secs%86400)/3600), m = Math.floor((secs%3600)/60);
      if (d > 0) return `${d}d ${pad(h)}h`;
      if (h > 0) return `${h}h ${pad(m)}m`;
      return `${m}m`;
    }
    function setFeed(id, cls, txt) {
      document.getElementById(id).className = 'feed ' + cls;
      document.getElementById(id + '-txt').textContent = txt;
    }
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
      // 系統健康：個頁攞到 data 即係 API + DB 都 ok
      setFeed('hl-api', ok ? 'ok' : 'down', ok ? 'OK' : 'DOWN');
      setFeed('hl-db', ok ? 'ok' : 'down', ok ? 'OK' : 'DOWN');
      document.getElementById('hl-last').textContent = ok ? relTime(r.last_update_secs) : '—';
      document.getElementById('hl-records').textContent =
        (ok && r.records_today != null) ? r.records_today : '—';
    }
    loadAbout();
    setInterval(loadAbout, 5000);

    // ===== radar background =====
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
  </script>
</body>
</html>'''


MAP_HTML = '''<!doctype html>
<html lang="{{HTML_LANG}}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{{T_map_title}}</title>
  <link rel="icon" type="image/svg+xml" href="/favicon.svg">
  <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
  <style>
    :root {
      --bg:#050a0d; --mint:#7fffd4; --mint-light:#aafff0; --amber:#f5d96f;
      --muted:#4a8a7a; --x-muted:#3a6a5a;
      --card:rgba(15,31,34,0.85); --hdr-bar:rgba(15,31,34,0.85);
      --border:0.5px solid rgba(127,255,212,0.15);
    }
    * { box-sizing:border-box; }
    html, body { margin:0; padding:0; height:100%;
      background:var(--bg); color:var(--mint);
      font-family:'SF Mono','Menlo','Courier New',monospace;
      -webkit-font-smoothing:antialiased; overflow:hidden; }
    .wrap { display:flex; flex-direction:column; height:100vh; height:100dvh;
      padding:18px 22px calc(14px + env(safe-area-inset-bottom)); }

    header.page-hdr { padding-bottom:12px; margin-bottom:12px; flex:0 0 auto;
      border-bottom:1px solid rgba(127,255,212,0.15); }
    .hdr-row { display:flex; align-items:center; justify-content:space-between; gap:16px; }
    .hdr-row.top { font-size:10px; letter-spacing:3px; color:var(--muted); text-transform:uppercase; }
    .hdr-row.top .dot { color:var(--mint); animation:blink 2s infinite; margin-right:4px; }
    @keyframes blink { 50% { opacity:0.35 } }
    .hdr-row.main { margin:6px 0 4px; }
    .hdr-row.main .title { font-size:20px; letter-spacing:1px; color:var(--mint); font-weight:500; margin:0; }
    .hdr-row.main .title a { color:inherit; text-decoration:none; }
    .hdr-row.main .clock { font-size:15px; color:var(--mint); letter-spacing:1px; }
    .hdr-row.sub { font-size:10px; letter-spacing:2px; color:var(--x-muted); }
    .tools { display:flex; gap:6px; align-items:center; }
    .tools .nav a, .tools .nav button {
      background:rgba(15,31,34,0.6); color:var(--mint); border:var(--border); border-radius:4px;
      font:inherit; font-size:10px; letter-spacing:1.5px; padding:6px 10px; cursor:pointer; text-decoration:none; }
    .tools .nav a:hover, .tools .nav button:hover { border-color:var(--mint); }
    .nav { display:flex; gap:4px; align-items:center; }
    .nav form { display:inline; margin:0; }
    .lang-switch { display:inline-flex; gap:2px; margin-right:4px; }
    .lang-switch a { color:var(--muted); text-decoration:none; font-size:10px;
      padding:5px 8px; border:var(--border); border-radius:4px; background:rgba(15,31,34,0.6); }
    .lang-switch a.on { color:var(--mint); border-color:var(--mint); }

    .map-meta { flex:0 0 auto; display:flex; align-items:baseline; gap:12px; flex-wrap:wrap;
      margin-bottom:10px; }
    .map-meta .ttl { font-size:11px; letter-spacing:2px; color:var(--amber); text-transform:uppercase; }
    .map-meta .ttl .diamond { margin-right:6px; }
    .map-meta .cnt { font-size:11px; letter-spacing:1px; color:var(--mint); }
    .map-meta .note { font-size:10px; letter-spacing:0.5px; color:var(--x-muted); flex:1 1 240px; }

    #map { flex:1 1 auto; min-height:0; border:var(--border); border-radius:6px;
      background:#050a0d; }
    .leaflet-container { background:#050a0d; font-family:inherit; }
    .leaflet-control-attribution { background:rgba(5,10,13,0.7)!important; color:var(--x-muted)!important; font-size:9px; }
    .leaflet-control-attribution a { color:var(--muted)!important; }
    .leaflet-bar a { background:var(--card)!important; color:var(--mint)!important; border-color:rgba(127,255,212,0.2)!important; }

    .ac-icon { background:none; border:none; overflow:visible; }
    .ac-wrap { position:relative; width:26px; height:26px; }
    .ac { position:absolute; inset:0; transition:transform 0.4s linear; will-change:transform;
      transform-origin:50% 50%; filter:drop-shadow(0 0 4px rgba(127,255,212,0.55)); }
    /* label 跟住架機走但唔會跟住轉 */
    .ac-lbl { position:absolute; left:28px; top:50%; transform:translateY(-50%);
      white-space:nowrap; line-height:1.15; pointer-events:none; }
    .ac-lbl span { display:block;
      text-shadow:0 0 3px #050a0d, 0 0 2px #050a0d, 0 1px 2px #050a0d; }
    .ac-lbl .fl { font-size:10px; letter-spacing:0.5px; color:var(--mint-light); }
    .ac-lbl .al { font-size:9px; letter-spacing:0.5px; color:var(--amber); }
    .ac-tip { background:rgba(5,10,13,0.92)!important; border:var(--border)!important;
      color:var(--mint)!important; font-size:10px; letter-spacing:0.5px; border-radius:4px; }
    .ac-tip::before { display:none!important; }
    .ac-tip b { color:var(--mint-light); }
    .ac-tip .k { color:var(--x-muted); }

    /* click 落去嘅詳細 popup */
    .leaflet-popup-content-wrapper, .leaflet-popup-tip {
      background:rgba(8,16,18,0.97)!important; color:var(--mint)!important;
      border:var(--border); box-shadow:0 4px 20px rgba(0,0,0,0.55); border-radius:6px; }
    .leaflet-popup-content { margin:11px 13px; font-size:11px; line-height:1.3; min-width:190px; }
    .leaflet-popup-close-button { color:var(--muted)!important; }
    .pop-h { font-size:14px; color:var(--mint-light); letter-spacing:1px;
      margin-bottom:8px; padding-bottom:7px; border-bottom:var(--border); }
    .pop .pr { display:flex; justify-content:space-between; gap:16px; padding:3px 0; }
    .pop .pk { color:var(--x-muted); letter-spacing:1px; text-transform:uppercase; font-size:9px; white-space:nowrap; }
    .pop .pv { color:var(--mint-light); text-align:right; }
    .pop-link { display:inline-block; margin-top:9px; color:var(--amber);
      text-decoration:none; font-size:10px; letter-spacing:1px; }
    .pop-link:hover { text-decoration:underline; }

    @media (max-width:700px) {
      .wrap { padding:14px 12px calc(10px + env(safe-area-inset-bottom)); }
      .hdr-row.main .title { font-size:15px; }
      .hdr-row.sub .coords { display:none; }
      .map-meta .note { display:none; }
    }
  </style>
</head>
<body>
  <div class="wrap">
    <header class="page-hdr">
      <div class="hdr-row top">
        <span><span class="dot">◉</span> LIVE · ADS-B · HOME RX</span>
        <span id="date">— — —</span>
      </div>
      <div class="hdr-row main">
        <h1 class="title"><a href="/">尾久 SKYLEDGER · TOKYO</a></h1>
        <span class="clock" id="clock">--:--:--</span>
      </div>
      <div class="hdr-row sub">
        <span class="coords">Powered by connie.hk</span>
        <div class="tools"><div class="nav" id="nav"></div></div>
      </div>
    </header>

    <div class="map-meta">
      <span class="ttl"><span class="diamond">◆</span>{{T_map_hdr}}</span>
      <span class="cnt" id="cnt">— —</span>
      <span class="note">{{T_map_note}}</span>
    </div>

    <div id="map"></div>
  </div>

  <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
  <script>
    const T = {{T_JSDICT}};
    const LANG = '{{LANG}}';
    const pad = n => String(n).padStart(2, '0');
    const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

    function getJST() { const n = new Date(); return new Date(n.getTime() + 9*3600*1000); }
    function updateClock() {
      const j = getJST();
      document.getElementById('clock').textContent =
        `${pad(j.getUTCHours())}:${pad(j.getUTCMinutes())}:${pad(j.getUTCSeconds())} JPT`;
      const wd = ['SUN','MON','TUE','WED','THU','FRI','SAT'][j.getUTCDay()];
      document.getElementById('date').textContent =
        `${j.getUTCFullYear()}.${pad(j.getUTCMonth()+1)}.${pad(j.getUTCDate())} · ${wd}`;
    }
    setInterval(updateClock, 1000); updateClock();

    function setLang(l) {
      document.cookie = `lang=${l}; Path=/; Max-Age=31536000; SameSite=Lax`;
      location.reload();
    }
    window.setLang = setLang;
    function langSwitchHTML() {
      const labels = { jp:'JP', hk:'HK', en:'EN' };
      return '<span class="lang-switch">' +
        ['jp','hk','en'].map(l => `<a href="#" onclick="setLang('${l}');return false" class="${l===LANG?'on':''}">${labels[l]}</a>`).join('') + '</span>';
    }
    async function renderNav() {
      const nav = document.getElementById('nav');
      const ls = langSwitchHTML();
      const links = `<a href="/">${esc(T.link_back_home)}</a><a href="/stats">${esc(T.nav_stats)}</a><a href="/details">${esc(T.nav_details)}</a><a href="/about">${esc(T.nav_about)}</a>`;
      try {
        const me = await (await fetch('/api/me')).json();
        if (me.username) {
          nav.innerHTML = ls + links + `<a href="/account">${esc(T.nav_account)}</a>` +
            `<form method="post" action="/logout"><button type="submit">${esc(T.nav_logout)}</button></form>`;
        } else { nav.innerHTML = ls + links + `<a href="/login">${esc(T.nav_login)}</a>`; }
      } catch { nav.innerHTML = ls + links + `<a href="/login">${esc(T.nav_login)}</a>`; }
    }
    renderNav();

    // ===== Leaflet 地圖 =====
    const map = L.map('map', { zoomControl:true, attributionControl:true, worldCopyJump:true })
      .setView([35.68, 139.76], 8);
    L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
      maxZoom: 18, subdomains:'abcd',
      attribution: '© OpenStreetMap © CARTO'
    }).addTo(map);

    // 俯視飛機剪影，機頭向上（track 0 = 北），rotate(track) 就啱
    const PLANE_SVG = '<svg viewBox="0 0 24 24" width="24" height="24"><path fill="#7fffd4" stroke="#031a14" stroke-width="0.7" d="M12 1.6 C12.6 1.6 13 2.4 13 4 L13 10.4 L21.6 15.4 L21.6 17.2 L13 14.6 L13 19.4 L15.2 21 L15.2 22.4 L12 21.4 L8.8 22.4 L8.8 21 L11 19.4 L11 14.6 L2.4 17.2 L2.4 15.4 L11 10.4 L11 4 C11 2.4 11.4 1.6 12 1.6 Z"/></svg>';
    function nameOf(p) { return p.flight || (p.hex || '').toUpperCase(); }
    function altOf(p) { return (p.alt != null) ? Math.round(p.alt).toLocaleString() + ' ft' : '—'; }
    function makeIcon(p) {
      const rot = (p.track != null) ? p.track : 0;
      const html = `<div class="ac-wrap"><div class="ac" style="transform:rotate(${rot}deg)">${PLANE_SVG}</div>`
        + `<div class="ac-lbl"><span class="fl">${esc(nameOf(p))}</span><span class="al">${esc(altOf(p))}</span></div></div>`;
      return L.divIcon({ className:'ac-icon', html, iconSize:[26,26], iconAnchor:[13,13] });
    }
    function syncLabel(p) {
      // 航班號 + 機頭方向喺 poll 設定；高度由 animate loop 即時跳動
      const el = p.marker.getElement();
      if (!el) return;
      const ac = el.querySelector('.ac');
      if (ac && p.track != null && p.rot !== p.track) { ac.style.transform = `rotate(${p.track}deg)`; p.rot = p.track; }
      const fl = el.querySelector('.ac-lbl .fl'); if (fl) fl.textContent = nameOf(p);
    }
    function setAltLabel(p, ft) {
      const el = p.marker.getElement();
      if (!el) return;
      const al = el.querySelector('.ac-lbl .al');
      if (al) al.textContent = (ft != null) ? ft.toLocaleString() + ' ft' : '—';
    }
    function tipHTML(p) {
      const spd = (p.gs != null) ? Math.round(p.gs) + ' kt' : '—';
      return `<b>${esc(nameOf(p))}</b><br><span class="k">${esc(T.map_alt)}</span> ${altOf(p)} · <span class="k">${esc(T.map_spd)}</span> ${spd}`;
    }
    function prow(k, v) {
      return v ? `<div class="pr"><span class="pk">${esc(k)}</span><span class="pv">${esc(v)}</span></div>` : '';
    }
    function buildPopup(p) {
      const spd = (p.gs != null) ? Math.round(p.gs) + ' kt' : null;
      const vs = (p.rate != null) ? ((p.rate > 0 ? '+' : '') + Math.round(p.rate) + ' ft/min') : null;
      const hdg = (p.track != null) ? (Math.round(p.track) + '°') : null;
      const route = (p.from || p.to) ? `${p.from || '—'} › ${p.to || '—'}` : null;
      const fr24 = p.reg ? `https://www.flightradar24.com/data/aircraft/${p.reg.toLowerCase()}`
                         : `https://www.flightradar24.com/data/aircraft/${p.hex}`;
      let h = `<div class="pop"><div class="pop-h">${esc(nameOf(p))}</div>`;
      h += prow(T.map_reg, p.reg);
      h += prow(T.map_type, p.type);
      h += prow(T.map_op, p.operator);
      h += prow(T.map_country, p.country);
      h += prow(T.map_route, route);
      h += prow(T.map_alt, (p.alt != null) ? Math.round(p.alt).toLocaleString() + ' ft' : null);
      h += prow(T.map_vs, vs);
      h += prow(T.map_spd, spd);
      h += prow(T.map_hdg, hdg);
      h += prow('ICAO', (p.hex || '').toUpperCase());
      h += `<a class="pop-link" href="${fr24}" target="_blank" rel="noopener">${esc(T.map_fr24)} ↗</a>`;
      return h + '</div>';
    }

    const planes = {};   // hex -> state
    let firstFit = true;

    function extrap(fix, dt) {
      const ms = (fix.gs || 0) * 0.514444;        // kt -> m/s
      const dist = ms * Math.min(dt, 30);         // cap 30s 防 poll 卡住飛走
      const rad = (fix.track || 0) * Math.PI/180;
      const dLat = (dist * Math.cos(rad)) / 111320;
      const dLon = (dist * Math.sin(rad)) / (111320 * Math.cos(fix.lat * Math.PI/180));
      return { lat: fix.lat + dLat, lon: fix.lon + dLon };
    }

    async function poll() {
      let data;
      try { data = await (await fetch('/api/live')).json(); }
      catch (e) { return; }
      const list = data.aircraft || [];
      const now = performance.now();
      const seen = new Set();
      const fitPts = [];
      for (const a of list) {
        if (a.lat == null || a.lon == null) continue;
        seen.add(a.hex);
        fitPts.push([a.lat, a.lon]);
        let p = planes[a.hex];
        const fix = { lat:a.lat, lon:a.lon, track:a.track, gs:a.gs, t:now };
        if (!p) {
          p = planes[a.hex] = { marker:null, fix, disp:{lat:a.lat, lon:a.lon},
            hex:a.hex, lastSeen:now, rot:(a.track!=null?a.track:0),
            altFix:a.alt, rate:a.rate, altT:now, dispAlt:a.alt, altShown:null,
            flight:a.flight, alt:a.alt, gs:a.gs, track:a.track,
            reg:a.reg, type:a.type, operator:a.operator, country:a.country, from:a.from, to:a.to };
          p.marker = L.marker([a.lat, a.lon], { icon: makeIcon(p) })
            .bindTooltip('', { className:'ac-tip', direction:'top', offset:[0,-10], opacity:1 })
            .bindPopup('', { className:'ac-pop', maxWidth:280, autoPan:true })
            .addTo(map);
          p.marker.on('click', () => { p.marker.setPopupContent(buildPopup(p)); p.marker.openPopup(); });
        } else {
          p.fix = fix; p.lastSeen = now;
          p.altFix = a.alt; p.rate = a.rate; p.altT = now;
          if (p.dispAlt == null) p.dispAlt = a.alt;
          p.flight = a.flight; p.alt = a.alt; p.gs = a.gs; p.track = a.track;
          p.reg = a.reg; p.type = a.type; p.operator = a.operator; p.country = a.country; p.from = a.from; p.to = a.to;
        }
        p.marker.setTooltipContent(tipHTML(p));
        syncLabel(p);
        if (p.marker.isPopupOpen()) p.marker.setPopupContent(buildPopup(p));
      }
      // 移走已經出區（45 秒冇再見）嘅機
      for (const hex in planes) {
        if (!seen.has(hex) && (now - planes[hex].lastSeen) > 45000) {
          map.removeLayer(planes[hex].marker); delete planes[hex];
        }
      }
      const n = Object.keys(planes).length;
      document.getElementById('cnt').textContent = n ? (n + ' ' + T.map_unit) : T.map_empty;
      if (firstFit && fitPts.length) { firstFit = false;
        try { map.fitBounds(fitPts, { padding:[40,40], maxZoom:10 }); } catch (e) {} }
    }
    poll();
    setInterval(poll, 3000);

    // ===== 平滑移動（dead-reckoning + lerp，似 FR24）=====
    function animate() {
      const now = performance.now();
      for (const hex in planes) {
        const p = planes[hex];
        const target = extrap(p.fix, (now - p.fix.t) / 1000);
        p.disp.lat += (target.lat - p.disp.lat) * 0.12;
        p.disp.lon += (target.lon - p.disp.lon) * 0.12;
        p.marker.setLatLng([p.disp.lat, p.disp.lon]);

        // 高度即時跳動：用 baro_rate 外推 + lerp，按 25ft 級更新個 label
        if (p.altFix != null) {
          const dtA = Math.min((now - p.altT) / 1000, 60);
          const tgtAlt = p.altFix + (p.rate || 0) / 60 * dtA;   // rate ft/min -> ft/s
          p.dispAlt += (tgtAlt - p.dispAlt) * 0.15;
          const r = Math.round(p.dispAlt / 25) * 25;
          if (r !== p.altShown) { p.altShown = r; setAltLabel(p, r); }
        }
      }
      requestAnimationFrame(animate);
    }
    requestAnimationFrame(animate);
  </script>
</body>
</html>'''


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
        if parsed.path == '/stats':
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(_render(STATS_HTML, lang).encode('utf-8'))
            return
        if parsed.path == '/api/stats':
            payload = query_stats()
            body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if parsed.path == '/about':
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(_render(ABOUT_HTML, lang).encode('utf-8'))
            return
        if parsed.path == '/api/about':
            payload = query_about()
            body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if parsed.path == '/api/health':
            payload, status = query_health()
            body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
            self.send_response(status)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if parsed.path == '/map':
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(_render(MAP_HTML, lang).encode('utf-8'))
            return
        if parsed.path == '/api/live':
            payload = query_live()
            body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
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
