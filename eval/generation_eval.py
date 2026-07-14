"""
Generation eval — uses a local Ollama model as judge (faithfulness,
relevance, fact coverage). Judge calls are cached by (question, context,
answer) so re-running against unchanged retrieval/generation doesn't
re-score everything.

Requires Ollama running locally with a pulled model, e.g.:
    ollama pull phi3:mini
    ollama serve

Usage:
    python eval/generation_eval.py --document-id 15
    python eval/generation_eval.py --document-id 15 --no-cache
"""
import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from app.services.rag_service import get_pinecone_index, hybrid_retrieve, rerank
from app.services.llm_service import answer_question
from eval.retrieval_eval import get_namespace_for_document, load_golden_set

GOLDEN_SET_PATH = os.path.join(os.path.dirname(__file__), "golden_set.json")
REPORTS_DIR = os.path.join(os.path.dirname(__file__), "reports")
CACHE_DIR = os.path.join(os.path.dirname(__file__), "cache")
JUDGE_MODEL = "phi3:mini"  # chosen for 8GB RAM machines; swap to a bigger
                            # model if running eval on something with more.

JUDGE_PROMPT = """You are a strict evaluator. You will be given a QUESTION, the CONTEXT that was retrieved to answer it, the ANSWER that was generated, and a list of FACTS that a good answer should contain.

Respond with ONLY a JSON object (no other text, no markdown fences) in this exact shape:
{{
  "faithfulness": <0.0 to 1.0, how much of the answer is actually supported by the context, 1.0 = fully grounded, 0.0 = fully hallucinated>,
  "relevance": <0.0 to 1.0, does the answer actually address the question>,
  "facts_covered": <integer, how many of the listed FACTS are present in the answer, in substance not exact wording>,
  "reasoning": "<one short sentence>"
}}

QUESTION: {question}

CONTEXT:
{context}

ANSWER:
{answer}

FACTS a good answer should contain:
{facts}

JSON:"""


def _cache_key(question: str, context: str, answer: str) -> str:
    payload = json.dumps({"q": question, "ctx": context, "a": answer}, sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()


def _get_cached_judgment(key: str) -> dict | None:
    path = os.path.join(CACHE_DIR, f"{key}.json")
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return None


def _save_cached_judgment(key: str, result: dict) -> None:
    os.makedirs(CACHE_DIR, exist_ok=True)
    with open(os.path.join(CACHE_DIR, f"{key}.json"), "w") as f:
        json.dump(result, f)


def _get_judge_llm():
    # Imported lazily so retrieval-only runs don't require langchain_community
    # or a running Ollama server at all.
    from langchain_community.chat_models import ChatOllama
    return ChatOllama(model=JUDGE_MODEL, temperature=0)


def judge_answer(question: str, context: str, answer: str, facts: list[str], judge_llm) -> dict:
    prompt = JUDGE_PROMPT.format(
        question=question,
        context=context[:4000],  # keep judge input bounded on an 8GB machine
        answer=answer,
        facts="\n".join(f"- {f}" for f in facts)
    )
    raw = judge_llm.invoke(prompt).content.strip()

    # Local small models sometimes wrap JSON in markdown fences despite
    # instructions — strip those before parsing rather than failing the run.
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.lower().startswith("json"):
            raw = raw[4:]
        raw = raw.strip()

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        # Judge gave unparseable output — record as a failed judgment rather
        # than crashing the whole eval run or silently scoring it as 0.
        return {
            "faithfulness": None,
            "relevance": None,
            "facts_covered": None,
            "reasoning": f"JUDGE_PARSE_FAILURE: {raw[:200]}"
        }
    return parsed


def run_generation_eval(document_id: int, use_cache: bool = True) -> dict:
    namespace = get_namespace_for_document(document_id)
    index = get_pinecone_index()
    golden_set = load_golden_set()
    judge_llm = _get_judge_llm()

    per_question_results = []
    cache_hits = 0

    for item in golden_set:
        question = item["question"]
        facts = item["expected_answer_facts"]

        candidates = hybrid_retrieve(question, [], index, namespace)
        top_docs = rerank(question, candidates)
        context = "\n\n---\n\n".join(d.page_content for d in top_docs)

        answer = answer_question(question, top_docs, history=[])

        key = _cache_key(question, context, answer)
        judgment = _get_cached_judgment(key) if use_cache else None
        if judgment is not None:
            cache_hits += 1
        else:
            judgment = judge_answer(question, context, answer, facts, judge_llm)
            if use_cache:
                _save_cached_judgment(key, judgment)

        per_question_results.append({
            "id": item["id"],
            "question": question,
            "answer": answer,
            "num_facts_expected": len(facts),
            **judgment
        })

    valid = [r for r in per_question_results if r["faithfulness"] is not None]
    parse_failures = len(per_question_results) - len(valid)
    n = len(valid) or 1

    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "document_id": document_id,
        "namespace": namespace,
        "judge_model": JUDGE_MODEL,
        "num_questions": len(per_question_results),
        "judge_parse_failures": parse_failures,
        "cache_hits": cache_hits,
        "mean_faithfulness": round(sum(r["faithfulness"] for r in valid) / n, 4),
        "mean_relevance": round(sum(r["relevance"] for r in valid) / n, 4),
        "mean_fact_coverage_ratio": round(
            sum(r["facts_covered"] / r["num_facts_expected"] for r in valid if r["num_facts_expected"]) / n, 4
        ),
        "per_question": per_question_results,
    }
    return report


def save_report(report: dict) -> str:
    os.makedirs(REPORTS_DIR, exist_ok=True)
    filename = f"generation_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}.json"
    path = os.path.join(REPORTS_DIR, filename)
    with open(path, "w") as f:
        json.dump(report, f, indent=2)
    latest_path = os.path.join(REPORTS_DIR, "generation_latest.json")
    with open(latest_path, "w") as f:
        json.dump(report, f, indent=2)
    return path


def main():
    parser = argparse.ArgumentParser(description="Run generation eval against a golden set using a local Ollama judge.")
    parser.add_argument("--document-id", type=int, required=True, help="ID of the indexed golden document")
    parser.add_argument("--no-cache", action="store_true", help="Bypass judge cache and re-score everything")
    args = parser.parse_args()

    report = run_generation_eval(args.document_id, use_cache=not args.no_cache)
    path = save_report(report)

    print(f"\nGeneration eval — document_id={args.document_id}, judge={report['judge_model']}")
    print(f"  Questions evaluated:   {report['num_questions']}")
    print(f"  Cache hits:            {report['cache_hits']}")
    print(f"  Judge parse failures:  {report['judge_parse_failures']}")
    print(f"  Mean faithfulness:     {report['mean_faithfulness']:.2%}")
    print(f"  Mean relevance:        {report['mean_relevance']:.2%}")
    print(f"  Mean fact coverage:    {report['mean_fact_coverage_ratio']:.2%}")
    print(f"  Report saved to:       {path}\n")


if __name__ == "__main__":
    main()