# 尾久 SKYLEDGER · TOKYO

**繁體中文** · [日本語](README.ja.md) · [English](README.en.md)

喺東京・尾久屋企接收機收到嘅飛機資料，記錄 + 可視化嘅個人 project。屋企裝嘅 ADS-B 接收機攞飛機資料，存落 MySQL 做歷史；Django + DRF + gunicorn 後端 API + Web dashboard 可視化，HKE 航班入區仲會即時 push 通知。

https://flight.connie.hk/

# 技術棧
- 前端
 HTML · CSS · vanilla JS · Three.js · Leaflet（都 self-host vendor，零第三方可執行 JS）
- 後端
Python 3.13 · Django 5 · DRF · gunicorn
- 資料庫
MySQL · PyMySQL
- 接收機
Raspberry Pi · dump1090 / readsb / tar1090
- 部署
macOS launchd · gunicorn · whitenoise
- 通知
push.connie.hk (HMAC)


本地 ADS-B 飛機經過記錄器（receiver mode）+ Django web stack。

## screenshot
*FrontPage*

![Demo screenshot](https://flight.connie.hk/static/img/screenshot_01_resize.png)

*Map*

![Demo screenshot](https://flight.connie.hk/static/img/screenshot_02_resize.png)

*rawdata*

![Demo screenshot](https://flight.connie.hk/static/img/screenshot_03_resize.png)


*stats*

![Demo screenshot](https://flight.connie.hk/static/img/screenshot_04_resize.png)

## 功能

- 每 60 秒抓取 tar1090 `aircraft.json`
- 每 3 分鐘自動補 `registration / country / aircraft_type`
- `operator` 會由兩條路徑補完
  - 先用 flight prefix 推斷（例如 `HKE`）
  - 再對符合條件嘅 aircraft 去 FR24 aircraft page 補真實 operator
- Web dashboard（SKYLEDGER 雷達主題）多頁：
  - `/`：首頁，recent contacts + 今日 operator group + 4 個 stat tile（PEAK ALT 撳得入嗰架最高高度機）
  - `/details`：歷史飛機接觸搜尋 / filter（公司・機型・航線・國家・高度）+ sort
  - `/stats`：7 日每日班次、近 24 小時逐鐘 histogram、**近 30 日 weekday × hour heatmap**、TOP 10（機型 / 公司 / 出發 / 目的地 / **ICAO** 7 日 + 全 DB）、peak altitude、busiest hour；**長窗口段**：累計 unique ICAO 發現曲線、最高高度分佈 histogram、罕見機 list（只見過 1–2 次嘅 ICAO）。`/discover` 舊 URL 301 redirect 入嚟
  - `/map`：即時地圖，tar1090 live 位置，FR24 式平滑移動，click 出詳細 popup（`/api/live` 有 1 秒 TTL cache，N 個 client 共用同一 fetch）
  - `/aircraft/<hex>/`：單機歷史（聚合統計、每日出現、**SVG 速度·高度 dual-axis profile chart**、經過記錄含 per-pass FROM / TO + **速度範圍**、planespotters 相片、enrichment 資料新鮮度 badge）—— 喺 `/`、`/details`、`/map` 撳機入。舊 `/aircraft?icao=` URL 自動 redirect
  - `/about`：接收機狀態 + uptime + records today + feed health
  - `/api/health`：monitoring endpoint（DB ok 回 200、死回 503）
- ICAO 前面 sprinkle category emoji：🚁 直升機（A7）、🪁 滑翔機（B1）、🎈 氣球 / UAV（B2/B6）、🚗 地面車（C\*）；客機留白避免 noise
- 三套 i18n（繁中 / 日 / 英）：Django gettext + .po + JavaScriptCatalog（`/about/` 完整 swap，其他 page 過渡期仍用 legacy STRINGS dict）
- Django 內建 auth + custom login template（`/accounts/login/`；舊 `/login` 301 redirect）
- 凡係接收站收得到嘅 aircraft，都當作「屋企收到」
- Push 規則（`/push-rules/`，login 後可改）：按 callsign / icao / registration / type / route / country 前綴 match，中咗 + 已 enrich 就送 push（每機每日一次 dedup）。預設 HKE / Hong Kong Express（`HKE confirm: <flight no> | <reg> | <from>>HKG`）
- **直升機群集事故 alert**：偵測到多架直升機喺細範圍聚集（通常代表附近有事故 / 災害，報道機 + 警消直升機會聚埋）→ `/map` 即時警示橫額 + 範圍圈 + member 高亮，同時送 push（冇開住 map 都收到）。門檻（架數 / 半徑 / 冷卻）喺 `/admin/web/siteconfig/` 可調、`push_log` 做 cooldown dedup；on/off 喺 `/push-rules/` 「系統提示」section
- **Feed watchdog**：每 15 分鐘 check 一次 `MAX(sightings_raw.seen_at)`，超過 1 小時冇 update 就 push alert message 講 DB / tar1090 邊個死咗
- 寫入 MySQL
- macOS launchd 自動執行

## 資料來源

- tar1090 JSON endpoint: `http://192.168.x.x:8080/data/aircraft.json`
- tar1090 aircraft page: `http://192.168.x.x:8080/?icao=<HEX>`
- Receiver: `192.168.x.x`

## 設定

```bash
cp src/config.example.json src/config.json
# 改 src/config.json：source.aircraft_json_url（真 tar1090 URL）、
#                     mysql.password、push.secret、
#                     django.secret_key（用下面 command 隨機生成）、
#                     django.debug、django.allowed_hosts
.venv/bin/python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

## Quick start

```bash
# 1. venv + Django
brew install python@3.13
python3.13 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/playwright install chromium

# 2. fake-initial（連返舊 MySQL table 但唔重 create）
.venv/bin/python manage.py migrate --fake-initial
.venv/bin/python manage.py createsuperuser

# 3. 試跑 pipeline
.venv/bin/python manage.py ingest_pipeline
.venv/bin/python manage.py browser_bulk_backfill
.venv/bin/python manage.py healthcheck_alert
```

## 自動執行（launchd · 4 個 plist）

```bash
cp com.connie.plane-history.{web,ingest,backfill,healthcheck}.plist ~/Library/LaunchAgents/
for L in web ingest backfill healthcheck; do
  launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.connie.plane-history.$L.plist
done
```

| Plist | 內容 | Schedule |
|---|---|---|
| `.web` | gunicorn `:8765`（`0.0.0.0` bind，LAN 可達） | KeepAlive |
| `.ingest` | `manage.py ingest_pipeline` 5 step sequential | StartInterval=60 |
| `.backfill` | `manage.py browser_bulk_backfill` | StartInterval=180 |
| `.healthcheck` | `manage.py healthcheck_alert` | StartInterval=900 |

`ingest_pipeline` 入面 sequence：

1. `manage.py ingest`（subprocess wrap `src/ingest.py --once`）
2. `manage.py enrich_registry`
3. `manage.py backfill_reg_browser`（容錯，rc 非零繼續）
4. `manage.py enrich_operator`
5. `manage.py build_passes`

`browser_bulk_backfill.py` 會補：
- `registration`
- `country`
- `aircraft_type`（例如 `A21N`, `B77W`）
- `operator`

規則：
- `registration / country / aircraft_type` 會優先補
- `operator` 會對符合條件嘅 aircraft 去 FR24 aircraft page 補
- country 會盡量中文化（例如 `台灣`, `新加坡`, `加拿大`, `盧森堡`, `馬來西亞`）

## 主要 management command

- `manage.py ingest`：抓 tar1090 `aircraft.json` 寫入 `sightings_raw`，並在 callsign HKE/UO 廣播 + registry 已 enrich registration 時送 push 通知到 `push.connie.hk`
- `manage.py ingest_pipeline`：5 step sequence（上面 list）
- `manage.py enrich_registry`：prefix/country fallback enrichment
- `manage.py backfill_reg_browser`：browser-based REG backfill（quick source）
- `manage.py browser_bulk_backfill`：Playwright bulk backfill，掃缺 `registration / country / aircraft_type / operator` 嘅 ICAO，自動寫回 DB；補完後如果係 HKE / Hong Kong Express 同 callsign 廣播咗，會送 `HKE confirm` push（一日一次）
- `manage.py enrich_operator`：按 flight prefix 補 operator / operator_country（唔會用空值覆蓋 browser / FR24 補回嘅 operator）
- `manage.py build_passes`：用 20 分鐘 gap 聚合 passes；同時用 `aircraft_route_snapshots` 揾返 per-pass FROM / TO
- `manage.py healthcheck_alert`：feed watchdog，超過 1 小時冇 update 推 alert + 講 DB vs tar1090 邊度死

過渡期：management command 全部 thin wrapper（`tracking/services/runner.py` → `subprocess.run`），裡面跑舊 `src/*.py` 嘅 logic。第二期可以慢慢 refactor 入 `tracking/services/` + `enrichment/services/` 做 import 模式。

舊 `src/*.py` 仲喺 working tree，做 rollback safety net。14 日穩定後可以 archive 入 `src/_archived/`。

## Logs / DB

- `data/django-{web,ingest,backfill,healthcheck}.{log,err}`：4 個 launchd job 各自 stdout / stderr
- `data/ingest.log` / `data/browser_bulk_backfill.log`：舊 script 直接寫嘅 detailed log
- `data/.healthcheck_state.json`：feed watchdog 嘅 dedup state（last_alert_at + last_alerted）
- MySQL：`127.0.0.1:3306`，DB `plane_history`（connection info 喺 `src/config.json` 入面）

## Web UI

`web.plist` 啟動 gunicorn `:8765`（bind `0.0.0.0`，LAN 都可達）。直接開 `http://127.0.0.1:8765/` 或者 LAN `http://192.168.x.x:8765/`。

頁面：`/`（首頁）、`/details`（搜尋 / filter / sort）、`/stats`（統計 + 長窗口發現）、`/map`（即時地圖）、`/aircraft/<hex>/`（單機歷史）、`/about`（關於 / 系統健康）、`/admin/`（Django admin，readonly tracking / editable registry cache）。三語切換（繁中 / 日 / 英）。

JSON API：
- `/api/stats`：統計數據（7 日 / 24h histogram、heatmap、top 10、peak alt、busiest hour）
- `/api/discover`：discovery curve、rare finds、altitude 分佈、全 DB top 10 ICAO（`/stats` 頁同時 fetch 呢條同 `/api/stats`）
- `/api/live`：tar1090 即時飛機（地圖用，含 registry enrichment，1 秒 TTL cache）
- `/api/aircraft?icao=`：單機歷史（registry + passes 聚合，含 per-pass FROM / TO）
- `/api/aircraft/track?icao=&from=&to=`：單一 pass 嘅 sightings_raw 軌跡（畫 alt + gs profile chart 用）
- `/api/today?day=&sort=&country=&operator=&...`：home + details 頁用，rows + filter dropdown options
- `/api/summary?day=`：home 頁 operator breakdown + total aircraft count
- `/api/about`：接收機 / feed 狀態
- `/api/me`：current user info（nav 用嚟揀 login / account 顯示）
- `/api/health`：健康檢查（200 / 503）

## 備註

- `samples` = 今日同一 ICAO 在 `sightings_raw` 入面出現嘅 row 數
- `passes` = 以 20 分鐘 gap 聚合後嘅經過次數
- `aircraft_route_snapshots` 表：每次 `browser_bulk_backfill` 由 FR24 攞到 from/to + 當時 ADS-B 廣播 callsign，記低一條 `(icao, flight, from, to, observed_at)`。`build_passes` 重建時揾返每組 `(icao, flight)` 最新 snapshot 填返入 `aircraft_passes.from_airport / to_airport`，達到 per-pass route 而唔係全部 pass 共用 registry 嘅最新一條
- `/api/live` 用 module-level dict cache（process-local，restart 即清，無需 Redis）
- REG bulk backfill 依賴 Python `playwright` + `chromium`（venv 入面裝晒）
- 前端 Three.js + Leaflet self-host 喺 `static/vendor/`（`base.html` importmap 把 `three` 指過去、Leaflet 用 `{% static %}`），auth 頁零第三方可執行 JS，連 vendored LICENSE（THREE MIT / Leaflet BSD-2）。Radar 背景而家係 `base.html` default `radar_bg`，login / 後台頁都有。地圖 tiles（cartocdn）+ planespotters 相維持外部（圖片、非可執行）
- `push.connie.hk` 使用 HMAC header 驗證，Python notifier 用 `openssl + curl` 兼容現有 shell 簽名流程
- Feed watchdog 兩次 alert 之間 dedup 6 小時，避免重複轟炸；recovery（feed 返來）會 send 一次 `✓ recovered` confirm
- `/coverage` 同 `/api/coverage` 已 cut（意義不明），舊 URL 301 redirect 入 `/`
- i18n：`/about/` 用 gettext + `.po`，其他 page 仍用 `web/_legacy_strings.py` 嘅 STRINGS dict（過渡期），cookie set `django_language` 同 legacy `lang` 兩個並存
