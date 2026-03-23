# Engram — Private AI Memory Layer

Engram is a fully private, self-hosted AI memory layer. It remembers your conversations, notes, and documents and makes that knowledge available in every AI interaction you have.

Everything runs locally. Zero cloud. Zero cost.

---

## What it does

- Extracts atomic facts from anything you tell it
- Deduplicates, contradiction-checks, and auto-expires time-sensitive memories
- Retrieves relevant memories using hybrid search (BM25 + vector + reranker)
- Injects memories as context into every chat response
- Masks PII before storage, restores it on display
- Builds a knowledge graph of relationships between memories
- Chrome extension that works transparently on claude.ai and ChatGPT

---

## Requirements

- Python 3.11+
- Node.js 18+
- Docker Desktop
- Google Gemini API key (free at [aistudio.google.com](https://aistudio.google.com))
- Chrome (for the extension)

---

## Installation

### 1. Clone the repo

```bash
git clone https://github.com/your-username/Engram.git
cd Engram
```

### 2. Start the databases

```bash
docker compose up -d
```

This starts four services:
- **Qdrant** on port 6333 — vector store
- **PostgreSQL** on port 5432 — metadata, audit log, PII vault
- **Redis** on port 6379 — TTL / auto-expiry
- **FalkorDB** on port 6380 — knowledge graph

Wait about 10 seconds for all services to be healthy.

### 3. Configure environment

```bash
cp backend/.env.example backend/.env
```

Open `backend/.env` and set your Gemini API key:

```
GEMINI_API_KEY=your_key_here
GEMINI_MODEL=gemini-2.0-flash
```

Everything else can stay as default for local use.

### 4. Install Python dependencies

```bash
pip install -r backend/requirements.txt
```

### 5. Install spaCy language model (required by Presidio for PII detection)

```bash
python -m spacy download en_core_web_lg
```

### 6. Install chat UI dependencies

```bash
cd chat-ui
npm install
cd ..
```

---

## Running

You need three terminals running simultaneously.

### Terminal 1 — Databases

```bash
docker compose up
```

Keep this running. You can also run it detached with `docker compose up -d`.

### Terminal 2 — API server

```bash
cd backend
python -m uvicorn api:app --host 0.0.0.0 --port 8000 --reload
```

The API will be available at `http://localhost:8000`.  
Interactive docs at `http://localhost:8000/docs`.

### Terminal 3 — Chat UI

```bash
cd chat-ui
npm run dev
```

Open `http://localhost:3000` in your browser.

---

## Chrome Extension

1. Open Chrome and go to `chrome://extensions`
2. Enable **Developer mode** (toggle in the top right)
3. Click **Load unpacked**
4. Select the `Engram/extension/` folder
5. Click the Engram icon in your toolbar
6. Verify the status dot is green (API online)

The extension will automatically:
- Inject relevant memories before you send a message on claude.ai or ChatGPT
- Store the conversation turn after each AI response

---

## First use — Onboarding

On your first visit to the chat UI, go to the **Onboarding** tab. It walks you through 10 structured questions to seed your memory store and solve the cold-start problem. Each answer is stored as a set of facts.

---

## API endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/memory/store` | Store content — runs full ingestion pipeline |
| `POST` | `/memory/recall` | Retrieve memories — runs full retrieval pipeline |
| `POST` | `/chat` | Memory-augmented chat via Gemini |
| `GET` | `/memory/list/{user_id}` | List all memories for a user |
| `DELETE` | `/memory/{memory_id}` | Invalidate a memory (soft delete) |
| `GET` | `/health` | Service health check |

Full interactive API docs: `http://localhost:8000/docs`

---

## Running tests

Make sure Docker and the API server are running first.

```bash
# Test individual modules
python tests/test_memory.py
python tests/test_extractor.py
python tests/test_search.py
python tests/test_graph.py

# Test full pipeline
python tests/test_brain.py

# Test API endpoints (requires uvicorn running)
python tests/test_api.py
```

---

**Docker port conflicts**  
If port 6379 (Redis) conflicts with an existing Redis instance, FalkorDB is already mapped to 6380. For Redis, edit `docker-compose.yml` and change `"6379:6379"` to `"6381:6379"` and update `REDIS_PORT=6381` in `.env`.

---

## Tech stack

| Layer | Technology | Cost |
|-------|-----------|------|
| LLM | Google Gemini 2.0 Flash | Free (20 req/day) |
| Embeddings | sentence-transformers all-MiniLM-L6-v2 | Free (local) |
| Reranker | BAAI/bge-reranker-base | Free (local) |
| Vector DB | Qdrant | Free (self-hosted) |
| Graph DB | FalkorDB | Free (self-hosted) |
| Relational DB | PostgreSQL 16 | Free (self-hosted) |
| Cache / TTL | Redis 7 | Free (self-hosted) |
| PII Detection | Microsoft Presidio | Free |
| Backend API | FastAPI + uvicorn | Free |
| Chat UI | Next.js 14 | Free |
| Extension | Chrome Manifest V3 | Free |
| **Total** | | **$0** |

---

## License

MIT
