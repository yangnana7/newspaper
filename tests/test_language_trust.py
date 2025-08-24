def test_language_weights_and_normalization():
    from search.ranker import load_ranking_config
    cfg = load_ranking_config()
    w = cfg["score_weights"]
    assert "language" in w
    total = sum(float(v) for v in w.values())
    assert abs(total - 1.0) < 1e-6

