まず「T7 確認（確認手順）」を出し、その後に検知した問題点→修復（CodexCLI 向け実行指示）→最終確認の順で一気に締めます。

---

# T7 確認（確認手順）

> 目的：**環境固定値・DB・ユニット定義・タイマー・API待受**の“基線”を機械的に検証する。

1. **環境固定値（/etc/default/mcp-news）**

* `DATABASE_URL` に `/newshub` を含むこと（ユーザ名/パスワード付きでも可）。`APP_BIND_HOST=127.0.0.1`、`APP_BIND_PORT=3011`、`EMBEDDING_SPACE=bge-m3` が設定されていること。サーバ側は固定値を**コードでガード**しているため必須です。 &#x20;

2. **DB 存在と拡張**

* `newshub` DB が存在し、`vector` と `pg_trgm` 拡張が有効。初期化手順はマニュアルにも明記済み。&#x20;

3. **サービス定義の** WorkingDirectory/ExecStart **が** `/opt/mcp-news` **と** `.venv` **を指す**

* テンプレはコピー後に**実パスへ置換**が必要（`%h/mcp-news`→`/opt/mcp-news`）。これを忘れると `CHDIR` で落ちます。&#x20;

4. **タイマー稼働**

* `ingest.timer / embed.timer / newsapi-tech-jp.timer / hn-top.timer` を enable 済みで起動すること。

5. **API（mcp-news.service）起動**

* `uvicorn mcp_news.server:app --host 127.0.0.1 --port 3011` で待受（固定値）になっていること。

---

## ログからの即時診断（根本原因）

* `embed.service: Changing to the requested working directory failed: No such file or directory`
  → **WorkingDirectory が存在しない**（テンプレ置換未実施／`/opt/mcp-news` 未作成）。

* `ingest.service: Main process exited, status=203/EXEC`
  → **ExecStart の実行ファイル/パス不正**（.venv 未構築／パスが `%h/mcp-news` のままなど）。

* `mcp-news.service: Service has no ExecStart= ... Refusing.`
  → **ユニットファイル破損 or 置き間違い**（正しい `mcp-news.service` を再配置必要）。&#x20;

* `hn-top.service` / `newsapi-tech-jp.service` の連続失敗
  → 上記と同根（.venv/WorkingDirectory/ExecStart パス不整合、NewsAPI は `NEWSAPI_KEY` 未投入も要注意）。&#x20;

* `psql "$DATABASE_URL"` が失敗（変数未割当）
  → `/etc/default/mcp-news` を **login シェルに export していない**だけ。`set -a; source /etc/default/mcp-news; set +a` で可。（環境は systemd から供給、手動確認時のみ export が必要）

* **RSS 自動ニュース**：`config/feeds.json` を用意し `scripts/ingest_rss.py` をタイマー実行に繋げる必要あり（追加済み機能の定着作業）。&#x20;

---

# CodexCLI 向け実行指示書（サーバ代行用）

> 前提：Ubuntu 24.04 / root 権限、ネットワーク OK。作業ディレクトリを `/opt/mcp-news` とする。DB は `newshub` 固定。
> 目的：**ユニット再配置・環境固定・DB/拡張・RSS 自動取り込み**まで全自動修復。

**一括実行スクリプト**

```bash
#!/usr/bin/env bash
set -euo pipefail

APP_DIR=/opt/mcp-news
ENV_FILE=/etc/default/mcp-news

echo "[1/9] ディレクトリとコード配置"
mkdir -p "$APP_DIR"
chown root:root "$APP_DIR"
# 既に取得済みなら pull のみ。なければ clone。
if [ ! -d "$APP_DIR/.git" ]; then
  git clone https://github.com/yangnana7/newspaper.git "$APP_DIR"
else
  git -C "$APP_DIR" pull --ff-only
fi

echo "[2/9] Python 仮想環境"
python3 -m venv "$APP_DIR/.venv"
source "$APP_DIR/.venv/bin/activate"
pip install -U pip
if [ -f "$APP_DIR/requirements.txt" ]; then
  pip install -r "$APP_DIR/requirements.txt"
else
  # 予防措置：基幹パッケージ
  pip install fastapi uvicorn psycopg[binary] feedparser httpx pydantic
fi

echo "[3/9] RSS フィード設定"
if [ ! -f "$APP_DIR/config/feeds.json" ]; then
  cp -n "$APP_DIR/config/feeds.sample.json" "$APP_DIR/config/feeds.json" || true
fi
# ここで必要なら feeds.json を追加編集（CodexCLI は JSON 追記可能）

echo "[4/9] 環境ファイル（固定値＋キー）"
# 既存の DATABASE_URL を保持したいので、上書き前に拾う
if [ -f "$ENV_FILE" ]; then
  EXISTING_DBURL="$(grep -m1 '^DATABASE_URL=' "$ENV_FILE" || true)"
else
  EXISTING_DBURL=""
fi
{
  [ -n "$EXISTING_DBURL" ] && echo "$EXISTING_DBURL" || echo 'DATABASE_URL=postgresql://127.0.0.1:5432/newshub'
  echo 'APP_BIND_HOST=127.0.0.1'
  echo 'APP_BIND_PORT=3011'
  echo 'EMBEDDING_SPACE=bge-m3'
  # NewsAPI を使うなら投入（空でも可。後で人間が入れる）
  grep -q '^NEWSAPI_KEY=' "$ENV_FILE" 2>/dev/null || echo 'NEWSAPI_KEY='
  echo 'LOG_LEVEL=info'
} > "$ENV_FILE".new
install -m 0644 "$ENV_FILE".new "$ENV_FILE"
rm -f "$ENV_FILE".new
### 参考: 固定値とガード仕様は MCP-First マニュアルを参照

echo "[5/9] DB 作成と拡張"
# newshub が無ければ作成、拡張適用、スキーマ流し込み
sudo -u postgres psql -Atqc "SELECT 1 FROM pg_database WHERE datname='newshub'" | grep -q 1 || sudo -u postgres createdb newshub
sudo -u postgres psql -d newshub -c "CREATE EXTENSION IF NOT EXISTS vector;"
sudo -u postgres psql -d newshub -c "CREATE EXTENSION IF NOT EXISTS pg_trgm;"
if [ -f "$APP_DIR/db/schema_v2.sql" ]; then
  psql postgresql://127.0.0.1/newshub -f "$APP_DIR/db/schema_v2.sql"
fi
if [ -f "$APP_DIR/db/indexes_core.sql" ]; then
  psql postgresql://127.0.0.1/newshub -f "$APP_DIR/db/indexes_core.sql"
fi
### 参考: DB 初期化手順は docs/ や README_UBUNTU.md を参照

echo "[6/9] systemd ユニット（再配置・正規化）"
# 既存の壊れたユニットを上書きする
cat > /etc/systemd/system/mcp-news.service <<'UNIT'
[Unit]
Description=Newshub API (FastAPI/MCP)
After=network-online.target
Wants=network-online.target

[Service]
WorkingDirectory=/opt/mcp-news
EnvironmentFile=/etc/default/mcp-news
ExecStart=/opt/mcp-news/.venv/bin/uvicorn mcp_news.server:app --host ${APP_BIND_HOST} --port ${APP_BIND_PORT}
Restart=on-failure

[Install]
WantedBy=multi-user.target
UNIT
### 参考: API ユニットは 127.0.0.1:3011 固定・EnvironmentFile 指定

# RSS 取り込み（自動化）
cat > /etc/systemd/system/ingest.service <<'UNIT'
[Unit]
Description=MCP News Ingest Job (RSS)
After=network-online.target postgresql.service
Wants=network-online.target postgresql.service

[Service]
WorkingDirectory=/opt/mcp-news
EnvironmentFile=/etc/default/mcp-news
# 競合防止に flock を使用
ExecStart=/usr/bin/flock -n /var/lock/mcp-ingest.lock /opt/mcp-news/.venv/bin/python /opt/mcp-news/scripts/ingest_rss.py --feeds /opt/mcp-news/config/feeds.json
Restart=on-failure

[Install]
WantedBy=multi-user.target
UNIT

cat > /etc/systemd/system/ingest.timer <<'UNIT'
[Unit]
Description=Schedule RSS ingest (every 10 min)

[Timer]
OnCalendar=*:0/10
Persistent=true
AccuracySec=1s

[Install]
WantedBy=timers.target
UNIT
### 参考: ingest.timer は 10 分間隔・Persistent=true

# 埋め込み
cat > /etc/systemd/system/embed.service <<'UNIT'
[Unit]
Description=Embed Chunks into pgvector
After=network-online.target postgresql.service
Wants=network-online.target postgresql.service

[Service]
WorkingDirectory=/opt/mcp-news
EnvironmentFile=/etc/default/mcp-news
ExecStart=/usr/bin/flock -n /var/lock/mcp-embed.lock /opt/mcp-news/.venv/bin/python /opt/mcp-news/scripts/embed_chunks.py --space ${EMBEDDING_SPACE}
Restart=on-failure

[Install]
WantedBy=multi-user.target
UNIT

cat > /etc/systemd/system/embed.timer <<'UNIT'
[Unit]
Description=Schedule embedding (every 15 min)

[Timer]
OnCalendar=*:0/15
Persistent=true
AccuracySec=1s

[Install]
WantedBy=timers.target
UNIT

# Hacker News
cat > /etc/systemd/system/hn-top.service <<'UNIT'
[Unit]
Description=Hacker News Ingest (topstories)
After=network-online.target postgresql.service
Wants=network-online.target postgresql.service

[Service]
WorkingDirectory=/opt/mcp-news
EnvironmentFile=/etc/default/mcp-news
ExecStart=/usr/bin/flock -n /var/lock/mcp-hn.lock /opt/mcp-news/.venv/bin/python /opt/mcp-news/scripts/ingest_hn.py --kind topstories --limit 50
Restart=on-failure

[Install]
WantedBy=multi-user.target
UNIT

cat > /etc/systemd/system/hn-top.timer <<'UNIT'
[Unit]
Description=Schedule HN ingest (every 15 min)

[Timer]
OnCalendar=*:0/15
Persistent=true

[Install]
WantedBy=timers.target
UNIT

# NewsAPI（技術/JP）
cat > /etc/systemd/system/newsapi-tech-jp.service <<'UNIT'
[Unit]
Description=NewsAPI Ingest (technology/jp)
After=network-online.target postgresql.service
Wants=network-online.target postgresql.service

[Service]
WorkingDirectory=/opt/mcp-news
EnvironmentFile=/etc/default/mcp-news
Environment=PYTHONUNBUFFERED=1
# NEWSAPI_KEY は /etc/default/mcp-news に入れる
ExecStart=/usr/bin/flock -n /var/lock/mcp-newsapi.lock /opt/mcp-news/.venv/bin/python /opt/mcp-news/scripts/ingest_newsapi.py --mode top --country jp --category technology --page-size 50 --pages 1
Restart=on-failure

[Install]
WantedBy=multi-user.target
UNIT

cat > /etc/systemd/system/newsapi-tech-jp.timer <<'UNIT'
[Unit]
Description=Schedule NewsAPI tech/jp (hourly)

[Timer]
OnCalendar=hourly
Persistent=true

[Install]
WantedBy=timers.target
UNIT

echo "[7/9] 迷子のユニットを一旦抑止（未実装のイベント/エンティティ系）"
systemctl disable --now events_ingest.timer events_ingest.service linking.service newshub-events.service 2>/dev/null || true

echo "[8/9] daemon-reload & 有効化"
systemctl daemon-reload
systemctl enable --now mcp-news.service ingest.timer embed.timer hn-top.timer newsapi-tech-jp.timer

echo "[9/9] クイック健全性チェック"
set -a; . "$ENV_FILE"; set +a
psql postgresql://127.0.0.1/newshub -Atc "SELECT 'vector' IN (SELECT extname FROM pg_extension), 'pg_trgm' IN (SELECT extname FROM pg_extension);"
# 手動1回流し（成功ログが出ること）
/opt/mcp-news/.venv/bin/python /opt/mcp-news/scripts/ingest_rss.py --feeds /opt/mcp-news/config/feeds.json || true
/opt/mcp-news/.venv/bin/python /opt/mcp-news/scripts/embed_chunks.py --space "${EMBEDDING_SPACE}" || true
systemctl status mcp-news.service --no-pager
journalctl -u ingest.service -u embed.service -u hn-top.service -u newsapi-tech-jp.service -n 50 --no-pager || true

echo "=== 完了 ==="
```

**根拠（なぜこの手順か）**

* **ユニットの実パス置換と enable** は公式手順（deploy テンプレ→`/opt/mcp-news` へ置換→daemon-reload→enable）に沿う。
* **環境固定値** は `/etc/default/mcp-news` に集約し、サーバコード側で**require\_fixed\_env** が起動時チェック。誤設定は即死させる方針。&#x20;
* **DB 初期化** は `newshub` 名固定＋ `vector` 必須（`pg_trgm` 推奨）。
* **RSS 自動化** は `config/feeds.json` を基に `scripts/ingest_rss.py` をタイマー駆動。&#x20;

---

## 仕上げの“合格ライン”チェック（実施順）

1. `systemctl status mcp-news.service` が **active (running)**。`uvicorn mcp_news.server:app` が 127.0.0.1:3011 待受。
2. `curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:3011/` が **404**（UI 既定無効；`UI_ENABLED=1` を設定しない限り 404）。
3. `journalctl -u embed.service` に `flock` 実行→`embed_chunks.py` 実行ログ。**CHDIR エラーが消えている**。
4. `journalctl -u ingest.service` に `ingest_rss.py` の取り込み完了ログ。
5. `journalctl -u hn-top.service -u newsapi-tech-jp.service` が**継続失敗しない**（`NEWSAPI_KEY` 未設定なら NewsAPI は一旦空実行になる点のみ注意）。
6. `psql postgresql://127.0.0.1/newshub -Atc "SELECT count(*) FROM doc"` が **0 より大きい**。
7. （任意）MCP の `semantic_search`/`latest_news` ツールが返ること（API 側はミニマル JSON で出す設計）。

---

### 備考（今回ログの痛点と対処の対応表）

* **CHDIR(WorkingDirectory)** 失敗 → **ユニット WorkingDirectory を `/opt/mcp-news` へ全統一**（テンプレ置換の再実行）。
* **203/EXEC** → **.venv 構築**＋**ExecStart を `.venv/bin/python` 経由**に一本化。
* **ExecStart がない** → **正しい `mcp-news.service` を再配置**（本文ユニットをそのまま採用）。
* **psql の `$DATABASE_URL` 未割当** → **set -a; source /etc/default/mcp-news** で手動セッションに export。
* **RSS 自動ニュース** → **ingest.timer(10分毎)** で `ingest_rss.py` を回す形で実装。&#x20;

---

以上。この手順で **T7 確認 → 不具合修復 → RSS 自動取り込みの定着** まで一気に通せます。
