CIが失敗している原因は、PRで追加された `.github/workflows/ci.yml` の環境変数設定にあります。具体的には、以下の行で **`runner.temp`** コンテキストを参照しています。

* `.github/workflows/ci.yml` で `env` セクションに次を追加した箇所

  ```yaml
  PROGRESS_FILE: ${{ runner.temp }}/linking.progress
  LINK_PROGRESS_FILE: ${{ runner.temp }}/linking.progress
  ```

GitHub Actions の `env` ブロックでは `runner.*` コンテキストが利用できないため、ワークフロー自体が無効と判定され、Actions UI に「Unrecognized named‑value: 'runner'」というエラーが表示されています。

### 修正案

* `runner.temp` への参照を廃止し、どの環境でも存在するディレクトリに固定する。例えば `/tmp` などです。
* そのため、以下のように修正してください（`env` セクションだけ抜粋）:

```yaml
env:
  PYTHONUNBUFFERED: "1"
  PIP_DISABLE_PIP_VERSION_CHECK: "1"
  APP_BIND_HOST: 127.0.0.1
  APP_BIND_PORT: '3011'
  DATABASE_URL: postgresql://127.0.0.1/newshub
  CI: "true"
  SKIP_DB_TESTS: "1"
  # tmp にリンク進捗ファイルを書き出す
  PROGRESS_FILE: /tmp/linking.progress
  LINK_PROGRESS_FILE: /tmp/linking.progress
```

この修正により、無効なワークフローエラーは解消されます。`/tmp` 以外のディレクトリを使いたい場合は、例えば `${{ github.workspace }}/linking.progress` のように `github.workspace` コンテキスト（現在のリポジトリチェックアウトディレクトリ）を使うこともできます。`PROGRESS_FILE` と `LINK_PROGRESS_FILE` を参照するコード側では、存在しない場合のフォールバック処理も実装しておくと、環境を問わず動作しやすくなります。

ワークフローを更新して push し直し、Actions のジョブが通るか確認してみてください。次のステップとしてテストが失敗するようなら、そのログに基づいて実装側を修正していきます。
