# 整合性チェック（差戻し/注意点）

良い:

* **環境ファイルの保全**と**UIデフォルトOFF**は、こちらの運用原則と一致（UIは開発時のみ `UI_ENABLED=1`。MCP優先）です。&#x20;
* **固定不変条件**（DB名 `newshub`、バインド `127.0.0.1:3011`、ベクトル次元 `vector(768)`、距離=cos）は明文化済みで一致。

要注意（必ず是正/確認して進める）:

* **HNSWインデックスの演算子クラス**
  設計v2のドラフト断片に `vector_l2_ops` が残っている箇所がありましたが、最終運用は **cos 距離（`vector_cosine_ops`）固定**です。インデックス作成は「`USING hnsw (emb vector_cosine_ops)`」としてください。

# 72時間分ログからの障害の芯（＝今回の修復ターゲット）

1. **embed.service**: `(flock) … Changing to the requested working directory failed: No such file or directory`
   → WorkingDirectory が存在しない/誤り。`/opt/mcp-news` を作らずに走らせている、または unit の `WorkingDirectory=` がズレ。

2. **ingest.service**: `status=203/EXEC`
   → `ExecStart=` コマンドが存在しない/権限なし/パス誤り。

3. **mcp-news.service**: `Service has no ExecStart=`
   → unit ファイル破損（`ExecStart` 無し）／テンプレート `newshub-api@.service` と実ファイルの混同。

4. **newsapi-tech-jp / hn-top**: timer は起動するが service 実体が失敗
   → 実行パスの `%h` 置換未実施 or `.venv` パス未置換。ドキュメント上は `sed` で `/opt/mcp-news` へ置換必須。

5. **psql 実行エラー**: 「`$DATABASE_URL` 未割当」や「`yang_server` 不明」
   → シェルが `set -u` 等で未定義変数をエラーにしているか、環境ファイル未 `source`。`/etc/default/mcp-news` から **安全に `DATABASE_URL` を読み出す**手順に直す。

6. **RSS 自動取り込み**（新機能）
   → `ingest_rss.py` を timer に組み込む（または既存 ingest に統合）。`config/feeds.json` の配置確認。

# CodexCLI への実行指示書（サーバ代行用・そのまま投下可）

> 方針: 破壊的変更を避け、「存在確認→修正→検証→受入」の順。**DB=newshub** / **bind=127.0.0.1:3011** / **vector(768)+cos** を強制。UIは既定OFF。

```bash
set -Eeuo pipefail

# 0) 前提ディレクトリ
sudo mkdir -p /opt/mcp-news /opt/mcp-news/logs /opt/mcp-news/tmp
sudo chown -R "$USER":"$USER" /opt/mcp-news || true

# 1) 環境ファイルの読み出し（未定義でも死なない形で）
db_url="$(grep -E '^DATABASE_URL=' /etc/default/mcp-news | cut -d= -f2- || true)"
app_host="$(grep -E '^APP_BIND_HOST=' /etc/default/mcp-news | cut -d= -f2- || true)"
app_port="$(grep -E '^APP_BIND_PORT=' /etc/default/mcp-news | cut -d= -f2- || true)"
: "${app_host:=127.0.0.1}"; : "${app_port:=3011}"

# 2) unit ファイルの健全化（存在しなければ安全に再作成）
create_unit() {
  local name="$1" ; shift
  local content="$1" ; shift || true
  if ! sudo test -s "/etc/systemd/system/${name}"; then
    printf '%s\n' "$content" | sudo tee "/etc/systemd/system/${name}" >/dev/null
    echo "[info] installed ${name}"
  else
    echo "[skip] ${name} exists"
  fi
}

create_unit mcp-news.service "[Unit]
Description=Newshub API (FastAPI/MCP)
After=network-online.target
Wants=network-online.target

[Service]
WorkingDirectory=/opt/mcp-news
EnvironmentFile=/etc/default/mcp-news
ExecStart=/opt/mcp-news/.venv/bin/uvicorn mcp_news.server:app --host \${APP_BIND_HOST} --port \${APP_BIND_PORT}
Restart=on-failure

[Install]
WantedBy=multi-user.target
"

create_unit ingest.service "[Unit]
Description=MCP News Ingest Job (RSS/NewsAPI/HN)
After=network-online.target
Wants=network-online.target

[Service]
WorkingDirectory=/opt/mcp-news
EnvironmentFile=/etc/default/mcp-news
ExecStart=/opt/mcp-news/.venv/bin/python /opt/mcp-news/scripts/ingest_rss.py --feeds /opt/mcp-news/config/feeds.json
Restart=on-failure
"

create_unit ingest.timer "[Unit]
Description=Every 10 minutes: ingest RSS

[Timer]
OnBootSec=3m
OnUnitActiveSec=10m
AccuracySec=30s
Unit=ingest.service

[Install]
WantedBy=timers.target
"

create_unit embed.service "[Unit]
Description=Embed Chunks into pgvector
After=network-online.target
Wants=network-online.target

[Service]
WorkingDirectory=/opt/mcp-news
EnvironmentFile=/etc/default/mcp-news
ExecStart=/opt/mcp-news/.venv/bin/python /opt/mcp-news/scripts/embed_chunks.py --space \${EMBEDDING_SPACE}
Restart=on-failure
"

create_unit embed.timer "[Unit]
Description=Hourly: build embeddings

[Timer]
OnBootSec=5m
OnUnitActiveSec=60m
AccuracySec=1m
Unit=embed.service

[Install]
WantedBy=timers.target
"

# 既存の newsapi-tech-jp / hn-top があれば ExecStart の実体パスを検証
for s in newsapi-tech-jp.service hn-top.service; do
  if sudo test -s "/etc/systemd/system/$s"; then
    sudo sed -i 's#%h/mcp-news#/opt/mcp-news#g;s#%h/mcp-news/.venv#/opt/mcp-news/.venv#g' "/etc/systemd/system/$s"
  fi
done

sudo systemctl daemon-reload

# 3) DB 健全化（newshub + pgvector + スキーマ + インデックス）
if [ -n "${db_url}" ]; then
  psql "${db_url}" -Atc "SELECT 'ok'::text" >/dev/null || true
fi

# postgres 管理者接続で最低限の存在を保証（idempotent）
sudo -u postgres psql -v ON_ERROR_STOP=1 <<'PSQL'
DO $$ BEGIN PERFORM 1 FROM pg_database WHERE datname='newshub';
IF NOT FOUND THEN EXECUTE 'CREATE DATABASE newshub'; END IF; END $$;
\c newshub
CREATE EXTENSION IF NOT EXISTS vector;

-- スキーマ（存在チェック付きの簡易DDL: 本番は schema_v2.sql を使う）
CREATE TABLE IF NOT EXISTS doc(
  doc_id BIGSERIAL PRIMARY KEY,
  source TEXT NOT NULL,
  url_canon TEXT UNIQUE,
  title_raw TEXT NOT NULL,
  published_at TIMESTAMPTZ NOT NULL,
  first_seen_at TIMESTAMPTZ DEFAULT now(),
  raw JSONB
);

CREATE TABLE IF NOT EXISTS chunk(
  chunk_id BIGSERIAL PRIMARY KEY,
  doc_id BIGINT REFERENCES doc(doc_id) ON DELETE CASCADE,
  part_ix INT NOT NULL,
  text_raw TEXT NOT NULL,
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS chunk_vec(
  chunk_id BIGINT REFERENCES chunk(chunk_id) ON DELETE CASCADE,
  embedding_space TEXT NOT NULL,
  dim INT NOT NULL,
  emb vector NOT NULL,
  PRIMARY KEY (chunk_id, embedding_space)
);

-- HNSW を cos で（L2は禁止）
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_indexes WHERE indexname='chunk_vec_emb_hnsw_bge_m3_cos'
  ) THEN
    EXECUTE 'CREATE INDEX chunk_vec_emb_hnsw_bge_m3_cos ON chunk_vec USING hnsw (emb vector_cosine_ops) WHERE embedding_space=''bge-m3''';
  END IF;
END $$;
PSQL

# 4) サービス起動
sudo systemctl enable --now mcp-news.service ingest.timer embed.timer || true
sudo systemctl enable --now newsapi-tech-jp.timer hn-top.timer 2>/dev/null || true

# 5) 受入チェック（UI OFF時の 404 / API 200）
code_=/usr/bin/curl -s -o /dev/null -w '%{http_code}\n'
${code_} "http://${app_host}:${app_port}/" || true    # 期待: 404
${code_} "http://${app_host}:${app_port}/search?q=hello" || true  # 期待: 200 or 204 (空)

# 6) 診断スナップショット
( set -x
  sudo systemctl list-timers --all | egrep 'ingest|embed|newsapi|hn|mcp-news' || true
  sudo systemctl --no-pager -l status mcp-news.service | sed -n '1,120p'
  sudo systemctl --no-pager -l status ingest.service   | sed -n '1,120p'
  sudo systemctl --no-pager -l status embed.service    | sed -n '1,120p'
  journalctl --since '2 hours ago' -u mcp-news.service -u ingest.service -u embed.service -p info --no-pager | tail -n 200
  db_url_now="$(grep -E '^DATABASE_URL=' /etc/default/mcp-news | cut -d= -f2- || true)"; \
  [ -n "$db_url_now" ] && psql "$db_url_now" -Atc "SELECT extname FROM pg_extension WHERE extname IN ('vector') ORDER BY 1;" || true
) | tee /opt/mcp-news/logs/T7-postfix.log
```

# ログと報告書は「書かせる」べき？

**はい、必須です。** 今回の障害は unit/WorkingDirectory/ExecStart の齟齬と DB 準備の不備が混在しており、**修復の追跡性**が重要です。以下の成果物を Codex に必ず生成させてください。

* 実行ログ（そのまま吐き出し）

  * `/opt/mcp-news/logs/T7-postfix.log`（上スクリプトで作成）
  * 追加で:

    ```bash
    journalctl --since '24 hours ago' -u mcp-news.service -u ingest.service -u embed.service -u newsapi-tech-jp.service -u hn-top.service --no-pager > /opt/mcp-news/logs/T7-journey.log
    ```
* 受入チェック結果の要約（Markdown）: `docs/T7-run-report.md`
  最低項目:

  1. **MCP-First検証**: `GET /` が 404（UI\_OFF）、`/search` は 200/204。
  2. **不変条件**: DB=`newshub` / 127.0.0.1:3011 / `vector(768)+cos` を設定とDDL/Indexで確認。
  3. **pgvector**: `CREATE EXTENSION vector;` 済み、`chunk_vec` あり、HNSW が **`vector_cosine_ops`**。
  4. **timer**: `ingest.timer / embed.timer / newsapi-tech-jp.timer / hn-top.timer` が *active*。
  5. **取り込み**: `doc` 件数/最新 `published_at` のサマリ（空でもOK、0件ならRSS設定の有無も併記）。
  6. **エラー再発**: embed/ingest の `(CHDIR/203/EXEC)` が解消されていること。

> なお、**cos距離のHNSW**だけはレッドラインです。`vector_l2_ops` が残っていないかを報告書に**明示**させてください（誤っていたら即DDL修正）。

---

この方針で進めれば、今回の大量の `Failed to start …` は **WorkingDirectory/ExecStart の復旧**と**DB/pgvectorの初期化**で止まります。`/etc/default/mcp-news` は **既存の `DATABASE_URL` を維持**のまま使い、`psql` はファイルから確実に読み出す形に統一してください。

