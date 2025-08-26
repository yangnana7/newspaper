# systemd timers: sample units (staging/prod)

These are sample service/timer units for periodic entity linking and event ingestion.
Adjust `User=` and `WorkingDirectory=` to your environment. Keep MCP-First invariants: bind to `127.0.0.1:3011`, DB=`newshub`.

## Files

Place under `/etc/systemd/system/`.

### `/etc/systemd/system/newshub-linking.service`
```
[Unit]
Description=Newshub — Link entities to Wikidata
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=newsp
WorkingDirectory=/opt/mcp-news
EnvironmentFile=/etc/default/mcp-news
ExecStart=/opt/mcp-news/.venv/bin/python -m scripts.link_entities_wikidata
Nice=10
IOSchedulingClass=best-effort
IOSchedulingPriority=7
Restart=on-failure
```

### `/etc/systemd/system/newshub-linking.timer`
```
[Unit]
Description=Run entity linking periodically

[Timer]
OnBootSec=2min
OnUnitActiveSec=15min
AccuracySec=1min
Persistent=true

[Install]
WantedBy=timers.target
```

### `/etc/systemd/system/newshub-events.service`
```
[Unit]
Description=Newshub — Ingest events from mentions
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=newsp
WorkingDirectory=/opt/mcp-news
EnvironmentFile=/etc/default/mcp-news
ExecStart=/opt/mcp-news/.venv/bin/python -m scripts.ingest_events
Nice=10
IOSchedulingClass=best-effort
IOSchedulingPriority=7
Restart=on-failure
```

### `/etc/systemd/system/newshub-events.timer`
```
[Unit]
Description=Run events ingestion periodically

[Timer]
OnBootSec=3min
OnUnitActiveSec=30min
AccuracySec=1min
Persistent=true

[Install]
WantedBy=timers.target
```

## Enable
```
sudo systemctl daemon-reload
sudo systemctl enable --now newshub-linking.timer newshub-events.timer
systemctl list-timers | grep newshub
```

## Verify metrics
After a cycle, counters should increment:
```
curl -s http://127.0.0.1:3011/metrics | grep -E 'entities_linked_total|events_with_participants_total'
```

