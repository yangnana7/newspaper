ナイス対応。ログ確認しました。CI赤の原因は**テスト1件のみ失敗**です。

### 症状（ログ要約）

`tests/test_language_detection.py::test_detect_lang_basic_cases`
`detect_lang("这是一个用于测试的中文句子。")` の期待値が `zh` に対し、実装は `zh-cn` を返して失敗。

```
E AssertionError: assert 'zh-cn' == 'zh'
- zh
+ zh-cn
1 failed, 20 passed, 5 skipped in 1.42s
```

※ なお、環境変数はログ上 `/tmp/linking.progress` が反映されており、runner.temp 撤廃はOK（`PROGRESS_FILE=/tmp/linking.progress` などが出力）。

---

## 方針

言語判定ライブラリが**地域付きの中国語コード（zh-CN/zh-TW/zh-Hans/zh-Hant …）を返すケース**に備えて、\*\*canonicalize（正規化）\*\*して `zh` に丸めます。将来の揺れ対策で、他の別名（`iw→he`, `in→id`, `pt-br→pt` など）も一緒に吸収しておくと堅くなります。

---

## パッチ（例）

`scripts/set_language.py` に正規化関数を追加し、`detect_lang` の返り値に適用してください。

```diff
--- a/scripts/set_language.py
+++ b/scripts/set_language.py
@@
+from typing import Optional
+
+_ALIASES = {
+    # 中国語は地域や表記体系に依らず 'zh' に統一
+    "zh-cn": "zh", "zh-sg": "zh", "zh-my": "zh",
+    "zh-tw": "zh", "zh-hk": "zh",
+    "zh-hans": "zh", "zh-hant": "zh",
+    # レガシーや地域別コードの正規化
+    "iw": "he",   # Hebrew old -> he
+    "in": "id",   # Indonesian old -> id
+    "ji": "yi",
+    "pt-br": "pt", "pt-pt": "pt",
+}
+
+def _canon_lang(code: Optional[str]) -> str:
+    if not code:
+        return "und"
+    c = code.lower().replace("_", "-")
+    # 'zh', 'zh-*' はすべて 'zh'
+    if c == "zh" or c.startswith("zh-"):
+        return "zh"
+    # 上記以外は alias を見て、なければベース言語に丸める
+    return _ALIASES.get(c, c.split("-")[0])
@@
-def detect_lang(text: str) -> str:
-    raw = _detector.detect(text)  # 例: 'zh-cn'
-    return raw
+def detect_lang(text: str) -> str:
+    raw = _detector.detect(text)  # 例: 'zh-cn'
+    return _canon_lang(raw)
```

> `_detector` は現行の検出器（langdetect / cld3 / lingua 等）を指す想定。関数名が異なる場合でも**返り値に `_canon_lang` を必ず通す**だけでOKです。

---

## 追加の軽テスト（任意）

回帰防止として、テストに以下のケースを1つ足すと安心です（既存方針は変えない）。

```python
# tests/test_language_detection.py
def test_detect_lang_zh_variants():
    from scripts.set_language import detect_lang
    for s in ["简体中文测试", "繁體中文測試"]:
        assert detect_lang(s) == "zh"
```

---

## 作業メモ

1. 上記の正規化を実装 → `pytest -q`
2. グリーン確認後、コミット＆プッシュ
   `git add scripts/set_language.py tests/test_language_detection.py`（追加した場合）
   `git commit -m "lang: canonicalize Chinese variants to 'zh' (fix CI)"`
   `git push`

この修正で当該失敗は解消されるはず。ほかにもCIで気になるところがあれば、次のログ束を投げてください。
