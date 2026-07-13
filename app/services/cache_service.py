import hashlib
import json
from app.redis_client import redis_client

CACHE_TTL_SECONDS = 60 * 60 * 24 * 7  # 7 days — long enough to help repeat
                                        # askers, short enough that stale
                                        # answers don't linger if a doc is
                                        # re-indexed.
CACHE_PREFIX = "chat_cache"


def _normalize(question: str) -> str:
    return " ".join(question.strip().lower().split())


def _cache_key(namespace: str, question: str) -> str:
    normalized = _normalize(question)
    digest = hashlib.sha256(normalized.encode()).hexdigest()
    return f"{CACHE_PREFIX}:{namespace}:{digest}"


def get_cached_answer(namespace: str, question: str) -> dict | None:
    """Returns {"answer": str, "sources": list} if this exact question has
    been asked before against this document, else None."""
    key = _cache_key(namespace, question)
    raw = redis_client.get(key)
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return None


def set_cached_answer(
    namespace: str,
    question: str,
    answer: str,
    sources: list,
    ttl: int = CACHE_TTL_SECONDS
) -> None:
    key = _cache_key(namespace, question)
    payload = json.dumps({"answer": answer, "sources": sources})
    redis_client.setex(key, ttl, payload)


def invalidate_namespace_cache(namespace: str) -> None:
    """Call this if a document gets re-indexed/re-uploaded so stale cached
    answers don't get served against changed content. Only clears cache
    entries for that one document's namespace, not the whole cache."""
    pattern = f"{CACHE_PREFIX}:{namespace}:*"
    for key in redis_client.scan_iter(match=pattern):
        redis_client.delete(key)