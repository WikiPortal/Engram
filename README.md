# Engram — Private AI Memory Layer

Engram is a fully private, self-hosted AI memory layer. It remembers your conversations, notes, and documents and makes that knowledge available in every AI interaction you have.

---

## What it does

- Extracts atomic facts from anything you tell it
- Deduplicates, contradiction-checks, and auto-expires time-sensitive memories
- Retrieves memories using hybrid search (BM25 + vector + reranker + HyDE)
- Injects relevant memories as context into every chat response
- Masks PII before storage, restores it on display
- Builds a knowledge graph of relationships between memories (UPDATES / EXTENDS / DERIVES)
- Works with any LLM — Gemini, OpenAI, Claude, DeepSeek
- Chrome extension that works transparently on claude.ai and ChatGPT
- Auth — sign up, sign in, each user gets their own isolated memory namespace

---

## Requirements

- Python 3.11+
- Node.js 18+
- Docker Desktop (for local databases)
- An API key for your chosen LLM provider

---

## Installation

### 1. Clone the repo

```bash
git clone https://github.com/ItsRoy69/Engram.git
cd Engram
```

### 2. Create your `.env` file

Copy the example and fill in your values:

```bash
cp env.example .env
```

Open `.env` and set at minimum:

```env
LLM_PROVIDER=gemini
GEMINI_API_KEY=your_key_here
AUTH_SECRET=any-long-random-string
```

Everything else has working defaults for local Docker.

### 3. Start the databases

```bash
docker compose up -d
```

Starts Qdrant (vectors), PostgreSQL (metadata/auth), Redis (TTL), FalkorDB (graph).

### 4. Apply the database schema

```bash
docker exec -i engram_postgres psql -U engram -d engram < docker/init.sql
```

### 5. Install Python dependencies

```bash
pip install -r backend/requirements.txt
python -m spacy download en_core_web_lg
```

### 6. Install frontend dependencies

```bash
cd chat-ui
npm install
cd ..
```

---

## Running

You need three terminals.

**Terminal 1 — Databases**
```bash
docker compose up
```

**Terminal 2 — API server**
```bash
cd backend
python -m uvicorn api:app --host 0.0.0.0 --port 8000 --reload
```

**Terminal 3 — Chat UI**
```bash
cd chat-ui
npm run dev
```

Open `http://localhost:3000` → sign up → start chatting.

---

## LLM Providers

Switch providers by changing two lines in `.env`:

```env
# Google Gemini (default, free tier)
LLM_PROVIDER=gemini
GEMINI_API_KEY=your_key

# OpenAI
LLM_PROVIDER=openai
OPENAI_API_KEY=your_key

# Anthropic Claude
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=your_key

# DeepSeek (cheapest option)
LLM_PROVIDER=deepseek
DEEPSEEK_API_KEY=your_key
```

Install the matching package if needed:
```bash
pip install openai        # for openai or deepseek
pip install anthropic     # for anthropic
```

Default models per provider: `gemini-2.0-flash` · `gpt-4o-mini` · `claude-3-5-haiku-20241022` · `deepseek-chat`

Override with `LLM_MODEL=model-name-here`.

---

## Hosted Databases (optional)

By default everything runs in local Docker. To use hosted services instead, add their connection URLs to `.env` — the local Docker services are ignored automatically.

**PostgreSQL → [Neon](https://neon.tech) (free)**
```env
DATABASE_URL=postgresql://user:pass@ep-xyz.neon.tech/dbname?sslmode=require
```

**Qdrant → [Qdrant Cloud](https://cloud.qdrant.io) (free)**
```env
QDRANT_URL=https://xyz.cloud.qdrant.io
QDRANT_API_KEY=your_api_key
```

**Redis → [Upstash](https://upstash.com) (free)**
```env
REDIS_URL=rediss://default:pass@xyz.upstash.io:6379
```

FalkorDB has no managed free tier — keep it running via Docker.

---

## Chrome Extension

1. Go to `chrome://extensions`
2. Enable **Developer mode**
3. Click **Load unpacked**
4. Select the `extension/` folder
5. Click the Engram icon → verify the status dot is green

The extension automatically injects relevant memories before you send a message on claude.ai or ChatGPT, and stores the conversation turn afterward.

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/auth/register` | Create account |
| `POST` | `/auth/login` | Sign in, get JWT |
| `POST` | `/memory/store` | Store content — full ingestion pipeline |
| `POST` | `/memory/recall` | Retrieve memories — full retrieval pipeline |
| `POST` | `/chat` | Memory-augmented chat |
| `GET` | `/memory/list/{user_id}` | List all memories for a user |
| `DELETE` | `/memory/{memory_id}` | Soft-delete a memory |
| `GET` | `/health` | Service health check |

Interactive docs: `http://localhost:8000/docs`

---

## Tech stack

| Layer | Technology | Cost |
|-------|-----------|------|
| LLM | Gemini / OpenAI / Claude / DeepSeek | Free tier available |
| Embeddings | sentence-transformers all-MiniLM-L6-v2 | Free (local) |
| Reranker | BAAI/bge-reranker-base | Free (local) |
| Vector DB | Qdrant (local or Qdrant Cloud) | Free |
| Graph DB | FalkorDB | Free (local) |
| Relational DB | PostgreSQL (local or Neon) | Free |
| Cache / TTL | Redis (local or Upstash) | Free |
| PII Detection | Microsoft Presidio | Free |
| Backend | FastAPI + uvicorn | Free |
| Frontend | Next.js 14 | Free |
| Extension | Chrome Manifest V3 | Free |
| **Total** | | **$0** |

---

## License

[MIT](./LICENSE) © 2026 Jyotirmoy Roy
