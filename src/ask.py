"""
Project 2: Designs Law Assistant - Interactive CLI Query Interface

Provides an interactive CLI loop (like grounded_tutor.py) to ask questions about
Indian Industrial Designs Law, formats answers with metadata citations, and
logs every interaction to a JSONL audit file.

Usage:
    python src/ask.py
"""

import json
import os
import sys
from rag_chain import DesignsLawRAG

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOG_PATH = os.path.join(BASE_DIR, "outputs", "interaction_log.jsonl")


def log_interaction(question: str, result: dict, path: str = LOG_PATH) -> None:
    """Logs question and response record to a JSONL file (repo style)."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    record = {"question": question, **result}
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def format_source_display(citations: list) -> str:
    """Formats citations list into the required display format."""
    if not citations:
        return ""
    lines = []
    for c in citations:
        page = c.get("page", "?")
        chapter = c.get("chapter", "Unknown")
        section = c.get("section", "Unknown")
        lines.append(f"Source: Page {page} | Chapter: {chapter} | Section: {section}")
    return "\n".join(lines)


def main():
    print("=" * 65)
    print("Designs Law Assistant (Manual of Practice & Procedure)")
    print("Ask any question regarding Industrial Designs Law in India.")
    print("Type 'quit' or 'exit' to stop.")
    print("=" * 65 + "\n")

    try:
        rag = DesignsLawRAG()
    except Exception as e:
        print(f"Error initializing RAG Assistant: {e}")
        print("Please verify that your .env file is set and 'python src/ingest.py' has been run.")
        sys.exit(1)

    while True:
        try:
            question = input("\nQ: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nExiting.")
            break

        if question.lower() in {"quit", "exit"}:
            print("Goodbye.")
            break
        if not question:
            continue

        result = rag.query(question)
        log_interaction(question, result)

        answer = result.get("answer", "Not found")
        citations = result.get("citations", [])

        print(f"A: {answer}")
        if citations and answer != "Not found":
            print(format_source_display(citations))


if __name__ == "__main__":
    main()
