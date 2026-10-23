# Project 2: Designs Law Assistant

A production-grade, grounded Retrieval-Augmented Generation (RAG) assistant for querying the **Manual of Designs Practice & Procedure** (published by the Office of the Controller General of Patents, Designs & Trade Marks - CGPDTM, IP India, 87 pages). The system strictly answers questions from the official PDF, provides authentic citations (Page, Chapter, and Section), and enforces a strict two-layer gate to reply exactly `"Not found"` when an answer is not contained in the document.

---

## 1. System Architecture & Flow

```text
[ Manual of Designs PDF (87 pp) ]
                │
                ▼
        [ PyPDFLoader ]  ──> Extracts 1-based page numbers & raw document text
                │
                ▼
    [ Metadata Tagging Engine ]  ──> Regex detection of Chapters (1-16 + Annexures) & Sections
                │
                ▼
  [ RecursiveCharacterTextSplitter ]  ──> Chunk size: 1000, Overlap: 150 (Preserves table rows)
                │
                ▼
  [ GoogleGenerativeAIEmbeddings ]  ──> Model: models/gemini-embedding-001 (dim: 3072)
                │
                ▼
   [ ChromaDB Vector Store ]  ──> Persisted locally at ./chroma_db (collection: designs_manual)
                │
                ▼
     [ Similarity Retriever ]  ──> Top k=5 chunks with relevance scores
                │
                ▼
    ┌───────────────────────────┐
    │ Layer A: Retrieval Gate   │ ──(Score < 0.50)──> Return "Not found" (Bypasses LLM)
    └─────────────┬─────────────┘
                  │ (Score >= 0.50)
                  ▼
    ┌───────────────────────────┐
    │   LCEL RAG Pipeline       │
    │  - ChatPromptTemplate     │
    │  - ChatGoogleGenerativeAI │ ──> Grounded prompt with 5 techniques + few-shot examples
    │  - JsonOutputParser       │
    └─────────────┬─────────────┘
                  │
                  ▼
    ┌───────────────────────────┐
    │   Layer B: Prompt Gate    │ ──(Info absent in context)──> Return "Not found"
    └─────────────┬─────────────┘
                  │ (Info verified in context)
                  ▼
      [ Answer + Grounded Metadata Citations ]
      {"answer": "...", "citations": [{"page": X, "chapter": "...", "section": "..."}]}
```

---

## 2. Technology Stack & Rationale

| Component | Library / Model | Why It Is Used |
|---|---|---|
| **Language & Env** | Python 3.9+, `python-dotenv` | Standard data science environment; loads API credentials securely from `.env`. |
| **Orchestration** | `langchain` (0.3.*), `langchain-core` | Declarative LangChain Expression Language (LCEL) pipelines (`prompt \| model \| parser`). |
| **Document Loader** | `pypdf` (5.0.*), `PyPDFLoader` | Reliable page-by-page text extraction with explicit page indexing. |
| **Text Splitter** | `RecursiveCharacterTextSplitter` | Splits long legal sections into 1000-char blocks with 150-char overlap to prevent sentence and table clipping. |
| **Embeddings** | `models/gemini-embedding-001` | High-dimensional (3072) legal semantic embeddings via official Google GenAI API. |
| **Vector Database** | `chromadb` (0.5.*), `langchain-chroma` | Serverless, fast local vector database with persistent storage and cosine relevance scores. |
| **Generative LLM** | `gemini-3.5-flash-lite` / `gemini-2.5-flash` | State-of-the-art reasoning, JSON schema compliance, and fast inference. |
| **Output Parsing** | `JsonOutputParser` | Enforces structured JSON output matching `{"answer", "found", "citations", "confidence"}`. |

---

## 3. Setup & Installation

### Step 1: Clone Repository & Navigate
```bash
git clone https://github.com/Rewaskc02-lang/Gen_Ai-product.git
cd Gen_Ai-product/designs-law-assistant
```

### Step 2: Create & Activate Virtual Environment
```bash
python3 -m venv venv
source venv/bin/activate
```

### Step 3: Install Pinned Dependencies
```bash
pip install -r requirements.txt
```

### Step 4: Configure Environment Variables
Copy `.env.example` to `.env` and provide your Gemini API key:
```bash
cp .env.example .env
```
Inside `.env`:
```ini
GEMINI_API_KEY=your_gemini_api_key_here
MODEL_NAME=gemini-3.5-flash-lite
```

### Step 5: Place PDF Document
Ensure the official CGPDTM PDF (87 pages) is placed at:
```text
data/manual_of_designs.pdf
```

---

## 4. Run Commands

### Ingest Document into ChromaDB
```bash
python src/ingest.py
```
*Loads the 87 pages, extracts chapter and section metadata, chunks into 163 blocks, embeds with Gemini, and persists to `./chroma_db`.*

### Interactive CLI Assistant
```bash
python src/ask.py
```
*Starts an interactive CLI query loop with citation displays and logs interactions to `outputs/interaction_log.jsonl`.*

### Interactive Web UI (FastAPI + Glassmorphism Frontend)
```bash
python src/server.py
```
*Starts the local web server at **http://localhost:8000** with:*
- **Sub-millisecond Cached Responses**: Fast repeat replies (`0.0ms` cached).
- **Interactive Benchmark Pills**: 1-click execution for all 5 project questions.
- **Rich Citation Cards**: Shows exact Page pills, Chapter badges, Section pills, and quote snippets from the manual.
- **Two-Layer Gate Status**: Real-time indicators showing whether an answer was grounded or blocked by the Retrieval/Prompt Gate.

### Run Benchmark Evaluation
```bash
python src/evaluate.py
```
*Executes the 5 project questions and 3 out-of-document questions, validates pass/fail criteria, and saves reports to `outputs/results.json`.*

---

## 5. Benchmark Results (5 Core Questions)

| # | Question | Grounded Answer | Citation (Page & Chapter/Section) |
|---|---|---|---|
| **1** | How long does a proprietor have copyright in a registered design, and can it be extended? | A proprietor shall have copyright in the design for **ten years** from the date of registration. This period of ten years can be **extended by five years** if the registered proprietor applies for extension in the prescribed manner. | **Page 36** (Chapter 6, Sec. 06.04 / 06.05)<br>**Page 39** (Chapter 7, Sec. 07.02) |
| **2** | Which classification system is used to register designs? | For the purpose of registration of designs, articles are classified into thirty-one classes and a miscellaneous class 99 based on the **International Classification of Industrial Designs according to the Locarno Agreement (Locarno Classification system)**, as described in The Third Schedule of The Design Rules, 2001. | **Page 20** (Chapter 3, Sec. 03.06.02.05)<br>**Page 14** (Chapter 3, Sec. 03.06.02.01)<br>**Page 5** (Chapter 1) |
| **3** | What is the government fee to register a trademark? | **Not found** | *None* (Blocked by **Layer A Gate**: score 0.4712 < 0.50; document covers industrial designs, not trademarks) |
| **4** | Who is the current Controller General of Patents? | **Not found** | *None* (Blocked by **Layer B Gate**: Section 02.02.01 on Page 7 defines statutory powers of Controller, but does not name any individual) |
| **5** | What is the fee to register a design? | The fee to be paid in respect of any matter, including design applications, is **prescribed in the First Schedule of The Design Rules, 2001**. This fee may be paid in cash, through electronic means, or sent by bank draft or cheque payable at par to the Controller of Designs. | **Page 22** (Chapter 3, Sec. 03.08 Fee)<br>**Page 14** (Chapter 3, Sec. 03.06.02.01) |

---

## 6. How "Not Found" Works: The Two-Layer Gate

To completely prevent hallucinations and unnecessary LLM costs, the system uses a dual-layer gating strategy:

1. **Layer A — Retrieval Relevance Gate (`SCORE_THRESHOLD = 0.50`)**:
   - Every user query is scored against ChromaDB chunks using cosine relevance (`similarity_search_with_relevance_scores`).
   - If the top chunk's score is below `0.50` (e.g. general trademarks, weather, or completely unrelated domains), the system immediately returns `"Not found"` **without calling the LLM**, saving API quota and latency.
2. **Layer B — Prompt Grounding Gate (Negative-Constraint Few-Shot Prompt)**:
   - When queries match IP-related keywords (scores >= 0.50) but ask for facts not contained in the text (such as Q4 asking for the current Controller General's personal name, or Q6 asking for AI patent criteria), the LLM strictly evaluates the excerpt.
   - The prompt explicitly forbids assuming or extrapolating facts. If the excerpt lacks the answer, the LLM outputs `{"answer": "Not found", "found": false}`.

---

## 7. Verification Screenshots

All CLI execution runs and outputs are stored in `screenshots/`:

| Screenshot | Description | File Link |
|---|---|---|
| **Screenshot #1** | Ingestion pipeline output (87 pages, 163 chunks, sanity query) | `screenshots/01_ingestion.png` |
| **Screenshot #2** | Question 1 answer + citations (Term of design copyright & extension) | `screenshots/02_q1.png` |
| **Screenshot #3** | Question 2 answer + citations (Locarno Classification system) | `screenshots/03_q2.png` |
| **Screenshot #4** | Question 3 answer (Trademark fee -> Not found via Layer A) | `screenshots/04_q3.png` |
| **Screenshot #5** | Question 4 answer (Controller General name -> Not found via Layer B) | `screenshots/05_q4.png` |
| **Screenshot #6** | Question 5 answer + citations (Design registration fee & Schedule) | `screenshots/06_q5.png` |

---

## 8. Limitations & Edge Cases

1. **External Statutory Schedules**: The official Manual of Designs Practice & Procedure refers fees to the *First Schedule of The Design Rules, 2001* rather than printing the numerical rupee table inside the manual. The RAG system accurately grounds its answer in this reference without fabricating numbers.
2. **Scanned / Image Text**: Non-searchable bitmap representations in Annexure II (specimen representations) contain raster graphics. While textual disclaimers are extracted, graphical drawings cannot be queried via text embeddings without OCR/multimodal pipelines.
3. **Threshold Calibration**: The calibrated threshold of `0.50` balances false-rejection against noise. Queries with ambiguous wording benefit from the Layer B fallback gate if they cross the score threshold.
