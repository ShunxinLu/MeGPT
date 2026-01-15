# Local Memory Agent (MeGPT)

A privacy-first personal AI assistant with persistent long-term memory and web search capabilities.

## 🏗️ Architecture

```
┌─────────────────┐         ┌─────────────────┐
│   Next.js UI    │◄─SSE───►│  FastAPI Server │
│  (localhost:3000)│         │  (localhost:8000)│
└─────────────────┘         └────────┬────────┘
                                     │
                            ┌────────▼────────┐
                            │  LangGraph Agent │
                            └────────┬────────┘
                       ┌─────────────┴─────────────┐
               ┌───────▼───────┐           ┌───────▼───────┐
               │  Mem0 Memory  │           │  Web Search   │
               │   (Qdrant)    │           │ (DuckDuckGo)  │
               └───────────────┘           └───────────────┘
```

## 🚀 Quick Start

### Prerequisites

1. **LM Studio** - Running with Qwen model at `http://localhost:1234/v1`
2. **Qdrant** - Vector database for memory
   ```bash
   docker run -p 6333:6333 qdrant/qdrant
   ```

### Backend Setup

```bash
# Install dependencies
pip install -r requirements.txt

# Run CLI
python main.py

# Or run API server
uvicorn server:app --reload --port 8000
```

### Frontend Setup

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:3000`

## 📁 Project Structure

```
MeGPT/
├── .env                 # Configuration
├── config.py            # Settings loader
├── main.py              # CLI entry point
├── server.py            # FastAPI backend
├── agent_graph.py       # LangGraph agent
├── tools/
│   ├── memory_tool.py   # Mem0 integration
│   └── web_search.py    # DuckDuckGo wrapper
├── utils/
│   └── llm_factory.py   # Universal LLM client
└── frontend/            # Next.js UI
```

## 🔧 Configuration

Edit `.env` to configure:

| Variable | Description |
|----------|-------------|
| `LLM_BASE_URL` | LM Studio / Ollama endpoint |
| `LLM_MODEL_NAME` | Model to use |
| `EMBEDDER_MODEL_NAME` | Embedding model for Mem0 |
| `QDRANT_HOST` | Qdrant server address |

## 📝 License

MIT
