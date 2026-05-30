# plane-history

本地 ADS-B 飛機經過記錄器（receiver mode）。

## 功能

- 每 60 秒抓取 tar1090 `aircraft.json`
- 每 3 分鐘自動補 `registration / country / aircraft_type`
- `operator` 會由兩條路徑補完
  - 先用 flight prefix 推斷（例如 `HKE`）
  - 再對符合條件嘅 aircraft 去 FR24 aircraft page 補真實 operator
- Web dashboard（SKYLEDGER 雷達主題）多頁：
  - `/`：首頁，recent contacts + 今日 aircraft table
  - `/details`：歷史飛機接觸搜尋 / filter（公司・機型・航線・國家・高度）+ sort
  - `/stats`：7 日每日班次、近 24 小時逐鐘 histogram、**近 30 日 weekday × hour heatmap**、TOP 10（機型 / 公司 / 出發 / 目的地 / **ICAO** 7 日 + 全 DB）、peak altitude、busiest hour；**長窗口段**：累計 unique ICAO 發現曲線、最高高度分佈 histogram、罕見機 list（只見過 1–2 次嘅 ICAO）。`/discover` 舊 URL 301 redirect 入嚟
  - `/map`：即時地圖，tar1090 live 位置，FR24 式平滑移動，click 出詳細 popup（`/api/live` 有 1 秒 TTL cache，N 個 client 共用同一 fetch）
  - `/coverage`：接收覆蓋極座標雷達圖（近 30 日，每方位最遠距離）+ max range / 最遠機體
  - `/aircraft?icao=<hex>`：單機歷史（聚合統計、每日出現、**SVG 速度·高度 dual-axis profile chart**、經過記錄含 per-pass FROM / TO）—— 喺 `/`、`/details`、`/map` 撳機入
  - `/about`：接收機狀態、技術 stack、架構圖、系統健康
  - `/api/health`：monitoring endpoint（DB ok 回 200、死回 503）
- ICAO 前面 sprinkle category emoji：🚁 直升機（A7）、🪁 滑翔機（B1）、🎈 氣球 / UAV（B2/B6）、🚗 地面車（C\*）；客機留白避免 noise
- 簡單 login / session（`users` / `sessions` 表）
- 凡係接收站收得到嘅 aircraft，都當作「屋企收到」
- HKE / Hong Kong Express 入區時送 push（`HKE confirm: <flight no> | <reg> | <from>>HKG`）
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
```

## Quick start

```bash
python3 src/init_db.py
python3 src/ingest.py --once
python3 src/enrich_registry.py
python3 src/backfill_reg_browser.py
python3 src/enrich_operator.py
python3 src/build_passes.py
python3 src/query_today.py
python3 src/query_passes_today.py
python3 src/query_icao.py 84b5ee
python3 src/healthcheck.py
```

## 自動執行（launchd）

只有一個 supervisor job，入面跑晒 ingest / reg / web 三條 thread。

```bash
cp com.connie.plane-history.supervisor.plist ~/Library/LaunchAgents/
launchctl bootout gui/$(id -u)/com.connie.plane-history.supervisor 2>/dev/null || true
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.connie.plane-history.supervisor.plist
launchctl kickstart -k gui/$(id -u)/com.connie.plane-history.supervisor
```

`src/supervisor.py` 內容：
- Main thread：`web_app.serve()`（blocking）
- Thread `ingest`：每 60 秒 `bash run_ingest.sh`
- Thread `reg`：每 180 秒 `python3 src/browser_bulk_backfill.py`

`run_ingest.sh` 入面 pipeline 順序：
1. `ingest.py --once`
2. `enrich_registry.py`
3. `backfill_reg_browser.py`
4. `enrich_operator.py`
5. `build_passes.py`

`browser_bulk_backfill.py` 會補：
- `registration`
- `country`
- `aircraft_type`（例如 `A21N`, `B77W`）
- `operator`

規則：
- `registration / country / aircraft_type` 會優先補
- `operator` 會對符合條件嘅 aircraft 去 FR24 aircraft page 補
- country 會盡量中文化（例如 `台灣`, `新加坡`, `加拿大`, `盧森堡`, `馬來西亞`）

## 主要腳本

- `src/ingest.py`：抓 tar1090 `aircraft.json` 寫入 `sightings_raw`，並在**同一個 ICAO 今日第一次確認係 HKE / Hong Kong Express**時送 push message 到 `push.connie.hk`
- `src/enrich_registry.py`：prefix/country fallback enrichment
- `src/backfill_reg_browser.py`：browser-based REG backfill（目前 quick source）
- `src/browser_bulk_backfill.py`：Playwright bulk backfill，掃缺 `registration / country / aircraft_type / operator` 嘅 ICAO，自動寫回 DB；補完後如果係 HKE / Hong Kong Express，會送 `HKE confirm` push（一日一次）。flight no 用 ADS-B 廣播 callsign（`sightings_raw.flight`），**未 read 到 callsign 嗰鋪會 skip，唔會 push ICAO hex**，等下個 cycle 有 callsign 先送
- `src/enrich_operator.py`：按 flight prefix 補 operator / operator_country（唔會再用空值覆蓋 browser / FR24 補回來嘅 operator）
- `src/notifier.py`：用 `openssl + curl` 簽名送 message 去 `push.connie.hk`
- `src/build_passes.py`：用 20 分鐘 gap 聚合 passes；同時用 `aircraft_route_snapshots` 揾返 per-pass FROM / TO（match by (icao, flight) 最新 snapshot）
- `src/query_today.py`：查今日 aircraft（JST 顯示）
- `src/query_icao.py`：按 ICAO / callsign 搜尋
- `src/query_passes_today.py`：查今日 passes
- `src/healthcheck.py`：檢查 launchd / DB / logs 狀態
- `run_ingest.sh`：1 分鐘 ingest launchd 入口

## Logs / DB

- `data/supervisor.log` / `data/supervisor.out.log` / `data/supervisor.err.log`
- `data/ingest.log`
- `data/browser_bulk_backfill.log`
- MySQL：`127.0.0.1:3306`，DB `plane_history`（connection info 喺 `src/config.json` 入面）

## Web UI

`supervisor` 已經自動開咗 web app，直接開 `http://127.0.0.1:8765` 就睇到。手動 run 嘅話：

```bash
python3 src/web_app.py
```

頁面：`/`（首頁）、`/details`（搜尋 / filter / sort）、`/stats`（統計 + 長窗口發現）、`/map`（即時地圖）、`/coverage`（覆蓋雷達）、`/aircraft?icao=`（單機歷史）、`/about`（關於 / 系統健康）。三語切換（日 / 廣東話 / 英文）。

JSON API：
- `/api/stats`：統計數據（7 日 / 24h histogram、heatmap、top 10、peak alt、busiest hour）
- `/api/discover`：discovery curve、rare finds、altitude 分佈、全 DB top 10 ICAO（`/stats` 頁同時 fetch 呢條同 `/api/stats`）
- `/api/live`：tar1090 即時飛機（地圖用，含 registry enrichment，1 秒 TTL cache）
- `/api/aircraft?icao=`：單機歷史（registry + passes 聚合，含 per-pass FROM / TO）
- `/api/aircraft/track?icao=&from=&to=`：單一 pass 嘅 sightings_raw 軌跡（畫 alt + gs profile chart 用）
- `/api/coverage`：接收覆蓋（每方位最遠距離，10 分鐘 cache）
- `/api/about`：接收機 / feed 狀態
- `/api/health`：健康檢查（200 / 503）

## 常用指令

```bash
python3 src/query_today.py
python3 src/query_passes_today.py
python3 src/healthcheck.py
python3 src/browser_bulk_backfill.py
python3 src/web_app.py
```

## 備註

- `samples` = 今日同一 ICAO 在 `sightings_raw` 入面出現嘅 row 數
- `passes` = 以 20 分鐘 gap 聚合後嘅經過次數
- `aircraft_route_snapshots` 表：每次 `browser_bulk_backfill` 由 FR24 攞到 from/to + 當時 ADS-B 廣播 callsign，記低一條 `(icao, flight, from, to, observed_at)`。`build_passes` 重建時揾返每組 `(icao, flight)` 最新 snapshot 填返入 `aircraft_passes.from_airport / to_airport`，達到 per-pass route 而唔係全部 pass 共用 registry 嘅最新一條
- `/api/live` 同 `/api/coverage` 都用 module-level dict cache（process-local，restart 即清，無需 Redis）
- REG bulk backfill 依賴 Python `playwright` + `chromium`
- `push.connie.hk` 使用 HMAC header 驗證，Python notifier 會以 `openssl + curl` 兼容現有 shell 簽名流程
