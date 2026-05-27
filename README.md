# plane-history

本地 ADS-B 飛機經過記錄器（receiver mode）。

## 功能

- 每 60 秒抓取 tar1090 `aircraft.json`
- 每 3 分鐘自動補 `registration / country / aircraft_type`
- `operator` 會由兩條路徑補完
  - 先用 flight prefix 推斷（例如 `HKE`）
  - 再對符合條件嘅 aircraft 去 FR24 aircraft page 補真實 operator
- 支援 web UI 查今日飛機資料
- web UI 支援 `country / operator / type` filter 同 sort
- 凡係接收站收得到嘅 aircraft，都當作「屋企收到」
- 寫入 SQLite
- 查今日 / ICAO / passes
- macOS launchd 自動執行

## 資料來源

- tar1090 JSON endpoint: `http://192.168.x.x:8080/data/aircraft.json`
- tar1090 aircraft page: `http://192.168.x.x:8080/?icao=<HEX>`
- Receiver: `192.168.x.x`

## 專案位置

```bash
cd ~/plane-history
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
- `src/browser_bulk_backfill.py`：Playwright bulk backfill，掃缺 `registration / country / aircraft_type / operator` 嘅 ICAO，自動寫回 DB
- `src/enrich_operator.py`：按 flight prefix 補 operator / operator_country（唔會再用空值覆蓋 browser / FR24 補回來嘅 operator）
- `src/notifier.py`：用 `openssl + curl` 簽名送 message 去 `push.connie.hk`
- `src/build_passes.py`：用 20 分鐘 gap 聚合 passes
- `src/query_today.py`：查今日 aircraft（JST 顯示）
- `src/query_icao.py`：按 ICAO / callsign 搜尋
- `src/query_passes_today.py`：查今日 passes
- `src/healthcheck.py`：檢查 launchd / DB / logs 狀態
- `run_ingest.sh`：1 分鐘 ingest launchd 入口

## Logs / DB

- `data/supervisor.log` / `data/supervisor.out.log` / `data/supervisor.err.log`
- `data/ingest.log`
- `data/browser_bulk_backfill.log`
- `data/plane_history.sqlite3`

## Web UI

`supervisor` 已經自動開咗 web app，直接開 `http://127.0.0.1:8765` 就睇到。手動 run 嘅話：

```bash
python3 src/web_app.py
```

功能：
- 今日 aircraft table
- 顯示 `REG / TYPE / COUNTRY / OPERATOR`
- `country / operator / type` filter
- `last_seen / country / operator / type` sort

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
- REG bulk backfill 依賴 Python `playwright` + `chromium`
- `push.connie.hk` 使用 HMAC header 驗證，Python notifier 會以 `openssl + curl` 兼容現有 shell 簽名流程
