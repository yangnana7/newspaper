プロジェクトの目的と設計図を理解し、現状のコードとのズレを確認します。その上で、進捗状況の可視化、残作業の指示、修正箇所のアドバイス、スケジュール提示、UIのマニュアル作成を進めます。まずコードを確認して詳細をまとめます。

現在のリポジトリを確認したところ、CI はグリーンですがローカルの `pytest` では `ModuleNotFoundError: No module named 'pgvector'` が原因で一件だけ失敗していました。このテストは、`mcp_news.server` と `web.app` のインポート順序とメトリクスエンドポイントの動作を確認するものです。プロジェクトの趣旨・設計と実装状況の整合性、進捗状況、残作業や修正点について以下にまとめます。

## ① プロジェクト趣旨と設計図と現状コードの整合性（GPT内部の確認）

* **概要**：
  新聞/ニュース記事を取得・保存し、検索・ランキング・イベントタイムラインを提供するためのシステムです。データベースは Postgres + pgvector を利用し、ドキュメントは `doc` テーブルに保存、テキストを `chunk` テーブルへ分割し、そのベクトル表現を `chunk_vec` に保存します。エンティティやイベントはそれぞれ専用のテーブルで管理し、メトリクス収集には Prometheus を利用します。
* **検索**：
  検索 API と MCP ツールには、全文検索・ベクトル検索・エンティティ検索が用意されています。ベクトル検索はコサイン距離を用い、ランク付けは Recency や Source Trust 等の重みを YAML で設定可能です。
* **UI**：
  `web/app.py` は FastAPI を使った最小 UI を提供し、`/api/latest`・`/api/search`・`/api/search_sem` 等のエンドポイントを公開しています。HTML テンプレート `index.html` には検索ボックスと「最新を表示」ボタンがあり、取得した記事をカード形式で表示するシンプルな UI です。
* **メトリクス**：
  `mcp_news.metrics` で Prometheus 用カウンター／ヒストグラム／ゲージが定義され、サーバと Web アプリの双方から利用できるように共通化されています。

**設計とのズレ**：

* **pgvector の必須インポート**： `web/app.py` で `from pgvector.psycopg import Vector, register_vector` を必ず実行しており、CI やローカル環境で `pgvector` がインストールされていない場合に `ModuleNotFoundError` を起こします。`fastapi` や `psycopg` と同様に、無い場合はインポートをスキップし graceful degradation するべきです。
* **UI 有効化の条件**：トップページ (`/`) では `UI_ENABLED=1` かどうかで表示を切り替えており、README には「`mkdir -p web/static` を実行して uvicorn を起動する」と書かれているものの、環境変数 UI\_ENABLED の説明が README に記載されていません。設計ドキュメントに追記すると良いでしょう。
* **entity\_link\_stub の統合**：エンティティリンクのスタブは実装されていますが、Web/API レイヤではまだ利用していません。実運用ではインジェスト時に実行し、`entity`・`mention` テーブルを埋めて検索で利用できるようにする必要があります（今は後述の残作業に含めます）。

## ③ まだ残っている作業（今日中）

CodexCLI で取り組むべき具体的なタスクは次のとおりです。

1. **pgvector のオプションインポート化**
   `web/app.py` の先頭で `from pgvector.psycopg import Vector, register_vector` を直接インポートしているため、`pgvector` が無い環境でテストが落ちています。`fastapi` や `psycopg` と同じように `try/except` で包んで、ロードできない場合は `Vector=None; register_vector=None` としてエラーを起こさないように修正します。

2. **README に UI 有効化方法を追記**
   環境変数 `UI_ENABLED=1` を設定することでトップページが有効になることを README の Webアプリセクションに記載します。

3. **エンティティリンクの統合計画**
   `scripts/entity_link_stub.py` を定期的に実行し、`mention` と `entity` テーブルを更新する処理の追加。これは今後の作業計画に含めます。

4. **追加テストの修正**
   `pytest` を再実行して、`pgvector` インポート修正後にテストが通ることを確認します。CI でグリーンになるように `requirements.txt` の整合も確認してください。

## ④ 修正すべき箇所と指示（CodexCLI向け）

以下のパッチ例のように `web/app.py` を修正してください。

```python
# web/app.py の先頭付近
try:
    from pgvector.psycopg import Vector, register_vector  # type: ignore
except Exception:  # pragma: no cover
    # pgvector が無い環境ではベクトル検索を無効化
    Vector = None  # type: ignore
    def register_vector(conn):
        return None
```

* これにより `ModuleNotFoundError` が解消され、`Vector`/`register_vector` が無い環境ではベクトル検索エンドポイント (`/api/search_sem`) がフォールバックして最新記事一覧を返します。
* 同様に `requirements.txt` に `pgvector` をオプション依存としてコメント付きで追加すると運用時に明示できます。

README の Web アプリ説明に以下を追加してください。

```
- UI を有効にするには環境変数 `UI_ENABLED=1` を指定して起動してください。無効時には `/` エンドポイントが 404 になります。
```

## ⑥ 現在利用できる UI の簡易マニュアル（人間用）

1. **起動方法**
   README に記載のとおり、依存パッケージをインストールしたうえで `uvicorn web.app:app` を起動します。トップページを表示するには環境変数 `UI_ENABLED=1` をセットし、静的ディレクトリを用意します。

   ```sh
   mkdir -p web/static
   UI_ENABLED=1 uvicorn web.app:app --host 127.0.0.1 --port 3011
   ```
2. **画面概要**
   ブラウザで `http://127.0.0.1:3011/` にアクセスすると「MCP News – Minimal UI」が表示されます。画面上部に検索ボックスと「検索」「最新を表示」ボタンがあり、記事一覧を表示する領域がカード形式で配置されます。
3. **利用方法**

   * **最新記事の取得**：起動時や「最新を表示」クリック時に `/api/latest?limit=50` を呼び出し、最新の 50 件を表示します。
   * **キーワード検索**：検索ボックスに文字列を入力し「検索」を押すと `/api/search` にクエリが送られ、タイトルにそのキーワードを含む記事が表示されます。
   * **セマンティック検索**（オプション）：`/api/search_sem` では JSON 配列形式のベクトルをパラメータに渡すことでベクトル検索を行い、結果は再ランキングされます。ユーザ向け UI では現状ボタンやフォームがないため API 直接呼び出しになります。
   * **結果表示**：タイトルリンクをクリックすると元記事へ遷移し、行右側には公開日時・ソース・ジャンルが表示されます。

これらを参考に、コード修正とドキュメント更新を進めてください。
