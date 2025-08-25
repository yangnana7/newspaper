def test_detect_lang_basic_cases():
    from scripts.set_language import detect_lang

    assert detect_lang("これは日本語の文章です。AIがテストします。") == "ja"
    assert detect_lang("This is an English sentence for testing.") == "en"
    # Russian (Cyrillic)
    assert detect_lang("Это тестовое предложение на русском языке.") == "ru"
    # Chinese (CJK unified ideographs)
    assert detect_lang("这是一个用于测试的中文句子。") == "zh"

