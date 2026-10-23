"""
Project 2: Designs Law Assistant - Evaluation Runner

Runs the 5 project benchmark questions plus 3 out-of-document negative test
questions through the RAG chain. Evaluates Pass/Fail criteria:
- In-document questions must return found=True with valid citations.
- Out-of-document questions must return found=False and exactly "Not found".

Saves structured evaluation results to outputs/results.json.

Usage:
    python src/evaluate.py
"""

import json
import logging
import os
import sys
import time
from rag_chain import DesignsLawRAG, SCORE_THRESHOLD

EVALUATION_SET = [
    {
        "id": 1,
        "question": "How long does a proprietor have copyright in a registered design, and can it be extended?",
        "expected_type": "in_doc",
        "expected_found": True,
    },
    {
        "id": 2,
        "question": "Which classification system is used to register designs?",
        "expected_type": "in_doc",
        "expected_found": True,
    },
    {
        "id": 3,
        "question": "What is the government fee to register a trademark?",
        "expected_type": "out_of_doc",
        "expected_found": False,
    },
    {
        "id": 4,
        "question": "Who is the current Controller General of Patents?",
        "expected_type": "out_of_doc",
        "expected_found": False,
    },
    {
        "id": 5,
        "question": "What is the fee to register a design?",
        "expected_type": "in_doc",
        "expected_found": True,
    },
    {
        "id": 6,
        "question": "What are the patentability criteria for an artificial intelligence invention under the Indian Patents Act?",
        "expected_type": "out_of_doc",
        "expected_found": False,
    },
    {
        "id": 7,
        "question": "What is the penalty for copyright infringement under Section 63 of the Indian Copyright Act 1957?",
        "expected_type": "out_of_doc",
        "expected_found": False,
    },
    {
        "id": 8,
        "question": "What is the average annual rainfall and monsoon weather in New Delhi?",
        "expected_type": "out_of_doc",
        "expected_found": False,
    },
]


def run_evaluation():
    print("=" * 80)
    print("PROJECT 2: DESIGNS LAW ASSISTANT - BENCHMARK EVALUATION")
    print(f"Active SCORE_THRESHOLD: {SCORE_THRESHOLD}")
    print("=" * 80 + "\n")

    try:
        rag = DesignsLawRAG()
    except Exception as e:
        print(f"Error initializing RAG Assistant: {e}")
        sys.exit(1)

    results = []
    all_passed = True

    for item in EVALUATION_SET:
        qid = item["id"]
        q = item["question"]
        q_type = item["expected_type"]
        expected_found = item["expected_found"]

        print(f"Running Q{qid} ({q_type.upper()}): {q}")
        res = rag.query(q)

        actual_ans = res.get("answer", "Not found")
        actual_found = res.get("found", False)
        citations = res.get("citations", [])
        gate = res.get("gate_triggered", "")
        best_score = res.get("best_score", 0.0)

        # Verification rule
        if expected_found:
            passed = (actual_found is True) and (len(citations) > 0) and (actual_ans != "Not found")
        else:
            passed = (actual_found is False) and (actual_ans == "Not found")

        if not passed:
            all_passed = False

        status_str = "PASS" if passed else "FAIL"
        print(f"  Status: {status_str} | Found: {actual_found} | Score: {best_score:.4f} | Gate: {gate}")
        print(f"  Answer: {actual_ans}")
        if citations:
            for c in citations:
                print(f"  Citation: Page {c.get('page')} | Chapter: {c.get('chapter')} | Section: {c.get('section')}")
        print("-" * 80 + "\n")

        results.append({
            "id": qid,
            "question": q,
            "type": q_type,
            "expected_found": expected_found,
            "actual_found": actual_found,
            "answer": actual_ans,
            "passed": passed,
            "gate_triggered": gate,
            "best_score": best_score,
            "citations": citations,
        })

        # Rate-limiting pause between queries
        time.sleep(12)

    # Output directory
    output_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "outputs")
    os.makedirs(output_dir, exist_ok=True)

    json_path = os.path.join(output_dir, "results.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "score_threshold": SCORE_THRESHOLD,
                "all_passed": all_passed,
                "total_questions": len(results),
                "passed_count": sum(1 for r in results if r["passed"]),
                "results": results,
            },
            f,
            indent=2,
            ensure_ascii=False,
        )

    print("\n" + "=" * 80)
    print("FINAL EVALUATION SUMMARY TABLE")
    print("=" * 80)
    print(f"{'#':<3} | {'Type':<10} | {'Status':<6} | {'Gate / Citations':<35} | Question")
    print("-" * 80)
    for r in results:
        gate_or_cite = (
            f"Page {r['citations'][0]['page']}" if r["citations"] else r["gate_triggered"]
        )
        print(f"{r['id']:<3} | {r['type']:<10} | {('PASS' if r['passed'] else 'FAIL'):<6} | {gate_or_cite[:35]:<35} | {r['question'][:45]}...")
    print("=" * 80)
    print(f"Overall Result: {'ALL TESTS PASSED (8/8)' if all_passed else 'SOME TESTS FAILED'}")
    print(f"Saved results to: {json_path}\n")


if __name__ == "__main__":
    run_evaluation()
