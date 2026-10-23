"""
Project 2: Designs Law Assistant - Step 1: Ingest Document

Loads the "Manual of Designs Practice & Procedure" PDF, extracts citation
metadata (1-indexed page, chapter, and section), chunks text with overlap,
embeds via Gemini embeddings, and stores idempotently in ChromaDB.

Usage:
    python src/ingest.py [data/manual_of_designs.pdf]
"""

import logging
import os
import re
import sys
import time
import chromadb
from dotenv import load_dotenv
from langchain_chroma import Chroma
from langchain_community.document_loaders import PyPDFLoader
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

# Disable telemetry noise
os.environ["ANONYMIZED_TELEMETRY"] = "False"

# Configure logging (repo style)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

load_dotenv()

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_DIR = os.path.join(BASE_DIR, "chroma_db")
COLLECTION_NAME = "designs_manual"

CHAPTER_TITLES = {
    1: "Chapter 1 – Introduction",
    2: "Chapter 2 – Important definitions",
    3: "Chapter 3 – Filing of Design Application",
    4: "Chapter 4 – Examination and registration of designs",
    5: "Chapter 5 – Patent Office Journal",
    6: "Chapter 6 – Piracy of registered designs and consequences thereof",
    7: "Chapter 7 – Post registration procedures",
    8: "Chapter 8 – Transfer of rights",
    9: "Chapter 9 – General Services",
    10: "Chapter 10 – Use and acquisition of registered design by Government",
    11: "Chapter 11 – General powers of Controller",
    12: "Chapter 12 – Evidences etc.",
    13: "Chapter 13 – Restrictive conditions in contract etc.",
    14: "Chapter 14 – Appeals",
    15: "Chapter 15 – Requirements before delivery on sales",
    16: "Chapter 16 – Timelines",
}

# Regex patterns derived directly from PDF inspection
CHAPTER_HEADING_RE = re.compile(r"^(?:\d+\s+)?CHAPTER\s*[-–—]?\s*(\d+)", re.IGNORECASE)
ANNEXURE_HEADING_RE = re.compile(r"^(?:\d+\s+)?ANNEXURE\s*[-–—]?\s*([IVXLCDM]+)", re.IGNORECASE)
SECTION_HEADING_RE = re.compile(r"(?:^|\n)\s*(\d{2}\.\d{2}(?:\.\d{2})*(?:\.\d{2})*)\s+([^\n\r]+)")


def process_and_chunk_documents(pdf_path: str):
    """Loads PDF and applies citation metadata tracking across pages and chunks."""
    if not os.path.exists(pdf_path):
        logging.error("PDF file not found at %r", pdf_path)
        sys.exit(1)

    loader = PyPDFLoader(pdf_path)
    pages = loader.load()
    logging.info("Loaded %d page(s) from %s", len(pages), pdf_path)

    splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=150)

    processed_chunks = []
    current_chapter = "Unknown"
    current_section = "Unknown"

    for idx, doc in enumerate(pages):
        page_1_based = idx + 1
        page_0_based = idx
        content = doc.page_content

        # Detect chapter or annexure headings at top of page (pages 5 onwards)
        if page_1_based > 4:
            top_lines = [line.strip() for line in content.split("\n") if line.strip()][:3]
            for line in top_lines:
                ch_match = CHAPTER_HEADING_RE.search(line)
                if ch_match:
                    ch_num = int(ch_match.group(1))
                    current_chapter = CHAPTER_TITLES.get(ch_num, f"Chapter {ch_num}")
                    current_section = "General"
                    break
                ann_match = ANNEXURE_HEADING_RE.search(line)
                if ann_match:
                    current_chapter = f"Annexure {ann_match.group(1)}"
                    current_section = "General"
                    break

        # Split current page into chunks
        page_chunks = splitter.split_documents([doc])

        for chunk in page_chunks:
            # Check if this chunk introduces a new section heading
            sec_matches = SECTION_HEADING_RE.findall(chunk.page_content)
            if sec_matches:
                sec_code, sec_name = sec_matches[-1]
                current_section = f"{sec_code} {sec_name.strip()[:60]}"

            chunk.metadata = {
                "source": "manual_of_designs.pdf",
                "page": page_1_based,
                "page_0_indexed": page_0_based,
                "chapter": current_chapter,
                "section": current_section,
            }
            processed_chunks.append(chunk)

    logging.info("Split into %d chunk(s)", len(processed_chunks))

    # Log 3 sample chunks with metadata (repo requirement)
    logging.info("=== Sample Chunks ===")
    sample_indices = [
        0,
        len(processed_chunks) // 2,
        len(processed_chunks) - 1,
    ]
    for idx in sample_indices:
        c = processed_chunks[idx]
        logging.info(
            "Chunk #%d | Page: %s | Chapter: %s | Section: %s\nSnippet: %s\n",
            idx + 1,
            c.metadata.get("page"),
            c.metadata.get("chapter"),
            c.metadata.get("section"),
            c.page_content[:150].replace("\n", " "),
        )

    return pages, processed_chunks


def ingest(pdf_path: str):
    """Embeds chunks and writes to ChromaDB collection idempotently in safe rate-limited batches."""
    pages, chunks = process_and_chunk_documents(pdf_path)

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        logging.error("GEMINI_API_KEY not found in environment or .env file.")
        sys.exit(1)

    # Use verified Gemini embedding model
    embedding_model = "models/gemini-embedding-001"
    embeddings = GoogleGenerativeAIEmbeddings(
        model=embedding_model,
        google_api_key=api_key,
    )

    logging.info("Connecting to ChromaDB at %s...", DB_DIR)
    client = chromadb.PersistentClient(path=DB_DIR)

    # Idempotent: delete existing collection if present
    try:
        client.delete_collection(COLLECTION_NAME)
        logging.info("Deleted existing collection %r to prevent duplicates.", COLLECTION_NAME)
    except Exception:
        logging.info("Collection %r does not exist yet; creating fresh.", COLLECTION_NAME)

    vector_store = Chroma(
        client=client,
        collection_name=COLLECTION_NAME,
        embedding_function=embeddings,
        persist_directory=DB_DIR,
    )

    # Ingest in batches with retry logic to respect Gemini free-tier rate limits (100 RPM)
    batch_size = 40
    total_chunks = len(chunks)
    logging.info("Ingesting %d chunks in batches of %d...", total_chunks, batch_size)

    for i in range(0, total_chunks, batch_size):
        batch = chunks[i : i + batch_size]
        batch_num = (i // batch_size) + 1
        total_batches = (total_chunks + batch_size - 1) // batch_size
        logging.info("Embedding batch %d/%d (chunks %d to %d)...", batch_num, total_batches, i + 1, min(i + batch_size, total_chunks))

        max_retries = 3
        for attempt in range(max_retries):
            try:
                vector_store.add_documents(batch)
                break
            except Exception as e:
                err_str = str(e)
                if "429" in err_str or "ResourceExhausted" in err_str:
                    wait_time = 45
                    logging.warning("Hit quota/rate limit on batch %d. Sleeping %ds before retry (attempt %d/%d)...", batch_num, wait_time, attempt + 1, max_retries)
                    time.sleep(wait_time)
                else:
                    raise

    logging.info("Successfully ingested all %d chunks into Chroma collection %r.", total_chunks, COLLECTION_NAME)

    # Sanity query verification
    sanity_query = "term of registration of a design"
    print("\n" + "=" * 65)
    print(f"SANITY QUERY TEST: '{sanity_query}'")
    print("=" * 65)
    results = vector_store.similarity_search(sanity_query, k=3)
    for i, doc in enumerate(results, 1):
        print(f"\n[Result {i}]")
        print(f"  Page:    {doc.metadata.get('page')}")
        print(f"  Chapter: {doc.metadata.get('chapter')}")
        print(f"  Section: {doc.metadata.get('section')}")
        print(f"  Snippet: {doc.page_content[:200].replace(chr(10), ' ')}...")
    print("\n" + "=" * 65 + "\n")


if __name__ == "__main__":
    default_pdf = os.path.join(BASE_DIR, "data", "manual_of_designs.pdf")
    pdf_file = sys.argv[1] if len(sys.argv) > 1 else default_pdf
    ingest(pdf_file)
