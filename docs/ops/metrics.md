# メトリクス監視 運用メモ

## Prometheusメトリクスエンドポイント

### アクセス方法
```bash
curl http://127.0.0.1:3011/metrics
```

### 利用可能メトリクス

#### Counter（累積カウンタ）
- `items_ingested_total` - 取り込み済みアイテム数
- `embeddings_built_total` - 作成済み埋め込み数

#### Histogram（処理時間分布）
- `ingest_duration_seconds` - データ取り込み処理時間
- `embed_duration_seconds` - 埋め込み作成処理時間

## Grafanaダッシュボード取り込み

### Prometheus設定例
```yaml
# prometheus.yml
scrape_configs:
  - job_name: 'newshub-api'
    static_configs:
      - targets: ['127.0.0.1:3011']
    metrics_path: '/metrics'
    scrape_interval: 30s
```

### 推奨クエリ

#### 取り込み速度（毎分）
```promql
rate(items_ingested_total[1m]) * 60
```

#### 埋め込み処理速度（毎分）
```promql
rate(embeddings_built_total[1m]) * 60
```

#### 平均処理時間
```promql
rate(ingest_duration_seconds_sum[5m]) / rate(ingest_duration_seconds_count[5m])
```

#### 処理時間パーセンタイル
```promql
histogram_quantile(0.95, rate(ingest_duration_seconds_bucket[5m]))
```

## アラート推奨設定

### 取り込み停止検知
```yaml
- alert: IngestionStopped
  expr: increase(items_ingested_total[10m]) == 0
  for: 10m
  labels:
    severity: warning
  annotations:
    summary: "データ取り込みが10分間停止しています"
```

### 埋め込み処理遅延
```yaml
- alert: EmbeddingProcessingSlow
  expr: histogram_quantile(0.95, rate(embed_duration_seconds_bucket[5m])) > 30
  for: 5m
  labels:
    severity: warning
  annotations:
    summary: "埋め込み処理が遅延しています（95%ile > 30s）"
```

## 運用上の注意

1. **メトリクスは永続化されません** - サーバー再起動で累積値はリセット
2. **高頻度スクレイピング注意** - 30秒間隔を推奨
3. **メトリクス無効化** - `prometheus-client`未インストール時は自動無効化

## トラブルシューティング

### メトリクスが取得できない場合
```bash
# 1. サーバー起動確認
curl http://127.0.0.1:3011/api/latest

# 2. prometheus-client確認
python -c "import prometheus_client; print('OK')"

# 3. 依存関係インストール
pip install prometheus-client>=0.17.0
```

### メトリクス値が更新されない場合
- 取り込み処理スクリプトでのメトリクス呼び出し確認
- `web.app.record_ingest_item()` / `web.app.record_embedding_built()` の実行

## 実装者向けメモ

### メトリクス記録方法

#### 取り込み処理での使用例
```python
from web.app import record_ingest_item, time_ingest_operation

@time_ingest_operation
def process_feed_item(item):
    # 処理実装
    record_ingest_item()  # 処理完了時に呼び出し
```

#### 埋め込み処理での使用例  
```python
from web.app import record_embedding_built, time_embed_operation

@time_embed_operation
def create_embedding(text):
    # 埋め込み作成処理
    record_embedding_built()  # 完了時に呼び出し
```

## 更新履歴

- 2025-08-24: 初版作成（HNSW+ランク融合+メトリクススプリント）