"""
Retrieval eval — deterministic, no LLM calls.

Runs the golden set questions through the REAL retrieval pipeline
(hybrid_retrieve + rerank from app.services.rag_service) against a real,
already-indexed document, and checks whether the expected page(s) show up
in the retrieved results.

Usage:
    python eval/retrieval_eval.py --document-id 15
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone

# Allow `python eval/retrieval_eval.py` to import the app package as if run
# from the project root.
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from app.database import SessionLocal
from app.models.document import Document
from app.services.rag_service import get_pinecone_index, hybrid_retrieve, rerank

GOLDEN_SET_PATH = os.path.join(os.path.dirname(__file__), "golden_set.json")
REPORTS_DIR = os.path.join(os.path.dirname(__file__), "reports")


def load_golden_set() -> list[dict]:
    with open(GOLDEN_SET_PATH) as f:
        return json.load(f)


def get_namespace_for_document(document_id: int) -> str:
    db = SessionLocal()
    try:
        doc = db.query(Document).filter(Document.id == document_id).first()
        if doc is None:
            raise ValueError(f"No document with id={document_id}")
        if doc.status != "indexed":
            raise ValueError(
                f"Document id={document_id} has status='{doc.status}', "
                f"expected 'indexed'. Wait for Celery indexing to finish."
            )
        if not doc.pinecone_namespace:
            raise ValueError(f"Document id={document_id} has no pinecone_namespace set.")
        return doc.pinecone_namespace
    finally:
        db.close()


def recall_at_k(retrieved_pages: list[int], expected_pages: list[int]) -> int:
    """1 if any expected page appears anywhere in what was retrieved, else 0."""
    return int(any(p in retrieved_pages for p in expected_pages))


def reciprocal_rank(retrieved_pages: list[int], expected_pages: list[int]) -> float:
    """1/rank of the first correctly-retrieved page; 0 if none found."""
    for i, page in enumerate(retrieved_pages):
        if page in expected_pages:
            return 1.0 / (i + 1)
    return 0.0


def run_retrieval_eval(document_id: int, use_rerank: bool = True) -> dict:
    namespace = get_namespace_for_document(document_id)
    index = get_pinecone_index()
    golden_set = load_golden_set()

    per_question_results = []

    for item in golden_set:
        question = item["question"]
        expected_pages = item["expected_pages"]

        # chunks=[] mirrors production (routers/chat.py currently passes []
        # too, so BM25 doesn't actually run there — see note in run_eval.py)
        candidates = hybrid_retrieve(question, [], index, namespace)
        final_docs = rerank(question, candidates) if use_rerank else candidates

        retrieved_pages = [d.metadata.get("page") for d in final_docs]

        per_question_results.append({
            "id": item["id"],
            "question": question,
            "expected_pages": expected_pages,
            "retrieved_pages": retrieved_pages,
            "recall": recall_at_k(retrieved_pages, expected_pages),
            "reciprocal_rank": reciprocal_rank(retrieved_pages, expected_pages),
        })

    n = len(per_question_results)
    mean_recall = sum(r["recall"] for r in per_question_results) / n
    mean_rr = sum(r["reciprocal_rank"] for r in per_question_results) / n

    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "document_id": document_id,
        "namespace": namespace,
        "reranked": use_rerank,
        "num_questions": n,
        "recall_at_k": round(mean_recall, 4),
        "mrr": round(mean_rr, 4),
        "top_k_used": len(per_question_results[0]["retrieved_pages"]) if per_question_results else 0,
        "per_question": per_question_results,
    }
    return report


def save_report(report: dict) -> str:
    os.makedirs(REPORTS_DIR, exist_ok=True)
    filename = f"retrieval_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')}.json"
    path = os.path.join(REPORTS_DIR, filename)
    with open(path, "w") as f:
        json.dump(report, f, indent=2)
    # Also write/overwrite a "latest" pointer for CI to read easily.
    latest_path = os.path.join(REPORTS_DIR, "retrieval_latest.json")
    with open(latest_path, "w") as f:
        json.dump(report, f, indent=2)
    return path


def main():
    parser = argparse.ArgumentParser(description="Run retrieval eval against a golden set.")
    parser.add_argument("--document-id", type=int, required=True, help="ID of the indexed golden document")
    parser.add_argument("--no-rerank", action="store_true", help="Skip reranking, evaluate raw hybrid_retrieve output")
    args = parser.parse_args()

    report = run_retrieval_eval(args.document_id, use_rerank=not args.no_rerank)
    path = save_report(report)

    print(f"\nRetrieval eval — document_id={args.document_id}")
    print(f"  Questions evaluated: {report['num_questions']}")
    print(f"  Recall@k:            {report['recall_at_k']:.2%}")
    print(f"  MRR:                 {report['mrr']:.4f}")
    print(f"  Report saved to:     {path}\n")

    misses = [r for r in report["per_question"] if r["recall"] == 0]
    if misses:
        print(f"  {len(misses)} question(s) missed expected page entirely:")
        for m in misses:
            print(f"    [{m['id']}] expected {m['expected_pages']}, got {m['retrieved_pages']}")


if __name__ == "__main__":
    main()