#!/usr/bin/env python3
"""
Entity Linking stub.

方針:
- chunk.text_raw から固有表現抽出 → 候補生成（Wikidata, GeoNames 等）
- 候補スコアリング → ext_id（例: 'Q95'）へ正規化、mention に確信度付きで保存

TODO:
- 軽量NLPの選定（例: spaCy + ja_core_news_md / Stanza / SudachiPy+NE）
- 候補検索: Wikidata API / 事前ダンプ + Elastic/Meilisearch
- キャッシュ・レート制御
"""
import os
import psycopg


def main():
    dsn = os.environ.get("DATABASE_URL", "postgresql://localhost/newshub")
    with psycopg.connect(dsn) as conn:
        # ここで chunk を走査し、仮の実装としてスキップ
        print("[i] entity_link_stub: no-op")


if __name__ == "__main__":
    main()

