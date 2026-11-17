# DocuRAG — AI Document Q&A System (RAG-based PDF Chatbot)

An end-to-end, full-stack **Retrieval-Augmented Generation (RAG)** chatbot that allows users to upload multi-page PDF documents and ask natural-language questions. The system extracts text page-by-page, generates dense vector embeddings locally using **BGE-M3**, indexes vectors in **FAISS**, persists metadata in **PostgreSQL**, and synthesizes grounded answers with **Google Gemini API** (`gemini-2.0-flash`), citing exact source document names and page numbers.

---

## 🌟 Key Features

- 📄 **Page-Aware PDF Ingestion:** Extracts text page-by-page using PyMuPDF (`fitz`), tracking 1-indexed page numbers.
- 🧩 **Smart Recursive Chunking:** Splits text (~600 tokens window, ~100 token overlap) while preserving page-level attribution for 100% accurate citations.
- 🧠 **Local BGE-M3 Embeddings:** Runs `BAAI/bge-m3` locally via `sentence-transformers` without requiring any paid embedding APIs.
- ⚡ **High-Performance Vector Storage:** Fast cosine similarity retrieval using FAISS `IndexIDMap2` with `IndexFlatIP`, persisted to disk (`index.faiss`).
- 🤖 **Grounded Gemini Generation:** Answers are synthesized using Google Gemini API (`gemini-2.0-flash`) behind an extensible `BaseLLMProvider` interface.
- 🛡️ **Anti-Hallucination Guardrail:** The model is strictly instructed to answer only from retrieved passages. If the answer is not present, it explicitly states that the documents do not contain the answer.
- 📌 **Interactive Source Citations:** Every answer displays the source document, page number, relevance score, and an expandable passage preview showing the exact text used.
- 🗄️ **Full Persistence:** PDF files, chunk text, page numbers, and chat history are persisted in PostgreSQL across container restarts.
- 🔄 **Document Management:** Multi-document support, filtering queries to specific PDFs, and instant deletion with vector removal from the FAISS index.
- 🐳 **Dockerized:** Fully orchestrated multi-service architecture (FastAPI backend, React/Vite frontend, PostgreSQL database).

---

## 🏗️ System Architecture

```
+---------------------------------------------------------------------------------+
|                                 React Frontend                                  |
|     (File Dropzone, Document Manager, Chat Stream, Interactive Citations)       |
+---------------------------------------+-----------------------------------------+
                                        | REST API (Port 8000)
                                        v
+---------------------------------------------------------------------------------+
|                                FastAPI Backend                                  |
|                                                                                 |
|  +--------------------+   +---------------------+   +------------------------+  |
|  | Ingestion Pipeline |   |  Retrieval Engine   |   |   Generation Engine    |  |
|  | - PyMuPDF (fitz)   |   | - Query Embedding   |   | - BaseLLMProvider      |  |
|  | - Recursive Chunker|   | - FAISS top-k search|   | - GeminiLLMProvider    |  |
|  | - BGE-M3 Embedder  |   | - DB Chunk hydrate  |   |   (gemini-2.0-flash)   |  |
|  +---------+----------+   +----------+----------+   +-----------+------------+  |
+------------|-------------------------|--------------------------|---------------+
             |                         |                          |
             v                         v                          v
    +-----------------+       +-----------------+       +--------------------+
    |   PostgreSQL    |       |   FAISS Index   |       |  Google Gemini API |
    | (Docs & Chunks) |       | (Disk Persisted)|       | (Free Tier Flash)  |
    +-----------------+       +-----------------+       +--------------------+
```

### Retrieval & Generation Flow

```
PDF Upload -> PyMuPDF (page tracking) -> Recursive Chunker -> BGE-M3 Local Embedder
      -> PostgreSQL (Doc & Chunk metadata) + FAISS Index (Vectors)

User Query -> BGE-M3 Query Embedding -> FAISS Top-K Search -> PostgreSQL Chunks
      -> Grounded Prompt Assembly (Context + Question) -> Gemini 2.0 Flash
      -> Answer with Document Name & Page Number Citations
```

---

## 📁 Repository Structure

```
.
├── docker-compose.yml           # Docker orchestration (postgres, backend, frontend)
├── .env.example                 # Environment variables template
├── .env                         # Local environment configuration
├── .gitignore                   # Ignored files (data, uploads, caches, models)
├── README.md                    # Project documentation & walkthrough
├── backend/
│   ├── Dockerfile               # Python 3.11 container build
│   ├── requirements.txt         # FastAPI, PyMuPDF, SentenceTransformers, FAISS, etc.
│   ├── app/
│   │   ├── main.py              # FastAPI app initialization, CORS, and lifespans
│   │   ├── core/
│   │   │   └── config.py        # Settings via Pydantic BaseSettings
│   │   ├── db/
│   │   │   ├── database.py      # SQLAlchemy session factory & connection retry
│   │   │   └── models.py        # Document, Chunk, ChatMessage models
│   │   ├── ingestion/
│   │   │   ├── pdf_parser.py    # PyMuPDF page-aware text extractor
│   │   │   ├── chunker.py       # Page-aware recursive text chunker
│   │   │   ├── embedder.py      # BGE-M3 local sentence transformer
│   │   │   └── vector_store.py  # FAISS IndexIDMap2 vector index manager
│   │   ├── retrieval/
│   │   │   └── retriever.py     # Similarity search & metadata hydration
│   │   ├── generation/
│   │   │   └── llm_provider.py  # BaseLLMProvider & GeminiLLMProvider
│   │   └── api/
│   │       ├── health.py        # /api/health and /api/health/llm
│   │       ├── documents.py     # /api/documents (upload, list, delete)
│   │       └── chat.py          # /api/chat (query, history, clear)
│   └── tests/
│       ├── test_chunker.py      # Unit tests for chunking & page metadata
│       ├── test_retrieval.py    # Unit tests for FAISS vector storage & top-k
│       └── test_api.py          # Integration tests for FastAPI endpoints
└── frontend/
    ├── Dockerfile               # Node.js 20 container build
    ├── package.json             # React 18, Lucide icons, Vite
    ├── vite.config.js           # Vite dev server with /api proxy
    ├── index.html               # Entry HTML
    └── src/
        ├── main.jsx             # React DOM root
        ├── App.jsx              # Main UI (Upload, Doc List, Chat, Citations)
        └── index.css            # Modern styling & theme tokens
```

---

## 🚀 Quick Start (Docker Compose)

### 1. Prerequisites
- Docker and Docker Compose installed.
- A free Google Gemini API key from [Google AI Studio](https://aistudio.google.com/).

### 2. Configure Environment
Copy `.env.example` to `.env` and insert your `GEMINI_API_KEY`:
```bash
cp .env.example .env
```
Edit `.env`:
```ini
GEMINI_API_KEY=AIzaSyYourActualKeyHere
GEMINI_MODEL=gemini-2.0-flash
```

### 3. Launch Services
Run the following command in the project root:
```bash
docker-compose up --build
```

### 4. Access the Application
- **Frontend UI:** [http://localhost:3000](http://localhost:3000)
- **Backend API Docs (Swagger):** [http://localhost:8000/docs](http://localhost:8000/docs)
- **Health Check:** [http://localhost:8000/api/health](http://localhost:8000/api/health)

---

## 🧪 Local Manual Execution (Without Docker)

If you prefer to run services natively on your host machine:

### Backend
1. Create and activate a Python virtual environment:
   ```bash
   python -m venv venv
   # Windows:
   .\venv\Scripts\activate
   # Linux/macOS:
   source venv/bin/activate
   ```
2. Install dependencies:
   ```bash
   pip install -r backend/requirements.txt
   ```
3. Set your environment variables in `.env` (ensure `POSTGRES_HOST=localhost` if using a local Postgres instance).
4. Run the FastAPI development server:
   ```bash
   cd backend
   uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
   ```

### Frontend
1. Open a new terminal in `frontend/`:
   ```bash
   cd frontend
   npm install
   npm run dev
   ```
2. Open [http://localhost:3000](http://localhost:3000) in your browser.

---

## 🎯 Verification & Demo Walkthrough

Follow this step-by-step checklist to test all core capabilities:

### Step 1: Upload a PDF
1. Open [http://localhost:3000](http://localhost:3000).
2. Drag and drop any multi-page PDF document into the upload panel on the left (e.g. an academic paper, product manual, or quarterly financial report).
3. Observe the progress status:
   - `Uploading & extracting pages...`
   - `Chunking & generating BGE-M3 embeddings...`
   - `Indexing completed!`
4. Verify the document appears in the **Indexed Documents** sidebar showing:
   - Document filename
   - Total page count
   - Generated chunk count
   - File size

### Step 2: Ask a Factual Question & Verify Citations
1. In the chat box, type a factual question about content located on a specific page of your uploaded PDF (e.g., *"What were the total revenues in Q3?"* or *"What is the main finding in Section 2?"*).
2. Press **Enter** or click **Send**.
3. **Verify:**
   - The assistant answers the question accurately.
   - A **Sources & Citations** panel appears below the answer.
   - The citation displays the document name, exact page number, and similarity score.
   - Click **View passage** to expand and review the exact text snippet extracted from the PDF.

### Step 3: Test Document Scope Filtering
1. Upload a second PDF document.
2. In the **Query Scope** dropdown on the left, change the selection from *"Search All Documents"* to one specific document.
3. Ask a question relevant only to the selected document.
4. Verify that all returned citations originate exclusively from that selected document.

### Step 4: Test Anti-Hallucination Guardrail
1. Ask a question about a topic completely absent from the document (e.g., *"What is the recipe for chocolate chip cookies?"* or *"Who won the 1994 FIFA World Cup?"*).
2. **Verify:**
   - The assistant does NOT hallucinate or use outside knowledge.
   - It responds: *"I cannot find the answer in the provided documents based on the retrieved excerpts."*

### Step 5: Test Persistence & Document Deletion
1. Click the **Trash** icon next to an uploaded document in the sidebar and confirm deletion.
2. Verify the document disappears from the list.
3. Ask a question regarding the deleted document; verify the system no longer retrieves information from it.

---

## 🔬 Automated Tests

Run the automated test suite with pytest:
```bash
pytest backend/tests/ -v
```
Tests cover:
- **`test_chunker.py`**: Validates character splitting, overlapping windows, and strict page number retention across multi-page boundaries.
- **`test_retrieval.py`**: Validates FAISS vector insertion, top-k inner-product search shapes, vector ID removal, and index persistence.
- **`test_api.py`**: Validates API response codes, input validation (blocking non-PDFs/empty files), and empty-state chat handling.

---

## ⚙️ Configuration Reference (`.env`)

| Variable | Default | Description |
| :--- | :--- | :--- |
| `GEMINI_API_KEY` | *(Required)* | Google Gemini API key |
| `GEMINI_MODEL` | `gemini-2.0-flash` | Gemini model name |
| `DATABASE_URL` | `postgresql://raguser:ragpassword@postgres:5432/ragdb` | PostgreSQL connection string |
| `EMBEDDING_MODEL_NAME` | `BAAI/bge-m3` | SentenceTransformers model for dense embeddings |
| `FAISS_INDEX_PATH` | `faiss_index/index.faiss` | File path for persisting the FAISS index |
| `CHUNK_SIZE` | `600` | Target chunk size (approx tokens) |
| `CHUNK_OVERLAP` | `100` | Overlap size between adjacent chunks (approx tokens) |
| `TOP_K` | `5` | Number of most similar chunks retrieved for generation |

---

## 📌 Known Limitations & Next Steps

1. **OCR for Scanned Documents:** Documents containing scanned images without embedded text layers require an OCR pre-processor (e.g. Tesseract or PyMuPDF OCR extension).
2. **Distributed Vector Indexing:** The current local FAISS index runs on a single node with local volume persistence. For high-scale enterprise deployments, Pgvector or a managed vector database (e.g. Qdrant / Milvus) can be adopted.
3. **User Authentication:** Currently designed for single-tenant local operation. Multi-tenant support can be added by incorporating JWT authentication and tenant-scoped document filters.
