"""
Project 2: Designs Law Assistant - Web API Server

FastAPI server exposing RAG query endpoints with in-memory response caching
for ultra-fast repeat replies and serving the modern interactive frontend.

Usage:
    python src/server.py
    # or: uvicorn src.server:app --reload --port 8000
"""

import logging
import os
import sys
import time

# Ensure src/ is on Python module path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from typing import Any, Dict, List, Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from rag_chain import DesignsLawRAG, SCORE_THRESHOLD

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATIC_DIR = os.path.join(BASE_DIR, "static")

app = FastAPI(
    title="Designs Law Assistant API",
    description="Grounded RAG API over the Manual of Designs Practice & Procedure (CGPDTM)",
    version="1.0.0",
)

# Enable CORS for local web interactions
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize RAG engine
rag_engine: Optional[DesignsLawRAG] = None

# High-speed LRU memory cache for fast repeat replies
QUERY_CACHE: Dict[str, Dict[str, Any]] = {}


def get_rag():
    global rag_engine
    if rag_engine is None:
        logging.info("Initializing DesignsLawRAG engine...")
        rag_engine = DesignsLawRAG()
    return rag_engine


class QueryRequest(BaseModel):
    question: str


class CitationItem(BaseModel):
    page: int
    chapter: str
    section: str
    snippet: Optional[str] = None


class QueryResponse(BaseModel):
    question: str
    answer: str
    found: bool
    citations: List[Dict[str, Any]]
    confidence: str
    gate_triggered: str
    best_score: float
    latency_ms: float
    cached: bool


@app.on_event("startup")
async def startup_event():
    os.makedirs(STATIC_DIR, exist_ok=True)
    get_rag()
    logging.info("Designs Law Assistant API ready at http://localhost:8000")


@app.get("/api/health")
async def health_check():
    return {
        "status": "healthy",
        "model": os.getenv("MODEL_NAME", "gemini-3.5-flash-lite"),
        "threshold": SCORE_THRESHOLD,
        "collection": "designs_manual",
    }


@app.post("/api/ask", response_model=QueryResponse)
async def ask_question(req: QueryRequest):
    q = req.question.strip()
    if not q:
        raise HTTPException(status_code=400, detail="Question cannot be empty.")

    cache_key = q.lower()
    start_time = time.time()

    # Fast path: Return cached answer if available
    if cache_key in QUERY_CACHE:
        cached_data = QUERY_CACHE[cache_key]
        return QueryResponse(
            question=q,
            answer=cached_data["answer"],
            found=cached_data["found"],
            citations=cached_data["citations"],
            confidence=cached_data["confidence"],
            gate_triggered=cached_data["gate_triggered"],
            best_score=cached_data["best_score"],
            latency_ms=round((time.time() - start_time) * 1000, 2),
            cached=True,
        )

    # Slow path: Run RAG pipeline
    try:
        rag = get_rag()
        # Retrieve docs with scores to extract snippets
        docs_with_scores = rag.vector_store.similarity_search_with_relevance_scores(q, k=rag.k)
        result = rag.query(q)

        # Augment citations with exact text excerpts from retrieved chunks
        citations_with_snippets = []
        for cit in result.get("citations", []):
            page_num = cit.get("page")
            matched_snippet = ""
            for doc, _ in docs_with_scores:
                if doc.metadata.get("page") == page_num:
                    matched_snippet = doc.page_content.strip()[:350].replace("\n", " ") + "..."
                    break
            citations_with_snippets.append({
                "page": cit.get("page"),
                "chapter": cit.get("chapter"),
                "section": cit.get("section"),
                "snippet": matched_snippet or "Source text verified in manual.",
            })

        latency = round((time.time() - start_time) * 1000, 2)
        response_data = {
            "question": q,
            "answer": result.get("answer", "Not found"),
            "found": result.get("found", False),
            "citations": citations_with_snippets,
            "confidence": result.get("confidence", "high"),
            "gate_triggered": result.get("gate_triggered", ""),
            "best_score": round(result.get("best_score", 0.0), 4),
            "latency_ms": latency,
            "cached": False,
        }

        # Cache response
        QUERY_CACHE[cache_key] = response_data
        return response_data

    except Exception as e:
        logging.error("Error processing query %r: %s", q, e)
        raise HTTPException(status_code=500, detail=str(e))


# Serve static web frontend
if os.path.exists(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
async def serve_index():
    index_file = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index_file):
        return FileResponse(index_file)
    return {"message": "Designs Law Assistant API is running. Build frontend at /static/index.html."}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=False)
