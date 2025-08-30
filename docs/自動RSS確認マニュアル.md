いいね、**“今ほんとに自動で回ってる？”を30秒で判定**できるチェックだけ置きます。外部検索は使いません。

## 即判定ワンライナー（貼るだけ）

```bash
# 1) RSSタイマーの有無と次回実行時刻（名前差異に両対応）
systemctl list-timers --all | egrep 'rss_ingest|ingest\.timer'

# 2) 直近70分の実行ログ（成功/失敗/件数っぽいログを拾う）
for s in rss_ingest.service ingest.service; do
  echo "== $s =="; journalctl -u $s --since "-70 min" --no-pager \
    | egrep "Started |Finished|\[✓\]|Fetch|ingest" || true
done

# 3) 直近90分でdocが増えているか（JSTで時系列）
psql "$DATABASE_URL" -F $'\t' -Atc "
SELECT to_char(date_trunc('minute', first_seen_at AT TIME ZONE 'Asia/Tokyo'),'YYYY-MM-DD HH24:MI'),
       count(*)
FROM doc
WHERE first_seen_at > now() - interval '90 minutes'
GROUP BY 1 ORDER BY 1;"
```

* **OK判定**：
* タイマーが **ENABLED かつ NEXT が今後にあり**、
* サービスログに **Started/Finished** や **\[✓] ingest** 等が**10〜30分おき**に並び、
* その時間帯で **doc件数が増加**（同一分に複数カウントでもOK）。
  これで「自動巡回が回っている」確定です。
* **NG判定**：タイマーが見つからない／DISABLED／ログが空／docが全く増えない。

> 補足：あなたのレポートでは\*\*ingest.timer（10分ごと）\*\*が前提、API/Embedは正常稼働です（`uvicorn` LISTEN、`EMBED_SPACE=e5-multilingual` で埋め込み完了）。この構成なら上のチェックで可否が分かります。 &#x20;

---

## NGのときだけ（復旧ワンライナー）

```bash
sudo systemctl daemon-reload
# RSSタイマー名が rss_ingest.timer ならこちら、ingest.timer なら読み替え
sudo systemctl enable --now rss_ingest.timer || sudo systemctl enable --now ingest.timer
# その場で1回流してログ確認
sudo systemctl start rss_ingest.service 2>/dev/null || sudo systemctl start ingest.service
journalctl -u rss_ingest.service -n 50 --no-pager 2>/dev/null || journalctl -u ingest.service -n 50 --no-pager
```

> 設計上、**タイマーは自分で enable しない限り回りません**（標準は10分間隔）。`feeds.json` が空／重複URLだと件数は増えません。

必要なら、このチェックを `/usr/local/bin/newshub-auto-rss-check.sh` にまとめて渡します。
