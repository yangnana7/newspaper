# 議事録（MCPニュース／CI安定化）

日時：2025-08-26（火）JST

## 目的

* `master` 更新後に赤転した CI を原因特定→修正して安定化。
* CodexCLI 向けタスク群と実装状況を同期。
* 明日の着手項目を決める。

---

## 本日のハイライト（結論）

* **CIは最終的に緑化**。主因は段階的に3点：

  1. SimHashが `hash()` 由来で**非決定的** → **SHA-256→64bit**に置換で安定化。
  2. CIのDB/環境整備：**pgvector付きPostgres**、ENV（`EMBEDDING_SPACE/EMBED_SPACE` 両対応、`UI_ENABLED=0`）明示、`grep -E` に置換。
  3. DB周りのテスト整合：

     * `doc.source` の **NOT NULL** → テスト側で `source='test'` を明示。
     * `jsonb_build_object('name', %s)` の **型不定（IndeterminateDatatype）** → **`%s::text`** に統一。
     * `mention.span` **NOT NULL + PK** → **`int4range(0,0)`** を固定挿入（将来はオフセットで更新可）。

---

## 実施内容（時系列）

### Round 1：安定化の土台

* `search/near_duplicate.py`

  * `hash()` → \*\*SHA-256先頭8B（64bit）\*\*でSimHash決定論化。
* `.github/workflows/ci.yml`

  * DBサービスを **`pgvector/pgvector:pg16`** に変更。
  * `DATABASE_URL` を `postgresql://postgres:postgres@localhost:5432/newshub`。
  * `EMBEDDING_SPACE` / `EMBED_SPACE` を両方設定、`UI_ENABLED=0` を明示。
  * `rg` → **`grep -E`** に置換。
  * スキーマ適用：`CREATE EXTENSION vector/pg_trgm` → `db/schema_v2.sql` → `db/indexes_core.sql`。
* `mcp_news/config_guard.py` / `mcp_news/server.py`

  * ガード導入。`EMBEDDING_SPACE` or `EMBED_SPACE` の**両受け**、`/newshub`、`127.0.0.1:3011` を **Fail-Fast**。

### Round 2：DB整合テストの潰し込み

* `tests/test_entity_upsert.py`

  * 準備INSERTで **`doc.source` を明示**。
  * `chunk` カラム名の整合（`part_ix`）、挿入後に **`commit()`** → 別接続で可視化。
* `scripts/entity_link.py`

  * フォールバック抽出を \*\*カタカナ＋漢字の連続列（3文字以上）\*\*に強化。

### Round 3：型推論・NOT NULL 由来の赤を解消

* `scripts/ingest_entities.py`

  * 1発目INSERTは既に `::text` 化済み。
  * **フォールバックINSERTにも `jsonb_build_object('name', %s::text)` を適用**（型不定解消）。
* 同テスト再実行で次の赤：`mention.span` の **NOT NULL**

  * `INSERT INTO mention ... VALUES (%s, %s, **int4range(0,0)**, 1.0) ON CONFLICT DO NOTHING` に変更。
  * 必要に応じて **`ALTER TABLE mention ALTER COLUMN span SET DEFAULT int4range(0,0);`** のマイグレーション案も提示（任意）。

---

## 変更ファイル（要点）

* 追加：`mcp_news/config_guard.py`
* 更新：`mcp_news/server.py`、`.github/workflows/ci.yml`、`search/near_duplicate.py`、`scripts/ingest_entities.py`、`tests/test_entity_upsert.py`
* 既存の運用関連（参考／別途）：`deploy/linking.service|timer`、`deploy/events_ingest.service|timer`、`docs/UI_MANUAL.md`

---

## 決定事項

* MCP-First 準拠：**既定は UI 無効（`UI_ENABLED=0`）／ルートは 404**。
* 埋め込み空間ENVは **`EMBEDDING_SPACE` を主**としつつ **`EMBED_SPACE` も許容**。
* 近重複クラスタは **決定論的SimHash** を採用。
* `mention.span` は **空レンジ `int4range(0,0)` を既定**（将来精密化）。

---

## 残タスク／保留

* （任意の安全策）`mention.span` に **DEFAULT int4range(0,0)** を与えるマイグレーションの導入。
* CIで失敗時に **先頭〜100行ログを artifact 化**（トリアージ短縮）。

---

## 作業書き出し

1. **CIの最終確認とタグ付け**

   * `master` のCIがグリーンで安定していることを再確認。
   * `v0.**` のタグを打ち、CHANGELOGに本日の修正点（決定論化SimHash / jsonb型キャスト / mention.span / CI配線）を追記。

2. **（任意）DBマイグレーション追加**

   * 追加ファイル：`db/migrations/2025-08-27_mention_span_default.sql`

     * `ALTER TABLE mention ALTER COLUMN span SET DEFAULT int4range(0,0);`
   * CIで `migrations/*.sql` を順次適用するステップが入っているかを確認（入っていなければ追記）。

3. **Ops／運用統合の仕上げ**

   * `linking.timer` / `events_ingest.timer` を **staging** に適用。
   * **DoD**：`entities_linked_total` / `events_with_participants_total` が増分、`journalctl` にエラーなし、`systemctl list-timers` で active。

4. **UIマニュアルとMCP-Firstの追記**

   * `docs/UI_MANUAL.md` に **curl チェック**（`/api/latest`, `/api/search`, `/api/search_sem`, `/api/events`, `/metrics`）を最終確定。
   * 既定404の説明＋`UI_ENABLED=1` の明示で有効化手順を強調。

5. **近重複の閾値外部化＆受入テスト拡充**

   * 閾値を `config/near_duplicate.yaml`（例）に切り出し。
   * 受入テストに **dup\_ratio 15–35%** の評価セットを追加。

6. **失敗時ログの自動収集**

   * `.github/workflows/ci.yml` に失敗時 `ci_fail.log` を **upload-artifact** する2行を追加。

---

## 今回に使うミニ指示

```bash
# 1) （任意）mention span の既定値マイグレーション
apply <<'SQL' :: db/migrations/2025-08-27_mention_span_default.sql
ALTER TABLE mention ALTER COLUMN span SET DEFAULT int4range(0,0);
SQL

# 2) CI artifact（failログ）追加（該当ジョブ末尾）
apply <<'YAML' :: .github/workflows/ci.yml
- run: pytest -x --maxfail=1 -q 2>&1 | tee ci_fail.log; test ${PIPESTATUS[0]} -eq 0
- uses: actions/upload-artifact@v4
  if: failure()
  with:
    name: ci-fail-log
    path: ci_fail.log
YAML

# 3) 受入テスト・近重複閾値の外部化（ファイル新設）
apply <<'YAML' :: config/near_duplicate.yaml
simhash_hamming_max: 12
jaccard_min: 0.35
YAML
```
上記 1→6 の順で回せば、運用段取り（staging→本番）まで滑らかに進められます。
