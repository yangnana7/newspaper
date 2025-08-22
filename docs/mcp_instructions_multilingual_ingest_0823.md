# MCPニュース基盤 — 実装指示書（多言語対応＋自動蓄積）
日付: 2025-08-23
対象: Ubuntu Server 24.04 LTS / PostgreSQL 16 / Python 3.11 / pgvector

## 目的
- 言語カバレッジを拡張（韓/露/中文/阿/仏など）し、検索・抽出の多言語性を底上げ。
- ニュースの **毎日自動蓄積**（RSS/Atom中心）を systemd タイマーで常時実行。
- MCPサーバを最終化し、AIエージェントが工具（Tools）経由で検索・要約・証拠提示まで到達可能に。

---

## A. 多言語埋め込み（検索用）
### A-1. モデルと空間
- 既定空間を **`e5-multilingual`** とする（768次元・cos想定）。
- 既存の `bge-m3` インデックスは残置。以下を追加：

```sql
-- db/indexes_core.sql か専用マイグレーションに追記
CREATE INDEX IF NOT EXISTS idx_chunk_vec_hnsw_e5_cos
  ON chunk_vec USING hnsw (emb vector_cosine_ops)
  WHERE embedding_space='e5-multilingual';
```

### A-2. 埋め込み生成
```bash
export DATABASE_URL=postgresql://localhost/newshub
export EMBEDDING_MODEL=intfloat/multilingual-e5-base
# 既定の空間名を e5-multilingual に
python scripts/embed_chunks.py --space e5-multilingual --normalize  # 未ベクトル化分のみ
```

> **要件**: `--normalize`（単位長正規化）を必須に。cos距離と整合。

### A-3. ランク融合側の既定
```
export RANK_ALPHA=0.7
export RANK_BETA=0.2
export RANK_GAMMA=0.1
export RECENCY_HALFLIFE_HOURS=24
export SOURCE_TRUST_DEFAULT=1.0
export SOURCE_TRUST_JSON='{}'
export EMBED_SPACE=e5-multilingual
```

---

## B. 多言語エンティティ抽出スタブ拡張
### B-1. 追加言語の簡易規則
- **韓国語**: Hangul 連続語 `[\uAC00-\uD7AF]{2,}`
- **ロシア語**: Cyrillic `[\u0400-\u04FF\u0500-\u052F]{2,}`
- **中国語**: 漢字列 `[\u4E00-\u9FFF]{2,5}` を表層語（surface）として抽出（長すぎる語は分割）
- **アラビア語**: `[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF]{2,}`
- **フランス語**: 英字規則で代替（既存の EN パターンで十分）

> 実装: `scripts/entity_link_stub.py` の `extract_terms()` に正規表現ブロックを追加。`kind` は `surface`、`conf=0.3`。衝突抑止のため言語別接頭辞（例: `kr:` `ru:` `zh:` `ar:`）で de-dup。

### B-2. 将来の本実装（任意有効化）
- ja: SudachiPy（辞書: small）/ spaCy ja_core_news_md
- zh: jieba
- ar: camel_tools（分かち書き＋NERが重いので任意）
> 上記は **環境変数で ON/OFF**。未導入環境では正規表現のみで可。

### B-3. テスト（pytest）
- `tests/test_entity_stub_ko_ru_zh_ar_fr.py` を新規追加。
  - 各言語1フレーズを与え `kinds` に `surface` が含まれること。
  - 重複抑止が効くこと（同一語の多重挿入が無い）。

---

## C. 毎日自動蓄積（systemd タイマー）
### C-1. 環境ファイル `/etc/newshub.env`
```ini
DATABASE_URL=postgresql://localhost/newshub
ENABLE_SERVER_EMBEDDING=1
EMBEDDING_MODEL=intfloat/multilingual-e5-base
EMBED_SPACE=e5-multilingual
RANK_ALPHA=0.7
RANK_BETA=0.2
RANK_GAMMA=0.1
RECENCY_HALFLIFE_HOURS=24
SOURCE_TRUST_DEFAULT=1.0
SOURCE_TRUST_JSON={}
WORKDIR=/opt/newspaper
FEEDS_FILE=/opt/newspaper/config/feeds.json
VENV=/opt/newspaper/.venv
```

### C-2. 取り込みサービス `/etc/systemd/system/newshub-ingest@.service`
```ini
[Unit]
Description=Newshub RSS ingest (%i)
After=network-online.target postgresql.service

[Service]
Type=exec
EnvironmentFile=/etc/newshub.env
WorkingDirectory=%E{WORKDIR}
ExecStart=%E{VENV}/bin/python scripts/ingest_rss.py --feeds %E{FEEDS_FILE} --source RSS
Nice=10
Restart=on-failure
```

### C-3. 取り込みタイマー `/etc/systemd/system/newshub-ingest@.timer`
```ini
[Unit]
Description=Newshub RSS ingest timer (%i)

[Timer]
OnCalendar=hourly
RandomizedDelaySec=600
Persistent=true
Unit=newshub-ingest@%i.service

[Install]
WantedBy=timers.target
```

> 有効化:  
```bash
sudo systemctl daemon-reload
sudo systemctl enable --now newshub-ingest@$(whoami).timer
journalctl -u newshub-ingest@$(whoami).service -f
```

### C-4. 埋め込みサービス（任意だが推奨）
- 1時間ごとに未ベクトル化の chunk を処理：`scripts/embed_chunks.py --space e5-multilingual`
- 同様の `newshub-embed@.service/.timer` を用意（CPU負荷に応じて `OnCalendar=hourly`/`daily`）。

---

## D. MCPサーバの最終化（Tools 公開）
### D-1. 提供ツール（stdio）
- `semantic_search(q: float[], top_k: int=20, since_iso?: str, space?: str)`
- `entity_search(ext_ids: str[], top_k: int=20)`
- `event_timeline(filter: json, top_k: int=50)`
- `doc_head(doc_id: int)`

> すべて **失敗時は新着順フォールバック** を保証。Webの再ランク関数を共通化して呼び出し。

### D-2. 起動
```bash
source /opt/newspaper/.venv/bin/activate
export $(grep -v '^#' /etc/newshub.env | xargs -d '\n' )
python -m mcp_news.server
```

### D-3. 受入
- `tools/list` 相当で上記4ツールが列挙され、`semantic_search` が **再ランク** を反映。
- 3言語以上（ja/en/zh 等）でヒットし、`doc_head` が ISO-8601(JST表現) を返す。

---

## E. ランク融合の一本化
- WebとMCPの実装を **単一モジュール** に寄せる（例: `search/ranker.py`）。
- 係数とハーフライフは環境変数で共通読込（未設定時は既定値）。
- ベンチ: `scripts/eval_recall_stub.py`＋`eval/queries.json` で recall@k を採取。

---

## F. 運用・監視
- `journalctl -u newshub-* -n 200 --no-pager` で障害一次確認。
- `psql` で日次件数を監視：`SELECT date_trunc('day', first_seen_at) d, count(*) FROM doc GROUP BY 1 ORDER BY 1 DESC;`
- 近重複抑止：`url_canon UNIQUE`＋`hash_body` 併用。hash衝突時の上書きポリシーは後続。

---

## G. セキュリティ・コンプライアンス（要チェック）
- 各RSSのTOSとrobotsを遵守。User-Agentを明示（`scripts/ingest_rss.py`）。
- 失敗時のバックオフ／再試行、レート制御。

---

## H. 受入基準（Definition of Done）
- (1) 1日あたりRSSが自動取り込みされ、**日次でdocが増加**している。
- (2) `/api/search_sem` と MCP `semantic_search` が **同じ順序の再ランク結果** を返す。
- (3) 多言語（ja/ko/ru/zh/ar/fr のうち ≥4）で **最低1つ以上の mention** が抽出される。
- (4) `eval/queries.json` で **recall@10 ≥ 0.5**（暫定基準）を達成。
- (5) すべてのCIがグリーン、systemd タイマーが `active`。
