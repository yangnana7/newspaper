## ✅ レビュー

* CI ワークフローが `.github/workflows/ci.yml` に追加されており、Postgres（pgvector入り）をコンテナとして起動し、スキーマ適用や静的チェック、pytest 実行まで含まれています。この構成でリポジトリに CI が走るようになっています。
* `db/schema_v2.sql` の冒頭に `CREATE EXTENSION IF NOT EXISTS vector;` が追加され、pgvector 拡張が自動で有効化されるようになっています。補助インデックス (`idx_hint_genre`, `idx_entity_ext`) も残されています。
* 新しいテスト (`tests/test_smoke.py`、`tests/test_urlcanon.py`) が追加されています。`test_smoke` はテーブル存在確認と `doc_head`／`semantic_search` の疎通確認、`test_urlcanon` は URL からトラッカーを除去する処理の回帰確認を行っています。
* NewsAPI と HN の取り込みスクリプトでは、URL 正規化関数が RSS と同じように拡張され、`utm_*` だけでなく `gclid`/`fbclid` を確実に除外しています。

### 改善点・軽微な指摘

* CI の依存パッケージは `requirements.txt` からインストールするため、別途 `psycopg` や `pgvector` を指定しなくても動作しますが、明示的に `pip install psycopg[binary] pgvector` を入れておくと requirements に漏れが出ても CI が壊れにくくなります。
* スキーマに `idx_doc_url`（`doc.url_canon`）や `idx_hint_key`（`hint.key`）などの汎用インデックスがまだありません。クエリ最適化の観点では追加を検討しても良いでしょう。

## ▶️ CodexCLI に依頼する次のタスク

次のステップとして、以下の作業を CodexCLI で進めると良いでしょう。

1. **CI 実行結果の確認と修正**

   * GitHub Actions が走ったらログを確認し、テストが失敗した場合は原因を特定・修正してください。特に依存関係周りで不足があれば `ci.yml` に追記します。

2. **スキーマのインデックス拡充**

   * `db/schema_v2.sql` に以下のインデックスを追加するパッチを作成してください。

     ```sql
     CREATE INDEX IF NOT EXISTS idx_doc_url ON doc (url_canon);
     CREATE INDEX IF NOT EXISTS idx_hint_key ON hint (key);
     ```
   * 追加後はスキーマ適用スクリプトや README にその旨を追記すると親切です。

3. **`doc.author` カラムの追加（オプション）**

   * 将来的に著者情報を活用する計画がある場合、`doc` テーブルに `author` TEXT カラムを追加し、NewsAPI や HN 取り込み時に保存するよう拡張してください。既存コードへの影響が小さいため、このタイミングで入れておくと後で楽です。

4. **エンティティ抽出スタブの実装着手**

   * 今は `scripts/entity_link_stub.py` や `scripts/event_extract_stub.py` が空のはずです。まずは `entity_link_stub.py` に、テキストから単語を抽出して `entity`／`mention` テーブルに仮レコードを入れるダミー実装を書き、単体テストも追加してみてください。

5. **ドキュメントの整備**

   * README や `docs/FINAL_REPORT.md` に、CI の導入方法やテストの説明、今後のロードマップを追記しておくとプロジェクトに参加する人の理解が深まります。

これらの作業は、コード編集とテスト実行が中心ですので CodexCLI に適しています。CI を通しながら段階的に進めていきましょう。
