Prometheus Multiprocess Integration — Design (MCP News)

Date: 2025-08-27
Scope: Aggregate metrics across Web API (FastAPI) and CLI workers (ingest/link/embed) using Prometheus client multiprocess mode.

Goals
- Aggregate counters/histograms from multiple OS processes (web + CLI scripts) into a single `/metrics` endpoint.
- Preserve MCP-First invariants (APP_BIND_HOST=127.0.0.1, PORT=3011) and keep UI disabled by default.
- Keep changes minimal and reversible; maintain current tests without requiring Prometheus in CI.

Constraints
- DB and bind fixed by policy: `DATABASE_URL=.../newshub`, `127.0.0.1:3011`.
- Current metrics are defined in `mcp_news/metrics.py` and exposed at `web/app.py:/metrics`.
- CLI tools (e.g., `scripts/ingest_events.py`) run in separate processes; today their metric increments do not appear at Web `/metrics`.

Approach Overview
1) Use Prometheus client multiprocess mode via `PROMETHEUS_MULTIPROC_DIR`.
2) Web `/metrics` endpoint will instantiate a `CollectorRegistry` and attach `multiprocess.MultiProcessCollector` to aggregate per-process metric shards stored as files in the multiproc directory.
3) All processes that emit metrics (web + CLI) must run with the same `PROMETHEUS_MULTIPROC_DIR` set and writable.
4) Ensure directory lifecycle: clear shards on service restart and restrict permissions to the service user.

Directory & Permissions
- Path: `/run/mcp-news/prometheus` (tmpfs, cleared on reboot; avoids stale shards across reboots).
- Ownership: `newsp:newsp` (service user), mode `0750`.
- Provision via tmpfiles:
  - `/etc/tmpfiles.d/mcp-news.conf`
    - `d /run/mcp-news/prometheus 0750 newsp newsp -`

Environment & systemd
- Append to `/etc/default/mcp-news` (EnvironmentFile):
  - `PROMETHEUS_MULTIPROC_DIR=/run/mcp-news/prometheus`
- Add ExecStartPre to API service to ensure directory exists and is clean:
```
[Service]
EnvironmentFile=/etc/default/mcp-news
ExecStartPre=/usr/bin/mkdir -p ${PROMETHEUS_MULTIPROC_DIR}
ExecStartPre=/usr/bin/chown newsp:newsp ${PROMETHEUS_MULTIPROC_DIR}
ExecStartPre=/usr/bin/find ${PROMETHEUS_MULTIPROC_DIR} -type f -delete
```
- Ensure CLI timers/services also inherit `EnvironmentFile=/etc/default/mcp-news` so they write to the same directory.

Code Changes (proposed)
1) `mcp_news/metrics.py` — detect multiprocess and aggregate on demand:
```
try:
    from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST
    from prometheus_client import CollectorRegistry
    from prometheus_client import multiprocess
    PROMETHEUS_AVAILABLE = True
except ImportError:
    ...

def get_metrics_content() -> str:
    if not PROMETHEUS_AVAILABLE:
        return "# Prometheus client not available\n"
    # Multiprocess mode when PROMETHEUS_MULTIPROC_DIR is set
    if os.environ.get("PROMETHEUS_MULTIPROC_DIR"):
        registry = CollectorRegistry()
        try:
            multiprocess.MultiProcessCollector(registry)
        except Exception:
            pass  # fall back to default registry below
        else:
            return generate_latest(registry).decode('utf-8')
    # Single-process fallback
    return generate_latest().decode('utf-8')
```

2) Optional cleanup on process exit for short-lived CLI tasks:
```
import atexit, os
from prometheus_client import multiprocess
_pid = os.getpid()
atexit.register(lambda: multiprocess.mark_process_dead(_pid))
```
Place in CLI entry points that increment metrics (not strictly required if ExecStartPre cleans shards, but recommended to reduce shard buildup).

3) `web/app.py` — no direct change needed if it calls `get_metrics_content()` (it does). The updated function will aggregate when env var is present.

Operational Notes
- Test locally without multiprocess: do nothing; behavior unchanged.
- Enable aggregation by exporting `PROMETHEUS_MULTIPROC_DIR` for both web and CLI processes.
- Staleness: orphaned shards can appear if a process dies without cleanup; ExecStartPre (and tmpfs at reboot) mitigates this.
- Security: The directory must not be world-writable. Keep permissions to the service user only.

Rollout Plan
1) Create tmpfiles entry and reload: `systemd-tmpfiles --create`.
2) Update `/etc/default/mcp-news` with `PROMETHEUS_MULTIPROC_DIR=/run/mcp-news/prometheus`.
3) Patch `mcp_news/metrics.py` as described; restart web service.
4) Ensure CLI services/timers inherit the env file (entity linking, event ingest, embeddings).
5) Verify:
   - Run a CLI job that increments a counter (e.g., events with participants), then curl `/metrics` and confirm the counter increases.

Rollback
- Unset `PROMETHEUS_MULTIPROC_DIR` and restart services; `get_metrics_content()` will use single-process mode again.
- No DB schema changes; safe to revert.

Example Verification Sequence
```
export PROMETHEUS_MULTIPROC_DIR=/run/mcp-news/prometheus
curl -s http://127.0.0.1:3011/metrics | grep events_with_participants_total
.venv/bin/python -m scripts.ingest_events --limit 5  # increments in a separate process
curl -s http://127.0.0.1:3011/metrics | grep events_with_participants_total
```
Expect the value to increase after the CLI run when multiprocess is enabled for both processes.

Open Questions
- Do we want to add `PROMETHEUS_MULTIPROC_DIR` to `deploy/mcp-news.env.sample` and sample systemd units in `docs/ops/systemd-timers-sample.md`?
- Do we need per-environment override (staging/prod) for the directory path?

