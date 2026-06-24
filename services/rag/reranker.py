import os

import requests


def _tokenize(text):
    return {token for token in str(text or "").replace("\n", " ").split() if token}


def lexical_rerank(query, documents):
    query_tokens = _tokenize(query)
    scored = []
    for index, doc in enumerate(documents):
        doc_tokens = _tokenize(doc.get("content") or "")
        overlap = len(query_tokens & doc_tokens)
        base = float(doc.get("hybridScore") or doc.get("score") or 0)
        rerank_score = base + min(overlap / max(len(query_tokens), 1), 1.0) * 0.2
        scored.append((index, rerank_score))
    return scored


def external_rerank(query, documents, *, top_n=None):
    api_key = os.getenv("RERANK_API_KEY") or os.getenv("DASHSCOPE_API_KEY")
    base_url = (os.getenv("RERANK_BASE_URL") or "").rstrip("/")
    model = os.getenv("RERANK_MODEL", "gte-rerank-v2")
    if not api_key or not base_url:
        return None

    payload = {
        "model": model,
        "query": query,
        "documents": [doc.get("content") or "" for doc in documents],
        "top_n": top_n or len(documents),
    }
    response = requests.post(
        f"{base_url}/rerank",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json=payload,
        timeout=int(os.getenv("RERANK_TIMEOUT", "30")),
    )
    if response.status_code != 200:
        raise RuntimeError(f"rerank_failed status={response.status_code}")
    data = response.json()
    results = data.get("results") or data.get("output", {}).get("results") or []
    scored = []
    for item in results:
        index = item.get("index")
        score = item.get("relevance_score", item.get("score"))
        if index is not None and score is not None:
            scored.append((int(index), float(score)))
    return scored or None


def rerank(query, documents, *, top_n=None):
    if not documents:
        return []
    model = "lexical"
    try:
        scored = external_rerank(query, documents, top_n=top_n)
        if scored:
            model = os.getenv("RERANK_MODEL", "external")
        else:
            scored = lexical_rerank(query, documents)
    except Exception:
        scored = lexical_rerank(query, documents)

    by_index = {index: score for index, score in scored}
    ranked = []
    for index, doc in enumerate(documents):
        score = by_index.get(index, float(doc.get("hybridScore") or 0))
        ranked.append({**doc, "rerankScore": score, "rerankModel": model})
    return sorted(ranked, key=lambda item: item.get("rerankScore") or 0, reverse=True)[: top_n or len(ranked)]
