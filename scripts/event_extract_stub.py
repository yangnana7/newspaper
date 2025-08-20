#!/usr/bin/env python3
"""
Event Extraction stub.

方針:
- SRL/OIE で chunk.text_raw から S(主語)-P(述語)-O(目的語) を抽出
- event(type_id, t_start/t_end, loc_geohash) と evidence 紐付け

TODO:
- 軽量SRL/OIEモデル選定（日本語/英語）
- 場所・時間表現の正規化（HeidelTime 等）
"""
import os
import psycopg


def main():
    dsn = os.environ.get("DATABASE_URL", "postgresql://localhost/newshub")
    with psycopg.connect(dsn) as conn:
        print("[i] event_extract_stub: no-op")


if __name__ == "__main__":
    main()

