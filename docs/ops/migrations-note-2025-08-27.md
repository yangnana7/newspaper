# Migrations note

- `db/migrations/2025-08-26_mention_span_default.sql` と
- `db/migrations/2025-08-27_mention_span_default.sql` は同一内容で安全（idempotent）。
- 本番適用完了後に一方へ統合（後発ファイルをGit管理から除去）しても可。履歴の整合性に留意。

