# MCPニュース／CI安定化 — 次ステップ指示書 & 完了確認チェックシード（CodexCLI用）

作成: 2025-08-26 JST
対象リポジトリ: `yangnana7/newspaper`（master）

---

## 0. 要旨（昨日の議事録サマリ）

* CI は最終的に **緑化**。主因は次の3点を解消したため：

  1. **SimHash の非決定性**（`hash()` 由来）→ **SHA-256 → 64bit化**で決定論化。
  2. **CI の DB/ENV 不整合** → `pgvector/pgvector:pg16` を使用、`EMBEDDING_SPACE/EMBED_SPACE` 両対応、`UI_ENABLED=0` 明示、`rg`→`grep -E` に統一。
  3. **DB 制約周り** → `doc.source` を明示、`jsonb_build_object('name', %s::text)` に統一、`mention.span` を **`int4range(0,0)`** で安全挿入。

* 代表的な変更：

  * `search/near_duplicate.py`（SimHash 決定論化）
  * `.github/workflows/ci.yml`（pgvector + ENV 明示 + スキーマ適用）
  * `mcp_news/config_guard.py` / `mcp_news/server.py`（固定ガード / MCP-First 準拠）
  * `scripts/ingest_entities.py` / `tests/test_entity_upsert.py`（型・NOT NULL 整合）

---

## 1. 今日やること（次ステップ）

**A. 安全策マイグレーション（任意だが推奨）**

* `mention.span` に **DEFAULT `int4range(0,0)`** を付与（既定値で NOT NULL を常に満たす）

**B. CI 失敗時のトリアージ短縮**

* GitHub Actions の末尾に **失敗ログの artifact 化** を追加（`ci_fail.log` を upload）

**C. 近重複の閾値外部化**

* `config/near_duplicate.yaml` を新設し、**SimHash/Jaccard 閾値**を外出し → テストで参照

**D. Ops（staging）**

* `linking.timer` / `events_ingest.timer` を適用し、`entities_linked_total` / `events_with_participants_total` が増分することを確認

**E. ドキュメント**

* `docs/UI_MANUAL.md` に **curl チェック**（`/api/latest`, `/api/search`, `/api/search_sem`, `/api/events`, `/metrics`）を追記

---

## 2. CodexCLI へそのまま渡せる「実装パッチ指示」

### 2.1 マイグレーション追加（推奨）

```patch
*** Begin Patch
*** Add File: db/migrations/2025-08-27_mention_span_default.sql
+-- Set a safe default for mention.span so inserts without explicit span
+-- still satisfy NOT NULL via PRIMARY KEY (chunk_id, ent_id, span).
+-- An empty range int4range(0,0) is non-null and deterministic.
+ALTER TABLE mention
+  ALTER COLUMN span SET DEFAULT int4range(0,0);
+
*** End Patch
```

### 2.2 CI 失敗ログの artifact 追加（`ci.yml` 末尾に2行）

> pytest の終了コードを保持しつつログを tee 保存 → 失敗時に upload。

```patch
*** Begin Patch
*** Update File: .github/workflows/ci.yml
@@
-      - run: pytest -q
+      - run: pytest -x --maxfail=1 -q 2>&1 | tee ci_fail.log; test ${PIPESTATUS[0]} -eq 0
+      - uses: actions/upload-artifact@v4
+        if: failure()
+        with:
+          name: ci-fail-log
+          path: ci_fail.log
*** End Patch
```

### 2.3 近重複の閾値を外部化（新設ファイル）

```patch
*** Begin Patch
*** Add File: config/near_duplicate.yaml
+simhash_hamming_max: 12
+jaccard_min: 0.35
*** End Patch
```

> **メモ**: 実装側では `config/near_duplicate.yaml` を読み取り、既存の SimHash/Jaccard 閾値を上記設定で上書きできるようにしてください。

---

## 3. CodexCLI 実行テンプレ（プロンプト例）

> 失敗ログをそのまま貼り戻す運用を想定。差分が大きい場合はファイル単位で繰り返す。

```
# 目的: 0826議事録に基づく次の3点の反映
# 1) mention.span DEFAULT のマイグレーションを追加
# 2) ci_fail.log の artifact 化を .github/workflows/ci.yml に追加
# 3) config/near_duplicate.yaml を新設（SimHash/Jaccard 閾値の外部化）

# 手順
1. 上記「2. CodexCLI へそのまま渡せる実装パッチ指示」を apply。
2. pytest を実行。失敗したらログ全体を貼り戻し、修正差分を生成。
3. すべて緑になったら `git tag v0.**` を付与し、CHANGELOG を更新。

# 期待アウトカム
- master CI 緑
- migrations 適用で mention.span の DEFAULT が設定済み
- 近重複閾値は config から読み込まれる
```

---

## 4. 完了確認チェックシード（DoD）

* [ ] **CI 緑化**（`master` 最新コミットが緑）
* [ ] **pytest**（ローカル）: `SKIP_DB_TESTS=1 pytest -q` が pass（`s`/`.` のみ、`F` なし）
* [ ] **DB マイグレーション**（任意だが推奨）: `\d mention` で `span` の DEFAULT に `int4range(0,0)` が入っている
* [ ] **CI artifact**: ワザと1件落とした場合に `ci-fail-log` が GitHub Actions の Artifacts に現れる
* [ ] **近重複設定**: 実行時ログに `near_duplicate.yaml` のロード痕跡（`simhash_hamming_max/jaccard_min`）が出る
* [ ] **staging Ops**: `systemctl list-timers` で `linking.timer`/`events_ingest.timer` が active、メトリクスが増分
* [ ] **ドキュメント**: `docs/UI_MANUAL.md` に curl サンプルが追記済み

---

## 5. 補足（MCP-First 方針の再確認）

* 既定は **UI 無効**（ルート `/` は 404）。`UI_ENABLED=1` のみ開発用。
* DB 名は **`newshub` 固定**、アプリのバインドも **`127.0.0.1:3011` 固定**。
* ベクトルは **`vector(768)` / 距離は cos（`<=>`）** を採用。
