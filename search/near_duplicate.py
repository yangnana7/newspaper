from __future__ import annotations

import re
from typing import Iterable, List, Tuple, Dict, Set
import hashlib


_RE_ALNUM = re.compile(r"[A-Za-z0-9]+", re.UNICODE)


def _shingles(text: str, k: int = 3) -> List[str]:
    t = (text or "").strip()
    if not t:
        return []
    # Basic Latin tokens
    toks = _RE_ALNUM.findall(t.lower())
    out: List[str] = []
    if toks:
        for tok in toks:
            if len(tok) <= k:
                out.append(tok)
            else:
                out.extend(tok[i : i + k] for i in range(0, len(tok) - k + 1))
    else:
        # CJK or no-space languages: character shingles
        s = re.sub(r"\s+", "", t)
        out = [s[i : i + k] for i in range(0, max(0, len(s) - k + 1))]
    return list(dict.fromkeys(out))  # dedupe preserving order


def _token_set(text: str) -> Set[str]:
    return set(_RE_ALNUM.findall((text or "").lower()))


def simhash64(text: str) -> int:
    """Compute a deterministic 64-bit SimHash from text shingles.
    Uses SHA-256-derived 64-bit integers per shingle to avoid Python's
    randomized hash() behavior across processes.
    """
    feats = _shingles(text, 3)
    if not feats:
        return 0
    v = [0] * 64
    for f in feats:
        # Deterministic 64-bit feature hash from SHA-256 (first 8 bytes)
        h = int.from_bytes(hashlib.sha256(f.encode("utf-8")).digest()[:8], "big")
        for i in range(64):
            bit = 1 if (h >> i) & 1 else -1
            v[i] += bit
    out = 0
    for i in range(64):
        if v[i] >= 0:
            out |= (1 << i)
    return out


def hamming(a: int, b: int) -> int:
    return int(bin((a ^ b) & ((1 << 64) - 1)).count("1"))


def cluster_by_simhash(
    items: Iterable[Tuple[int, str]],
    threshold: int = 3,
    jaccard_threshold: float = 0.4,
) -> Dict[int, List[int]]:
    """Greedy clustering by SimHash Hamming distance.
    items: iterable of (id, title)
    returns: {cluster_id: [doc_ids...]}
    """
    data: List[Tuple[int, str]] = list(items)
    hashes: List[Tuple[int, int]] = [(doc_id, simhash64(title)) for doc_id, title in data]
    clusters: Dict[int, List[int]] = {}
    used: set[int] = set()
    toksets: Dict[int, Set[str]] = {doc_id: _token_set(title) for doc_id, title in data}
    for i, (doc_i, h_i) in enumerate(hashes):
        if doc_i in used:
            continue
        cid = h_i  # use simhash as cluster id
        clusters[cid] = [doc_i]
        used.add(doc_i)
        for j in range(i + 1, len(hashes)):
            doc_j, h_j = hashes[j]
            if doc_j in used:
                continue
            if hamming(h_i, h_j) <= threshold:
                clusters[cid].append(doc_j)
                used.add(doc_j)
            else:
                # Fallback with token Jaccard similarity
                a, b = toksets.get(doc_i, set()), toksets.get(doc_j, set())
                if a and b:
                    inter = len(a & b)
                    union = len(a | b) or 1
                    jacc = inter / union
                    if jacc >= jaccard_threshold:
                        clusters[cid].append(doc_j)
                        used.add(doc_j)
    return clusters
