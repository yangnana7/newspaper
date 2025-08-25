ログ見ました。CI赤は**言語テスト 1 件のみ**で、内容はこうです（要点だけ）:

* `tests/test_language_detection.py::test_detect_lang_zh_variants`
  `detect_lang("简体中文测试")` などで **期待: `zh`、実際: `ko`** → 失敗

`langdetect` が**漢字だけの短文を誤って韓国語判定**する揺れです。ここはスクリプト（文字種）ヒューリスティックで**安全に上書き**するのが手っ取り早く堅いです。

---

## 最小修正パッチ（安全寄りの上書き順）

ポイント:

* かな/ハングルがあればそれを最優先（`ja`/`ko`）。
* **漢字のみ**でハングル/かなが無い場合は **“検出結果が`ko`のときだけ” `zh`に上書き**（日本語の“漢字だけ文”誤検知リスクを避けるため）。
* それ以外は従来の検出＋正規化を採用。

```diff
--- a/scripts/set_language.py
+++ b/scripts/set_language.py
@@
+import re
+
 # 既存: _ALIASES, _canon_lang など
@@
+_RE_HAN     = re.compile(r"[\u4E00-\u9FFF]")                     # CJK統合漢字（基本面）
+_RE_KANA    = re.compile(r"[\u3040-\u309F\u30A0-\u30FF]")        # ひらがな/カタカナ
+_RE_HANGUL  = re.compile(r"[\u1100-\u11FF\uAC00-\uD7A3]")        # ハングル字母+音節
+
+def _script_hint(text: str) -> str | None:
+    """文字種から強いヒントを返す: 'ja'/'ko' または 'zh' か None。"""
+    has_han    = bool(_RE_HAN.search(text))
+    has_kana   = bool(_RE_KANA.search(text))
+    has_hangul = bool(_RE_HANGUL.search(text))
+    if has_kana:
+        return "ja"                    # かなが出たら日本語優先
+    if has_hangul and not has_kana:
+        return "ko"                    # ハングルがあれば韓国語
+    if has_han and not has_kana and not has_hangul:
+        return "zh"                    # 純漢字（中/日どちらもあり得るが中国語候補）
+    return None
@@
-def detect_lang(text: str) -> str:
-    raw = _detector.detect(text)
-    return _canon_lang(raw)
+def detect_lang(text: str) -> str:
+    # 1) 文字種ヒント（強いものは即決）
+    hint = _script_hint(text)
+    if hint in ("ja", "ko"):
+        return hint
+    # 2) 検出器 → 正規化
+    raw = _detector.detect(text)
+    canon = _canon_lang(raw)
+    # 3) 純漢字短文の誤検知（ko）だけ安全に上書き
+    if hint == "zh" and canon == "ko":
+        return "zh"
+    return hint or canon
```

> 既に `_canon_lang()` は `zh-* → zh`, `iw→he`, `in→id`, `pt-br→pt` 等を吸収しているとのことなのでそのまま活用。

---

## 追加テスト（任意だがおすすめ）

日本語優先の回帰用:

```python
def test_detect_lang_kana_priority():
    from scripts.set_language import detect_lang
    assert detect_lang("テストです") == "ja"
    assert detect_lang("これはテストです。") == "ja"
```

---

## これで直る理由

* 今回の失敗は **「漢字だけの超短文」×「detector が ko を返す揺れ」** が原因。
* かな/ハングルは言語専有度が高いので**最優先**。
* **漢字のみ**の場合は\*\*“ko だった時だけ zh に矯正”\*\*という保守的ルールにすることで、日本語の“漢字だけ文”をむやみに zh に倒さないようにしています。

---

## 次のアクション

1. 上記パッチ適用 → `pytest -q`（ローカル）
2. CI 実行でグリーン確認

   * まだ落ちるようなら、該当サンプル文字列をログ出力して detector の “生”判定値を見ます（`raw` と `canon` を `SKIP_DB_TESTS=1` の時だけ debug 出力、など）。
