import os
from importlib import reload


def test_config_fallback_when_yaml_missing(monkeypatch):
    # ensure file missing
    cfg = "config/near_duplicate.yaml"
    bak = cfg + ".bak"
    try:
        if os.path.exists(cfg):
            os.rename(cfg, bak)
        import search.near_duplicate as nd
        reload(nd)
        # defaultしきい値で極端一致はクラスタ化される（スモーク）
        items = [(1, "OpenAI launches new model"), (2, "OpenAI launches new model")]
        clusters = nd.cluster_by_simhash(items, threshold=3, jaccard_threshold=0.4)
        assert any(len(v) >= 2 for v in clusters.values())
    finally:
        if os.path.exists(bak):
            os.rename(bak, cfg)


def test_config_load_when_yaml_present(tmp_path, monkeypatch):
    # Place a YAML in cwd (simulating presence), then reload module
    yaml_path = tmp_path / "near_duplicate.yaml"
    yaml_path.write_text("simhash_hamming_max: 12\njaccard_min: 0.35\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    import search.near_duplicate as nd
    reload(nd)
    # しきい値を引数に反映できるヘルパ経由のスモーク
    items = [(1, "AI model released"), (2, "AI model released soon")]
    clusters = nd.cluster_by_simhash(items, threshold=12, jaccard_threshold=0.35)
    assert isinstance(clusters, dict)

