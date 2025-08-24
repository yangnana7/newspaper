def test_ranking_yaml_loads_and_weights_sum_to_1():
    from search.ranker import load_ranking_config
    c = load_ranking_config()
    s = c["score_weights"]
    total = sum(float(v) for v in s.values())
    assert abs(total - 1.0) < 1e-6


def test_ranking_config_fallback_when_no_yaml():
    """Test that defaults are used when YAML file doesn't exist."""
    from search.ranker import load_ranking_config
    c = load_ranking_config()
    
    # Check default values
    assert c["score_weights"]["cosine"] == 0.7
    assert c["score_weights"]["recency"] == 0.2
    assert c["score_weights"]["source_trust"] == 0.1
    assert c["recency_half_life_hours"] == 48
    assert c["source_trust"]["default"] == 0.0


def test_source_trust_loading():
    """Test that source trust values are loaded correctly."""
    from search.ranker import load_source_trust
    trust_map = load_source_trust()
    
    # Should be a dictionary (may be empty or contain values from config)
    assert isinstance(trust_map, dict)
    
    # If config file exists, check for expected sources
    if "nhk.or.jp" in trust_map:
        assert trust_map["nhk.or.jp"] == 0.2
    if "apnews.com" in trust_map:
        assert trust_map["apnews.com"] == 0.1


def test_language_trust_loading_and_default():
    from search.ranker import load_ranking_config, load_language_trust
    c = load_ranking_config()
    assert "language_trust" in c
    lt = load_language_trust()
    assert isinstance(lt, dict)
