def test_simhash_clusters_similar_titles():
    from search.near_duplicate import cluster_by_simhash

    items = [
        (1, "Breaking: Apple releases new iPhone"),
        (2, "Apple unveils new iPhone today"),
        (3, "Local weather shows heavy rain"),
        (4, "Weather update: heavy rain expected"),
        (5, "Completely different unrelated topic"),
    ]
    # Use a moderately lenient threshold to account for simplistic SimHash
    clusters = cluster_by_simhash(items, threshold=16)
    # Ensure at least one cluster has multiple items
    multi = [v for v in clusters.values() if len(v) > 1]
    assert len(multi) >= 1
    # A doc appears in exactly one cluster
    flat = [d for v in clusters.values() for d in v]
    assert sorted(flat) == sorted([i for i, _ in items])
