# Grafana ダッシュボード運用メモ

## インポート手順
1. Grafanaの左メニューから Dashboards > Import を選択
2. `grafana/dashboard.json` をアップロード
3. Prometheusデータソースを選択（newshub-api など）
4. 保存

## 含まれるパネル
- Items Ingested / min（`rate(items_ingested_total[1m]) * 60`）
- Embeddings Built / min（`rate(embeddings_built_total[1m]) * 60`）
- Ingest avg latency（平均）
- Embed p95 latency（95パーセンタイル）

## 推奨設定
- スクレイプ間隔: 30s（Prometheus側）
- ダッシュボードの自動更新: 30s

