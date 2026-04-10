# plane-history

本地 ADS-B 飛機經過記錄器（receiver mode MVP）。

## 功能

- 定時抓取 tar1090 / readsb `aircraft.json`
- 凡係接收站收得到嘅 aircraft，都當作「你屋企收到」
- 寫入 SQLite
- 查詢今日 / 某日見過邊啲機
- 查 ICAO / callsign
- 輸出 daily summary
- 提供 macOS launchd 自動 ingest

## 目前來源

- tar1090 JSON endpoint: `http://192.168.x.x:8080/data/aircraft.json`
- Raspberry Wing: `192.168.x.x`
- Beast port: `30005`

## Quick start

```bash
cd ~/Documents/plane-history
python3 src/init_db.py
python3 src/ingest.py --once
python3 src/enrich_registry.py
python3 src/enrich_operator.py
python3 src/build_passes.py
python3 src/query_today.py
python3 src/daily_summary.py
python3 src/query_icao.py 84b5ee
python3 src/query_passes_today.py
python3 src/healthcheck.py
```

## 自動執行（launchd）

```bash
mkdir -p ~/Library/LaunchAgents
cp ~/Documents/plane-history/com.connie.plane-history.ingest.plist ~/Library/LaunchAgents/
launchctl unload ~/Library/LaunchAgents/com.connie.plane-history.ingest.plist 2>/dev/null || true
launchctl load ~/Library/LaunchAgents/com.connie.plane-history.ingest.plist
launchctl kickstart -k gui/$(id -u)/com.connie.plane-history.ingest
```

會每 60 秒自動執行以下流程：
1. `ingest.py`
2. `enrich_registry.py`
3. `enrich_operator.py`
4. `build_passes.py`

log 喺：
- `data/ingest.log`
- `data/launchd.out.log`
- `data/launchd.err.log`

## 檔案

- `src/config.json`：receiver 名稱、資料來源
- `src/init_db.py`：初始化 SQLite schema
- `src/ingest.py`：抓資料寫 DB
- `src/enrich_registry.py`：補 country / registry cache
- `src/enrich_operator.py`：補 operator / operator country
- `src/query_today.py`：查今日收到邊啲機
- `src/query_icao.py`：按 ICAO / callsign 搜尋
- `src/daily_summary.py`：今日 summary
- `src/build_passes.py`：把 raw samples 聚合成 passes
- `src/query_passes_today.py`：查今日 passes
- `src/healthcheck.py`：檢查 launchd / DB / logs 狀態
- `run_ingest.sh`：launchd 執行入口
- `com.connie.plane-history.ingest.plist`：macOS 定時任務
- `data/plane_history.sqlite3`：SQLite DB

## 維護與檢查

```bash
python3 src/healthcheck.py
```

如果想清空舊 log：
```bash
: > data/ingest.log
: > data/launchd.out.log
: > data/launchd.err.log
```

## 現在的自動流程

每 60 秒：
- 抓 tar1090 / readsb `aircraft.json`
- 寫入 `sightings_raw`
- 更新 `aircraft_registry_cache`
- 補 operator / country enrichment
- 重建 `aircraft_passes`

## 建議下一步

- 補真正 registration lookup source
- 加 daily rollup table
- 加簡單 web UI / API
- 清理重複 sample / retention policy
