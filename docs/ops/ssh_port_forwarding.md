# SSH ポートフォワードでの公開手順（MCP-First準拠）

内部の Uvicorn/FastAPI は `127.0.0.1:3011` 固定のまま、SSH トンネルで外部から安全にアクセスします。UI は既定で無効です（MCP-First）。

## 前提
- サーバへ SSH 接続可能（ポート 22 開放）
- サーバ側で API が `127.0.0.1:3011` で稼働中（systemd か `uvicorn web.app:app --host 127.0.0.1 --port 3011`）

## 一時的なローカル転送（推奨・簡易）

Linux/macOS/Windows（PowerShell）共通:

```
ssh -N -L 3011:127.0.0.1:3011 <user>@<server-host>
```

- ローカルPCから `http://127.0.0.1:3011` へアクセス
- ローカルポートを変えたい場合: `-L 8080:127.0.0.1:3011` → `http://127.0.0.1:8080`
- バックグラウンド実行（Linux/macOS）: `ssh -f -N -L 3011:127.0.0.1:3011 <user>@<server-host>`

確認（ローカルPC）:

```
curl -sG "http://127.0.0.1:3011/search" --data-urlencode q="OpenAI" | jq .
curl -s "http://127.0.0.1:3011/search_sem?limit=5" | jq .
```

## SSH 設定で簡略化（~/.ssh/config）

`~/.ssh/config` に以下を追加:

```
Host newshub
  HostName <server-host>
  User <user>
  LocalForward 3011 127.0.0.1:3011
```

接続:

```
ssh -N newshub
```

## 自動再接続（任意: autossh）

```
autossh -M 0 -f -N -L 3011:127.0.0.1:3011 <user>@<server-host>
```

（systemd ユーザサービス化も可能。必要であればサンプル unit を提供します）

## UI の一時有効化（開発時のみ）

デフォルトでは `/` は 404。確認用途でのみサーバ側で UI を有効化:

```
export UI_ENABLED=1
uvicorn web.app:app --host 127.0.0.1 --port 3011
```

本番や恒久運用では UI を無効のままにし、API のみを利用してください。

