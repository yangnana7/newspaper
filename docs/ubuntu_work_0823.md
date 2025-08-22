# Ubuntu検証 0823 手順（AIエージェント実行用）

本手順は 0823 指示の検証観点（ランク融合・検索API・インデックス）に沿って、確認項目・必要レポート・ログの記入方法を定義します。実施後は docs/verification_report.md に結果を転記してください。

**固定条件**
- DB: `newshub`
- バインド: `127.0.0.1:3011`（外部公開はNginxで終端、アプリはローカル待受）
- ベクトル/距離: `vector(768)`、cosine `<=>`
- TZ: DB=UTC、UI/API=JST

---

## 0. 事前準備（環境）
- パッケージ: `python3.11 python3.11-venv python3-pip postgresql postgresql-contrib postgresql-16-pgvector`
- venv: `python3 -m venv /opt/mcp-news/.venv && source /opt/mcp-news/.venv/bin/activate`
- 依存: `pip install -U pip && pip install -r requirements.txt`
- 変数: `export PYTHONPATH=.`
- 推奨Envファイル `/etc/default/mcp-news` を用意（既存の ubuntu_work.md を参照）

レポート記入:
- docs/verification_report.md の「1. 環境情報」に以下を貼付
  - `cat /etc/os-release`
  - `python --version` / `psql --version`
  - `git rev-parse --short HEAD`
  - 使用した環境変数（抜粋）

---

## 1. DB初期化・拡張・スキーマ
チェック項目:
- vector/pg_trgm拡張の導入
- schema/indexes の適用エラー無し

実行コマンド:
- 拡張/DB作成:
  - `sudo -u postgres psql <<'SQL'\nCREATE DATABASE newshub;\n\\c newshub\nCREATE EXTENSION IF NOT EXISTS vector;\nCREATE EXTENSION IF NOT EXISTS pg_trgm;\nSQL`
- スキーマ/インデックス適用:
  - `psql "$DATABASE_URL" -f db/schema_v2.sql`
  - `psql "$DATABASE_URL" -f db/indexes_core.sql`
- 存在確認:
  - `psql "$DATABASE_URL" -c "SELECT to_regclass('doc'), to_regclass('chunk'), to_regclass('chunk_vec');"`
  - `psql "$DATABASE_URL" -c "SELECT indexname FROM pg_indexes WHERE tablename IN ('doc','hint','chunk_vec') ORDER BY 1;"`

レポート記入（コピー&ペースト）:
- 「2. スキーマ/インデックス適用ログ」に各コマンドの出力を ``` で囲って貼付

---

## 2. 最小データ投入・埋め込み
チェック項目:
- doc/chunk/hint の投入が成功
- `chunk_vec` に bge-m3 埋め込みが作成される

実行コマンド:
- サンプル投入（1件）:
  - `psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -c "INSERT INTO doc (source,url_canon,title_raw,published_at,first_seen_at,raw) VALUES ('test://local','https://example.com/1','Hello World', now() at time zone 'UTC', now() at time zone 'UTC', '{}'::jsonb) ON CONFLICT (url_canon) DO NOTHING;"`
  - `psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -c "WITH d AS (SELECT doc_id FROM doc WHERE url_canon='https://example.com/1') INSERT INTO chunk (doc_id,part_ix,text_raw,lang,created_at) SELECT d.doc_id,0,'Hello world body for semantic search','en', now() at time zone 'UTC' FROM d ON CONFLICT DO NOTHING;"`
  - `psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -c "WITH d AS (SELECT doc_id FROM doc WHERE url_canon='https://example.com/1') INSERT INTO hint (doc_id,key,val,conf) SELECT d.doc_id,'genre_hint','news',0.8 FROM d ON CONFLICT (doc_id,key) DO UPDATE SET val = EXCLUDED.val, conf = EXCLUDED.conf;"`
- 埋め込み（任意だが推奨）:
  - `python scripts/embed_chunks.py --space bge-m3 --batch 64`
  - `psql "$DATABASE_URL" -c "SELECT COUNT(*) FROM chunk_vec WHERE embedding_space='bge-m3';"`

レポート記入:
- 「3. データ投入/埋め込み」に投入件数ログと `COUNT(*)` 結果を ``` で貼付

---

## 3. HTTPアプリ起動
チェック項目:
- `127.0.0.1:3011` で起動

実行コマンド（どちらか）:
- 開発起動: `mkdir -p web/static && uvicorn web.app:app --host 127.0.0.1 --port 3011`
- systemd: `newshub-api@${USER}.service`（ubuntu_work.md の unit 例を参照）

レポート記入:
- 「4. API 疎通」に起動ログの先頭～数行を ``` で貼付（journalctl でも可）

---

## 4. API 検証（疎通）
チェック項目:
- latest / search / search_sem（q無し）が 200 で配列を返す

実行コマンド:
- 最新: `curl -s "http://127.0.0.1:3011/api/latest?limit=5"`
- ILIKE: `curl -s "http://127.0.0.1:3011/api/search?q=Hello&limit=5&offset=0"`
- セマンティック（q無し）: `curl -s "http://127.0.0.1:3011/api/search_sem?limit=3"`

レポート記入:
- 各レスポンスの先頭 1–3 件を整形して ``` で貼付（jq があれば `| jq .` 推奨）。

---

## 5. ランク融合の検証（0823 重点）
目的:
- α/β/γ、半減期、ソース信頼度の変更が並び順に影響することを確認

前提Env（例）:
- `export RANK_ALPHA=0.7 RANK_BETA=0.2 RANK_GAMMA=0.1`
- `export RECENCY_HALFLIFE_HOURS=24`
- `export SOURCE_TRUST_JSON='{"NHK 総合":1.1,"BBC News":1.0}'`

ケースA: 既定設定
- コマンド: `curl -s --get --data-urlencode "q=[0.0,0.0,0.0]" "http://127.0.0.1:3011/api/search_sem?limit=5&space=bge-m3"`
- レポート: タイトル/時刻/ソースを 5 件貼付。

ケースB: 新着重視（半減期を短縮）
- `export RECENCY_HALFLIFE_HOURS=1`
- 同コマンドを再実行し、結果を貼付。
- 記述: ケースA→B で新しい記事が上位化したかを所感で記述（どの doc_id が上がったか）。

ケースC: ソース信頼度の影響
- `export SOURCE_TRUST_JSON='{"test://local":1.2}'`（サンプルに合わせて source 名を調整）
- 同コマンドを再実行し、結果を貼付。
- 記述: `test://local` が含まれる場合の順位変化を所感で記述。

注意:
- ベクトルが無い環境では空配列になることがあります（q指定時）。その場合、ケースAは q無しでのフォールバック結果を併記してください。

---

## 6. 実行計画（任意だが推奨）
- ILIKE+trgm: `psql "$DATABASE_URL" -c "EXPLAIN ANALYZE SELECT * FROM doc WHERE title_raw ILIKE '%Hello%' ORDER BY published_at DESC LIMIT 10;"`
- semantic 先頭候補: `psql "$DATABASE_URL" -c "EXPLAIN ANALYZE SELECT d.doc_id, v.emb <=> '[0,0,0]'::vector(768) FROM chunk_vec v JOIN chunk c USING(chunk_id) JOIN doc d USING(doc_id) WHERE v.embedding_space='bge-m3' ORDER BY v.emb <=> '[0,0,0]'::vector(768) LIMIT 10;"`

レポート記入:
- 「6. パフォーマンス・実行計画」に両方のEXPLAIN結果を ``` で貼付。

---

## 7. 既知の注意点/課題
- モデルDLやネットワーク制約、HNSW構築時間
- ベクトル未作成時の挙動（q指定=空配列、q無し=新着）

レポート記入:
- 「7. 既知の注意点/課題」に箇条書きで追記。

---

## 8. 提出（docs/verification_report.md）
- 各セクションに本手順で得たログ/所感を転記
- 可能なら `docs/logs/2025-08-23/` などに原文ログを保存し、パスを併記
- 最後に「8. 結論」に Pass/Fail と改善提案を一言でまとめる

---

## 付録: 便利コマンド
- JSON整形: `sudo apt install -y jq`、`curl ... | jq .`
- 稼働確認: `ss -ltnp | grep :3011`、`journalctl -u newshub-api@${USER}.service -n 100 --no-pager`
- 環境変数確認: `env | egrep 'DATABASE_URL|EMBED|RANK_|RECENCY|SOURCE_TRUST'`

