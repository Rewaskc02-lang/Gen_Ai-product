"""
Project 2: Designs Law Assistant - RAG Chain Definition

Defines the LangChain LCEL RAG chain connecting Chroma vector retrieval,
two-layer "Not found" gating (Retrieval score gate + Prompt grounding gate),
and structured JSON output parsing with metadata-backed citations.
"""

import json
import logging
import os
import re
import time
from typing import Any, Dict, List, Tuple
import chromadb
from dotenv import load_dotenv
from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings

# Telemetry silencing
os.environ["ANONYMIZED_TELEMETRY"] = "False"

load_dotenv()

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_DIR = os.path.join(BASE_DIR, "chroma_db")
COLLECTION_NAME = "designs_manual"

# Layer A Retrieval Gate: If best score < SCORE_THRESHOLD, return "Not found" without calling LLM
SCORE_THRESHOLD = 0.50

SYSTEM_PROMPT = """You are Grounded Designs Law Assistant, a specialized legal tutor for Indian industrial designs law based strictly and solely on the provided Manual of Designs Practice & Procedure.

Follow these strict rules:
1. ROLE & GROUNDING: Answer strictly and only from the provided Context. Never use outside knowledge or extrapolate beyond the text. Even for famous public facts or legal generalities, if it is not in the context, do NOT answer it.
2. UNCERTAINTY & NOT FOUND: If the answer cannot be found completely in the context, or if the context lacks the specific fact asked, set "found": false, "answer": "Not found", and "confidence": "high".
3. CONCISENESS: If found, the answer must be at most 3 sentences.
4. OUTPUT FORMAT: Respond ONLY with a single JSON object. No markdown fences, no explanatory text before or after.
The object must follow this exact schema:
{{
  "answer": "<factual answer in max 3 sentences, or 'Not found'>",
  "found": true or false,
  "used_chunk_ids": [<list of integer chunk IDs used to answer, e.g. [1]>],
  "confidence": "high" or "medium" or "low"
}}

Few-shot Example 1 (Answer Found):
Context:
[Chunk 1 | Page: 36 | Chapter: Chapter 6 – Piracy of registered designs and consequences thereof | Section: 06.04 Period of protection]
The proprietor shall have copyright in the design for ten years from the date of registration. This period of ten years can be extended by five years.
Question: How long does a proprietor have copyright in a registered design, and can it be extended?
Output:
{{
  "answer": "A proprietor has copyright in a registered design for ten years from the date of registration. This initial period of ten years can be extended by an additional period of five years.",
  "found": true,
  "used_chunk_ids": [1],
  "confidence": "high"
}}

Few-shot Example 2 (Not Found / Outside Context):
Context:
[Chunk 1 | Page: 51 | Chapter: Chapter 11 – General powers of Controller | Section: 11.01 Powers of a Civil Court]
The Controller shall have certain powers of a Civil Court under the Code of Civil Procedure while trying a suit.
Question: What is the current GST tax rate on services in India?
Output:
{{
  "answer": "Not found",
  "found": false,
  "used_chunk_ids": [],
  "confidence": "high"
}}

Few-shot Example 3 (Statutory Schedule Reference):
Context:
[Chunk 1 | Page: 22 | Chapter: Chapter 3 – Filing of Design Application | Section: 03.08 Fee]
03.08 Fee: The fee to be paid in respect of any matter is prescribed in the First Schedule of The Design Rules, 2001.
Question: What is the fee to register a design?
Output:
{{
  "answer": "The fee to be paid for design registration is prescribed in the First Schedule of The Design Rules, 2001, and can be paid in cash, electronic means, bank draft, or cheque.",
  "found": true,
  "used_chunk_ids": [1],
  "confidence": "high"
}}
"""


def get_vector_store():
    """Initializes and returns the Chroma vector store."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY is not set in environment or .env file.")

    embeddings = GoogleGenerativeAIEmbeddings(
        model="models/gemini-embedding-001",
        google_api_key=api_key,
    )
    client = chromadb.PersistentClient(path=DB_DIR)
    vector_store = Chroma(
        client=client,
        collection_name=COLLECTION_NAME,
        embedding_function=embeddings,
        persist_directory=DB_DIR,
    )
    return vector_store


def format_context_for_prompt(docs_with_scores: List[Tuple[Document, float]]) -> str:
    """Formats retrieved chunks with Chunk IDs and metadata for the LLM."""
    formatted_chunks = []
    for idx, (doc, score) in enumerate(docs_with_scores, 1):
        page = doc.metadata.get("page", "Unknown")
        chapter = doc.metadata.get("chapter", "Unknown")
        section = doc.metadata.get("section", "Unknown")
        header = f"[Chunk {idx} | Page: {page} | Chapter: {chapter} | Section: {section}]"
        formatted_chunks.append(f"{header}\n{doc.page_content}")
    return "\n\n".join(formatted_chunks)


def build_citations_from_metadata(
    docs_with_scores: List[Tuple[Document, float]],
    used_chunk_ids: List[int],
) -> List[Dict[str, Any]]:
    """Builds reliable citations strictly from retrieved chunk metadata (anti-hallucination)."""
    citations = []
    seen = set()

    target_ids = used_chunk_ids if used_chunk_ids else [1]

    for chunk_id in target_ids:
        if 1 <= chunk_id <= len(docs_with_scores):
            doc, _ = docs_with_scores[chunk_id - 1]
            page = doc.metadata.get("page", 0)
            chapter = doc.metadata.get("chapter", "Unknown")
            section = doc.metadata.get("section", "Unknown")
            key = (page, chapter, section)
            if key not in seen:
                seen.add(key)
                citations.append({
                    "page": page,
                    "chapter": chapter,
                    "section": section,
                })
    return citations


class DesignsLawRAG:
    """RAG Assistant implementing Layer A (Retrieval Gate) and Layer B (Prompt Gate)."""

    def __init__(self, k: int = 5, score_threshold: float = SCORE_THRESHOLD):
        self.k = k
        self.score_threshold = score_threshold
        self.vector_store = get_vector_store()

        api_key = os.getenv("GEMINI_API_KEY")
        model_name = os.getenv("MODEL_NAME", "gemini-2.5-flash")
        self.llm = ChatGoogleGenerativeAI(
            model=model_name,
            google_api_key=api_key,
            temperature=0.0,
        )

        self.prompt_template = ChatPromptTemplate.from_messages([
            ("system", SYSTEM_PROMPT),
            ("user", "Context:\n{context}\n\nQuestion: {question}"),
        ])
        self.parser = JsonOutputParser()

        # LCEL chain: prompt | model | parser (repo style)
        self.lcel_chain = self.prompt_template | self.llm | self.parser

    def query(self, question: str) -> Dict[str, Any]:
        """Executes full RAG query with 2-layer Not found gate and metadata citations."""
        # 1. Retrieve with relevance scores
        docs_with_scores = self.vector_store.similarity_search_with_relevance_scores(question, k=self.k)

        if not docs_with_scores:
            return {
                "answer": "Not found",
                "found": False,
                "citations": [],
                "confidence": "high",
                "gate_triggered": "Layer A (no documents returned)",
                "best_score": 0.0,
            }

        best_score = docs_with_scores[0][1]

        # 2. LAYER A: Retrieval Gate
        if best_score < self.score_threshold:
            logging.info("Layer A Gate triggered: best score %.4f < threshold %.4f", best_score, self.score_threshold)
            return {
                "answer": "Not found",
                "found": False,
                "citations": [],
                "confidence": "high",
                "gate_triggered": "Layer A (retrieval score below threshold)",
                "best_score": best_score,
            }

        # 3. LAYER B: Prompt Gate (LCEL chain)
        context_str = format_context_for_prompt(docs_with_scores)
        payload = {"context": context_str, "question": question}

        parsed_response = None
        max_attempts = 4
        for attempt in range(max_attempts):
            try:
                parsed_response = self.lcel_chain.invoke(payload)
                break
            except Exception as exc:
                err_str = str(exc)
                if "429" in err_str or "ResourceExhausted" in err_str:
                    # Parse retry delay or default to 30s
                    retry_match = re.search(r"retry in (\d+(?:\.\d+)?)s", err_str)
                    wait_sec = float(retry_match.group(1)) + 2 if retry_match else 30.0
                    logging.warning("Gemini 5 RPM limit reached. Waiting %.1fs before retry (attempt %d/%d)...", wait_sec, attempt + 1, max_attempts)
                    time.sleep(wait_sec)
                    continue

                logging.warning("JSON parsing attempt %d failed: %s", attempt + 1, exc)
                if attempt == max_attempts - 1:
                    return {
                        "answer": "Not found",
                        "found": False,
                        "citations": [],
                        "confidence": "low",
                        "gate_triggered": "JSON parse error fallback",
                        "best_score": best_score,
                    }

        if parsed_response is None:
            return {
                "answer": "Not found",
                "found": False,
                "citations": [],
                "confidence": "low",
                "gate_triggered": "Rate limit / parsing error",
                "best_score": best_score,
            }

        # Process parsed response
        is_found = parsed_response.get("found", False)
        answer_text = str(parsed_response.get("answer", "Not found")).strip()

        # Normalize answer if model indicates Not found in text
        if not is_found or answer_text.lower() in {"not found", "not found.", "not in my documents"}:
            return {
                "answer": "Not found",
                "found": False,
                "citations": [],
                "confidence": parsed_response.get("confidence", "high"),
                "gate_triggered": "Layer B (prompt gate)",
                "best_score": best_score,
            }

        used_chunk_ids = parsed_response.get("used_chunk_ids", [1])
        citations = build_citations_from_metadata(docs_with_scores, used_chunk_ids)

        return {
            "answer": answer_text,
            "found": True,
            "citations": citations,
            "confidence": parsed_response.get("confidence", "high"),
            "gate_triggered": "None (Answer found)",
            "best_score": best_score,
        }
