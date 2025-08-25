# Systemd units for MCP News

## Layout
- Working directory: `/opt/mcp-news`
- Virtualenv: `/opt/mcp-news/.venv`

## Units
- `ingest.service` + `ingest.timer`: RSS ingest job
- `embed.service` + `embed.timer`: build embeddings periodically
- `mcp-news.service`: MCP server (stdio/long-running)
- Optional: `hn-top.service|timer`, `newsapi-tech-jp.service|timer`
- `linking.service|timer`: Wikidata 連携（ext_id の付与、進捗ファイルは `/etc/default/mcp-news` の `LINK_PROGRESS_FILE` を参照）
- `events_ingest.service|timer`: chunk からイベント抽出・格納（参加者・根拠も登録）

## Install
```bash
sudo mkdir -p /opt/mcp-news
sudo chown -R "$USER" /opt/mcp-news
# Sync your repository into /opt/mcp-news (e.g., git clone or rsync)

# venv
python3 -m venv /opt/mcp-news/.venv
/opt/mcp-news/.venv/bin/pip install -U pip
/opt/mcp-news/.venv/bin/pip install -r /opt/mcp-news/requirements.txt

# Copy units
sudo cp deploy/*.service deploy/*.timer /etc/systemd/system/

# Enable timers & services
sudo systemctl daemon-reload
sudo systemctl enable --now ingest.timer embed.timer linking.timer events_ingest.timer
sudo systemctl enable --now mcp-news.service

# Verify
systemctl list-timers | grep -E 'ingest|embed'
journalctl -u ingest.service -n 50 --no-pager
systemctl list-timers | grep -E 'linking|events_ingest'
journalctl -u linking.service -n 50 --no-pager
journalctl -u events_ingest.service -n 50 --no-pager
```

Adjust environment via `/etc/default/mcp-news` or service `Environment=` lines as needed.
