# Systemd units for MCP News

## Layout
- Working directory: `/opt/mcp-news`
- Virtualenv: `/opt/mcp-news/.venv`

## Units
- `ingest.service` + `ingest.timer`: RSS ingest job
- `embed.service` + `embed.timer`: build embeddings periodically
- `mcp-news.service`: MCP server (stdio/long-running)
- Optional: `hn-top.service|timer`, `newsapi-tech-jp.service|timer`

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
sudo systemctl enable --now ingest.timer embed.timer
sudo systemctl enable --now mcp-news.service

# Verify
systemctl list-timers | grep -E 'ingest|embed'
journalctl -u ingest.service -n 50 --no-pager
```

Adjust environment via `/etc/default/mcp-news` or service `Environment=` lines as needed.
