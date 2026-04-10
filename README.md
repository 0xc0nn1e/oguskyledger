# plane-history

本地 ADS-B 飛機經過記錄器（receiver mode）。

## 功能

- 每 60 秒抓取 tar1090 `aircraft.json`
- 每 3 分鐘自動補 REG / country
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

### 1 分鐘 ingest job

```bash
cp com.connie.plane-history.ingest.plist ~/Library/LaunchAgents/
launchctl bootout gui/$(id -u)/com.connie.plane-history.ingest 2>/dev/null || true
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.connie.plane-history.ingest.plist
launchctl kickstart -k gui/$(id -u)/com.connie.plane-history.ingest
```

內容：
1. `ingest.py --once`
2. `enrich_registry.py`
3. `backfill_reg_browser.py`
4. `enrich_operator.py`
5. `build_passes.py`

### 3 分鐘 REG bulk backfill job

```bash
cp com.connie.plane-history.reg.plist ~/Library/LaunchAgents/
launchctl bootout gui/$(id -u)/com.connie.plane-history.reg 2>/dev/null || true
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.connie.plane-history.reg.plist
launchctl kickstart -k gui/$(id -u)/com.connie.plane-history.reg
```

內容：
- `python3 src/browser_bulk_backfill.py`

## 主要腳本

- `src/ingest.py`：抓 tar1090 `aircraft.json` 寫入 `sightings_raw`
- `src/enrich_registry.py`：prefix/country fallback enrichment
- `src/backfill_reg_browser.py`：browser-based REG backfill（目前 quick source）
- `src/browser_bulk_backfill.py`：Playwright bulk backfill，掃缺 REG ICAO，自動寫回 DB
- `src/enrich_operator.py`：按 flight prefix 補 operator / operator_country
- `src/build_passes.py`：用 20 分鐘 gap 聚合 passes
- `src/query_today.py`：查今日 aircraft（JST 顯示）
- `src/query_icao.py`：按 ICAO / callsign 搜尋
- `src/query_passes_today.py`：查今日 passes
- `src/healthcheck.py`：檢查 launchd / DB / logs 狀態
- `run_ingest.sh`：1 分鐘 ingest launchd 入口

## Logs / DB

- `data/ingest.log`
- `data/browser_bulk_backfill.log`
- `data/launchd.out.log`
- `data/launchd.err.log`
- `data/launchd.reg.out.log`
- `data/launchd.reg.err.log`
- `data/plane_history.sqlite3`

## 常用指令

```bash
python3 src/query_today.py
python3 src/query_passes_today.py
python3 src/healthcheck.py
python3 src/browser_bulk_backfill.py
```

## 備註

- `samples` = 今日同一 ICAO 在 `sightings_raw` 入面出現嘅 row 數
- `passes` = 以 20 分鐘 gap 聚合後嘅經過次數
- REG bulk backfill 依賴 Python `playwright` + `chromium`
