# UI Manual (MCP-First)

本プロジェクトは「MCP-First」。人間向け UI は検収・動作確認のための最小構成で、既定（デフォルト）では無効です。外部公開は推奨しません。必要なときだけローカルで有効化してください。

## 1. 前提
- DB: PostgreSQL 16 + pgvector（DB名は固定で `newshub`）
- スキーマ適用: `psql "$DATABASE_URL" -f db/schema_v2.sql && psql "$DATABASE_URL" -f db/indexes_core.sql`
- バインド先（固定）: `127.0.0.1:3011`（Nginx 等の外部公開はプロキシ層で実施）
- 既定では `/` は 404（UI 無効）。`UI_ENABLED=1` を設定した時のみ起動します。

## 2. 起動（ローカル）
```bash
# 依存は requirements.txt に含まれています
# UI を有効化して起動（localhost のみ）
export UI_ENABLED=1
uvicorn web.app:app --host 127.0.0.1 --port 3011 --reload
```

- UI 無効時の挙動: `/` は 404 を返します（MCP-First ポリシー）
- API は常時利用可（/api/*, /search, /search_sem）

## 3. 主要エンドポイント
- GET `/api/latest?limit=50`
  - 最新記事を JST で返却（内部保存は UTC）
- GET `/api/search?q=keyword&limit=50&offset=0[&source=...&since_days=7]`
  - タイトル ILIKE 検索
- GET `/api/search_sem?limit=20&offset=0[&space=e5-multilingual][&q=[...]]`
  - ベクトル検索（`q` は数値配列）。`q` 省略時は新着順フォールバック
- GET `/search`（エイリアス）
  - `/api/search` と同じ
- GET `/api/events?[type_id=...&participant_ext_id=Q...&loc_geohash=...]`
  - 事象の時系列・参加者・根拠ドキュメント ID を返却
- GET `/metrics`
  - Prometheus テキストフォーマット（`CONTENT_TYPE_LATEST`）

## 4. 動作確認（curl）
```bash
# 新着（3件）
curl 'http://127.0.0.1:3011/api/latest?limit=3' | jq .

# ILIKE 検索（上位5件）
curl 'http://127.0.0.1:3011/api/search?q=OpenAI&limit=5' | jq .

# セマンティック検索（q 省略 → フォールバック）
curl 'http://127.0.0.1:3011/api/search_sem?limit=3' | jq .

# イベント一覧（参加者 ext_id=Q... で絞り込み例）
curl 'http://127.0.0.1:3011/api/events?participant_ext_id=Q95' | jq .

# メトリクス（冒頭のみ）
curl -s 'http://127.0.0.1:3011/metrics' | head
```

## 5. セキュリティと公開
- 直接外部公開は推奨しません（UI は検証用）。必要時は SSH トンネル等で転送してください。
- 参考: `docs/ops/ssh_port_forwarding.md`
- Nginx で UI を閉じ、API のみ公開する例は `docs/マニュアル.md` のスニペット（deny_ui.conf）を参照。

## 6. トラブルシューティング
- `ImportError: fastapi/uvicorn`: `pip install -r requirements.txt` を実行
- `/` が 404 のまま: `UI_ENABLED=1` が設定されているか確認
- DB 接続エラー: `DATABASE_URL` が `.../newshub` を指すか、スキーマを適用済みか確認

