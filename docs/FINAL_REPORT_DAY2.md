**完了確認（0821レビューpart2.md）**                                                   
- ベクトル検索整合                                                                     
  - `mcp_news/server.py`: 距離演算を `<=>`（cos）に統一、`ENABLE_SERVER_EMBEDDIN       
G` の判定を厳密化、`pgvector.psycopg.Vector` で型適合、例外時に `rollback()` し        
てフォールバック確実化。                                                               
  - `db/schema_v2.sql`: `idx_chunk_vec_hnsw_bge_m3_cos` を追加、`emb vector(768)       
` に固定（HNSW要件）。                                                                 
- イベント抽出スタブ                                                                   
  - `scripts/event_extract_stub.py`: 未処理chunkごとにダミーevent＋evidence追加        
。                                                                                     
  - `tests/test_event_stub.py`: 生成確認テストを追加（pass）。                         
- CI強化                                                                               
  - `.github/workflows/ci.yml`: 依存の保険インストール（`psycopg[binary] pgvecto       
r`）、`PYTHONPATH=.` 指定、収集対象を `tests/` のみに限定。                            
  - `tests/*`: JSONBは `Json({...})` で適合（psycopg3）。                              
- 互換・安定化                                                                         
  - `mcp_news/server.py`: `typing_extensions.TypedDict` を優先使用（Py3.11でのPy       
danticスキーマ化対策）。                                                               
                                                                                       
**更新ファイル（主）**                                                                 
- スキーマ: `db/schema_v2.sql`                                                         
- サーバ: `mcp_news/server.py`                                                         
- スタブ: `scripts/event_extract_stub.py`, `scripts/entity_link_stub.py`               
- テスト: `tests/test_smoke.py`, `tests/test_urlcanon.py`, `tests/test_entity_st       
ub.py`, `tests/test_event_stub.py`                                                     
- CI: `.github/workflows/ci.yml`                                                       
- ドキュメント: `docs/0821レビューpart2.md`, `README.md`, `docs/FINAL_REPORT_DAY       
1.md`                                                                                  
                                                                                       
**ドキュメント追記（主なポイント）**                                                   
- 0821レビューpart2.md: cos距離統一、イベントスタブ、CI強化、TypedDict互換、Vect       
or型適合・rollbackの記載を追加。                                                       
- README.md: tests/のみ収集、`vector(768)` 注記、Py3.11のTypedDict互換注記を追加       
。                                                                                     
- FINAL_REPORT_DAY1.md: 付記としてcos距離統一、スキーマ順序修正、CI強化を追記。        
                                                                                       
**現状の動作**                                                                         
- CI: 6 passed（スキーマ適用→コンパイル→pytest）。フォールバック検索含めて疎通OK       
。                                                                                     
- サーバ: ENABLE_SERVER_EMBEDDING=0 では常に新着順フォールバック、=1 ではcos検索       
が有効（右辺Vectorで型一致）。                                                         

問題なし。0821レビューpart2.mdの実施は完了です。次の着手候補があれば指示ください       
（例: ランク融合のパラメータ化、近重複検知、NewsAPIテンプレ整備など）。

### 総合レビュー
マージ後の `master` ブランチを確認したところ、0821レビューpart2.md に沿った修正が反映されていました。主なポイントは以下の通りです。

### コアコードの更新

* **semantic\_search の距離演算子を `<=>`（cosine 類似）に変更**し、`pgvector.psycopg.Vector` でクエリ埋め込みを明示的に包んでいます。これにより正規化済みベクトルとの整合が取れ、検索品質の再現性が向上します。
* `ENABLE_SERVER_EMBEDDING` の値判定が `"1" / "true" / "yes" / "on"` に限定され、曖昧な設定を排除したのも良い修正です。
* Python 3.11 環境で `TypedDict` が FastMCP に認識されない問題への対処として、`typing_extensions` からのインポートを優先している点も確認できました。
* ベクトル検索部で例外が発生した際に `conn.rollback()` を呼び出し、新着順フォールバックが確実に動作するようにしています。

### スキーマとインデックス

* `db/schema_v2.sql` では `chunk_vec.emb` の型が `vector(768)` に固定され、HNSW インデックスに cos 用オペレータクラスを追加しています。
* `doc.url_canon` の明示的なインデックス `idx_doc_url` と、`hint.key` に対する `idx_hint_key` が追加され、検索性能が向上しています。
* 既存DBへの後方互換のため、`ALTER TABLE doc ADD COLUMN IF NOT EXISTS author TEXT;` が最後に置かれており、新旧環境どちらでも動作します。

### 新しいスタブとテスト

* `scripts/event_extract_stub.py` は未処理のチャンクに対してダミーイベント (`type_id='stub:event'`) と `evidence` を生成する最小実装になっており、`tests/test_event_stub.py` でイベントと証拠の挿入が検証されています。
* `scripts/entity_link_stub.py` では英語の大文字単語をトークンとして抽出し、`entity`／`mention` テーブルへ挿入するスタブ実装を確認しました。こちらも新規テスト `tests/test_entity_stub.py` で動作を確認しています。

### CI の強化

* CI ワークフローでは、requirements.txt とは別に `psycopg[binary]` と `pgvector` を明示的にインストールし、テスト実行時の Python パスを `PYTHONPATH=.` に設定しているため、依存漏れや import エラーが起こりにくくなっています。
* `pytest -q tests` で `docs/ci_pack` 下の重複テスト収集を避けるようになっており、ファイル名衝突による誤動作を防いでいます。

### 総評と今後の課題

全体として、Day2 の目的だった「ベクトル検索の一貫性確保」「イベント抽出スタブ実装」「CIの堅牢化」が master ブランチに反映されており、テストもグリーンになっていると思われます。今後は以下の点を検討すると良いでしょう。

1. **古い L2 インデックスの整理**

   * `idx_chunk_vec_hnsw_bge_m3`（L2）と新しい cos 用インデックスの併存は構築時間と容量を増やすので、運用に支障がなければ片方に統一する。
2. **スタブの高度化**

   * Entity・Event のスタブは英語トークンのみ対象なので、日本語や多言語に対応した実装（SudachiPy, spaCyなど）の検討をすすめる。
3. **ランク融合のパラメータ化**

   * cosine 類似と recency や source trust などを組み合わせるスコアリング関数を実装し、環境変数や設定ファイルで係数を調整できるようにする。
4. **近重複検知の組み込み**

   * 今後のバージョンで MinHash/SimHash を使った重複記事クラスタリングを導入すると、検索結果の品質がさらに向上します。

現在の master ブランチは、この時点でサーバーにデプロイして動作確認をする準備が整っています。次は実データを取り込んでエンティティ・イベントのスタブがどの程度機能するかを評価し、ステップアップしていくと良いでしょう。
