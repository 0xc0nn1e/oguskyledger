# 尾久 SKYLEDGER · TOKYO

[繁體中文](README.md) · **日本語** · [English](README.en.md)

東京・尾久の自宅受信機で取得した航空機データを記録・可視化する個人開発プロジェクトです。
自宅に設置した ADS-B 受信機から航空機データを取得し、MySQL に履歴を保存。Django + DRF + gunicorn によるバックエンド API と Web ダッシュボードで可視化、HKE 便がエリアに入ったらリアルタイムで push 通知も送信します。

https://flight.connie.hk/

# 技術スタック
- フロントエンド
 HTML · CSS · vanilla JS · Three.js · Leaflet（すべて self-host vendor、サードパーティの実行可能 JS ゼロ）
- バックエンド
Python 3.13 · Django 5 · DRF · gunicorn
- データベース
MySQL · PyMySQL
- 受信機
Raspberry Pi · dump1090 / readsb / tar1090
- デプロイ
macOS launchd · gunicorn · whitenoise
- 通知
push.connie.hk (HMAC)


ローカル ADS-B 航空機通過レコーダー（receiver mode）+ Django web stack。

## screenshot
*FrontPage*

![Demo screenshot](https://flight.connie.hk/static/img/screenshot_01_resize.png)

*Map*

![Demo screenshot](https://flight.connie.hk/static/img/screenshot_02_resize.png)

*rawdata*

![Demo screenshot](https://flight.connie.hk/static/img/screenshot_03_resize.png)


*stats*

![Demo screenshot](https://flight.connie.hk/static/img/screenshot_04_resize.png)

## 機能

- 60 秒ごとに tar1090 `aircraft.json` を取得
- 3 分ごとに `registration / country / aircraft_type` を自動補完
- `operator` は 2 つの経路で補完
  - まず flight prefix から推定（例：`HKE`）
  - さらに条件に合う aircraft は FR24 aircraft page で実際の operator を補完
- Web ダッシュボード（SKYLEDGER レーダーテーマ）複数ページ：
  - `/`：トップ、recent contacts + 当日の operator group + 4 つの stat tile（PEAK ALT から最高高度の機体へジャンプ可）
  - `/details`：過去の航空機コンタクト検索 / filter（会社・機種・路線・国・高度）+ sort
  - `/stats`：7 日間の便数、直近 24 時間の毎時 histogram、**直近 30 日 weekday × hour heatmap**、TOP 10（機種 / 会社 / 出発 / 目的地 / **ICAO** 7 日 + 全 DB）、peak altitude、busiest hour；**ロングウィンドウ**：累計 unique ICAO 発見曲線、最高高度分布 histogram、レア機リスト（1〜2 回だけの ICAO）。`/discover` 旧 URL は 301 redirect
  - `/map`：リアルタイム地図、tar1090 live 位置、FR24 風スムーズ移動、click で詳細 popup（`/api/live` は 1 秒 TTL cache、複数 client が同一 fetch を共有）
  - `/aircraft/<hex>/`：単機の履歴（集計統計、日別出現、**SVG 速度・高度 dual-axis profile chart**、通過記録に per-pass FROM / TO + **速度レンジ**、planespotters 写真、enrichment データ鮮度 badge）—— `/`、`/details`、`/map` から機体をクリックして遷移。旧 `/aircraft?icao=` URL は自動 redirect
  - `/about`：受信機ステータス + uptime + records today + feed health
  - `/api/health`：monitoring endpoint（DB ok で 200、死んだら 503）
- ICAO の前に category emoji：🚁 ヘリ（A7）、🪁 グライダー（B1）、🎈 気球 / UAV（B2/B6）、🚗 地上車両（C\*）；旅客機は noise を避けるため空白
- 3 言語 i18n（繁体中文 / 日本語 / 英語）：Django gettext + .po + JavaScriptCatalog（`/about/` は完全 swap、他ページは過渡期で legacy STRINGS dict）
- Django 内蔵 auth + custom login template（`/accounts/login/`；旧 `/login` は 301 redirect）
- 受信局が受信できた aircraft はすべて「自宅で受信」とみなす
- Push ルール（`/push-rules/`、login 後に編集可）：callsign / icao / registration / type / route / country の prefix で match、ヒット + enrich 済みで push 送信（機体ごと 1 日 1 回 dedup）。デフォルトは HKE / Hong Kong Express（`HKE confirm: <flight no> | <reg> | <from>>HKG`）
- **ヘリ集結による事故 alert**：複数のヘリが狭い範囲に集結（通常は近くで事故 / 災害、報道機 + 警察・消防のヘリが集まる）→ `/map` にリアルタイム警告バナー + 範囲円 + member ハイライト、同時に push 送信（map を開いていなくても届く）。しきい値（機数 / 半径 / クールダウン）は `/admin/web/siteconfig/` で調整、`push_log` で cooldown dedup；on/off は `/push-rules/` の「システム通知」section
- **Feed watchdog**：15 分ごとに `MAX(sightings_raw.seen_at)` を check、1 時間以上 update が無ければ DB / tar1090 のどちらが落ちたか push alert
- MySQL に書き込み
- macOS launchd で自動実行

## データソース

- tar1090 JSON endpoint: `http://192.168.x.x:8080/data/aircraft.json`
- tar1090 aircraft page: `http://192.168.x.x:8080/?icao=<HEX>`
- Receiver: `192.168.x.x`

## 設定

```bash
cp src/config.example.json src/config.json
# src/config.json を編集：source.aircraft_json_url（実際の tar1090 URL）、
#                     mysql.password、push.secret、
#                     django.secret_key（下のコマンドでランダム生成）、
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

# 2. fake-initial（既存の MySQL table に接続するが再 create しない）
.venv/bin/python manage.py migrate --fake-initial
.venv/bin/python manage.py createsuperuser

# 3. pipeline を試走
.venv/bin/python manage.py ingest_pipeline
.venv/bin/python manage.py browser_bulk_backfill
.venv/bin/python manage.py healthcheck_alert
.venv/bin/python manage.py refresh_stats_cache
```

## 自動実行（launchd · 5 つの plist）

```bash
cp com.connie.plane-history.{web,ingest,backfill,healthcheck,stats-cache}.plist ~/Library/LaunchAgents/
for L in web ingest backfill healthcheck stats-cache; do
  launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.connie.plane-history.$L.plist
done
```

| Plist | 内容 | Schedule |
|---|---|---|
| `.web` | gunicorn `:8765`（`0.0.0.0` bind、LAN から到達可） | KeepAlive |
| `.ingest` | `manage.py ingest_pipeline` 5 step sequential | StartInterval=60 |
| `.backfill` | `manage.py browser_bulk_backfill` | StartInterval=180 |
| `.healthcheck` | `manage.py healthcheck_alert` | StartInterval=900 |
| `.stats-cache` | `/api/stats` + `/api/discover` の永続 snapshot を事前計算 | StartInterval=3600 |

`ingest_pipeline` 内の sequence：

1. `manage.py ingest`（`src/ingest.py --once` を subprocess wrap）
2. `manage.py enrich_registry`
3. `manage.py backfill_reg_browser`（耐障害、rc 非ゼロでも継続）
4. `manage.py enrich_operator`
5. `manage.py build_passes`

`browser_bulk_backfill.py` が補完：
- `registration`
- `country`
- `aircraft_type`（例：`A21N`, `B77W`）
- `operator`

ルール：
- `registration / country / aircraft_type` を優先補完
- `operator` は条件に合う aircraft を FR24 aircraft page で補完
- country はできる限り中国語化（例：`台灣`, `新加坡`, `加拿大`, `盧森堡`, `馬來西亞`）

## 主要 management command

- `manage.py ingest`：tar1090 `aircraft.json` を取得して `sightings_raw` に書き込み、callsign HKE/UO ブロードキャスト + registry が registration を enrich 済みのとき `push.connie.hk` へ push 通知
- `manage.py ingest_pipeline`：5 step sequence（上記リスト）
- `manage.py enrich_registry`：prefix/country fallback enrichment
- `manage.py backfill_reg_browser`：browser ベースの REG backfill（quick source）
- `manage.py browser_bulk_backfill`：Playwright bulk backfill、`registration / country / aircraft_type / operator` 欠けの ICAO を掃いて DB に書き戻し、補完後 HKE / Hong Kong Express かつ callsign ブロードキャスト済みなら `HKE confirm` push（1 日 1 回）
- `manage.py enrich_operator`：flight prefix で operator / operator_country を補完（browser / FR24 が補った operator を空値で上書きしない）
- `manage.py build_passes`：20 分 gap で passes 集計；同時に `aircraft_route_snapshots` で per-pass FROM / TO を復元
- `manage.py healthcheck_alert`：feed watchdog、1 時間以上 update 無しで alert + DB vs tar1090 のどちらが落ちたか
- `manage.py refresh_stats_cache`：`/api/stats` と `/api/discover` の永続 JSON snapshot をバックグラウンドで事前計算

過渡期：management command はすべて thin wrapper（`tracking/services/runner.py` → `subprocess.run`）で、中身は旧 `src/*.py` の logic を実行。第二期で `tracking/services/` + `enrichment/services/` に import 方式へ徐々に refactor 予定。

旧 `src/*.py` は working tree に残し、rollback safety net とする。14 日安定後に `src/_archived/` へ archive 可能。

## Logs / DB

- `data/django-{web,ingest,backfill,healthcheck,stats-cache}.{log,err}`：5 つの launchd job それぞれの stdout / stderr
- `data/ingest.log` / `data/browser_bulk_backfill.log`：旧 script が直接書く detailed log
- `data/.healthcheck_state.json`：feed watchdog の dedup state（last_alert_at + last_alerted）
- MySQL：`127.0.0.1:3306`、DB `plane_history`（connection info は `src/config.json`）

## Web UI

`web.plist` が gunicorn `:8765` を起動（`0.0.0.0` bind、LAN からも到達可）。`http://127.0.0.1:8765/` または LAN `http://192.168.x.x:8765/` を開く。

ページ：`/`（トップ）、`/details`（検索 / filter / sort）、`/stats`（統計 + ロングウィンドウ発見）、`/map`（リアルタイム地図）、`/aircraft/<hex>/`（単機履歴）、`/about`（About / システム健康）、`/admin/`（Django admin、readonly tracking / editable registry cache）。3 言語切替（繁体中文 / 日本語 / 英語）。

JSON API：
- `/api/stats`：毎時 snapshot の統計データ（7 日 / 24h histogram、heatmap、top 10、peak alt、busiest hour）
- `/api/discover`：同じ毎時 snapshot の discovery curve、rare finds、altitude 分布、全 DB top 10 ICAO（`/stats` ページはこれと `/api/stats` を同時 fetch）
- `/api/live`：tar1090 リアルタイム機体（地図用、registry enrichment 含む、1 秒 TTL cache）
- `/api/aircraft?icao=`：単機履歴（registry + passes 集計、per-pass FROM / TO 含む）
- `/api/aircraft/track?icao=&from=&to=`：単一 pass の sightings_raw 軌跡（alt + gs profile chart 用）
- `/api/today?day=&sort=&country=&operator=&...`：home + details ページ用、rows + filter dropdown options
- `/api/summary?day=`：home ページ operator breakdown + total aircraft count
- `/api/about`：受信機 / feed ステータス
- `/api/me`：current user info（nav で login / account 表示の判定）
- `/api/health`：ヘルスチェック（200 / 503）

## 備考

- `samples` = 当日同一 ICAO が `sightings_raw` に出現した row 数
- `passes` = 20 分 gap で集計した通過回数
- `aircraft_route_snapshots` table：`browser_bulk_backfill` ごとに FR24 から from/to + その時の ADS-B ブロードキャスト callsign を `(icao, flight, from, to, observed_at)` として記録。`build_passes` 再構築時に `(icao, flight)` ごとの最新 snapshot を `aircraft_passes.from_airport / to_airport` に埋め、全 pass が registry の最新一件を共有するのではなく per-pass route を実現
- `/api/live` は module-level dict cache（process-local、restart で即クリア、Redis 不要）
- REG bulk backfill は Python `playwright` + `chromium` に依存（venv に install 済み）
- フロントエンドの Three.js + Leaflet は `static/vendor/` に self-host（`base.html` importmap で `three` を vendor に向け、Leaflet は `{% static %}`）、auth ページはサードパーティ実行可能 JS ゼロ、vendored LICENSE も同梱（THREE MIT / Leaflet BSD-2）。Radar 背景は `base.html` default `radar_bg` に統一、login / 管理ページにも表示。地図 tiles（cartocdn）+ planespotters 写真は外部のまま（画像、非実行）
- `push.connie.hk` は HMAC header 認証、Python notifier は `openssl + curl` で既存 shell 署名フローと互換
- Feed watchdog は alert 間で 6 時間 dedup、重複連投を回避；recovery（feed 復帰）時に `✓ recovered` confirm を 1 回送信
- `/coverage` と `/api/coverage` は cut（意味不明）、旧 URL は `/` に 301 redirect
- i18n：`/about/` は gettext + `.po`、他ページは `web/_legacy_strings.py` の STRINGS dict（過渡期）、cookie は `django_language` と legacy `lang` の両方を併存
