# X-Ray Academy AI Assistant — Backend

Python FastAPI backend for the X-Ray Academy AI Assistant platform.

## Architecture

```
backend/
├── main.py                          # FastAPI app entry point
├── requirements.txt                 # Python dependencies
├── api/
│   ├── config.py                    # Pydantic Settings (env vars)
│   ├── routes/
│   │   ├── health.py                # GET /api/healthz
│   │   ├── chat.py                  # POST /api/chat, /api/conversations
│   │   ├── linkedin.py              # POST /api/linkedin/generate
│   │   ├── upload.py                # POST /api/upload/analyze
│   │   └── providers.py             # GET/POST /api/providers
│   ├── models/
│   │   ├── chat.py                  # Pydantic models for chat
│   │   ├── linkedin.py              # Pydantic models for LinkedIn
│   │   ├── upload.py                # Pydantic models for image analysis
│   │   └── providers.py             # Pydantic models for AI providers
│   └── services/
│       ├── store.py                 # In-memory data store
│       ├── xray_knowledge.py        # Domain knowledge base & system prompts
│       └── ai_providers/
│           ├── base.py              # Abstract base class
│           ├── mock_provider.py     # Built-in knowledge base (no API key needed)
│           ├── openai_provider.py   # OpenAI GPT-4o
│           ├── ollama_provider.py   # Ollama (local models)
│           ├── copilot_provider.py  # Microsoft Copilot / Azure OpenAI
│           └── registry.py          # Provider registry (singleton)
```

## Running Locally

```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

API docs available at: http://localhost:8000/api/docs

## Environment Variables

| Variable | Description | Default |
|---|---|---|
| `PORT` | Server port | `8000` |
| `ACTIVE_PROVIDER` | Active AI provider (`mock`, `openai`, `ollama`, `copilot`) | `mock` |
| `OPENAI_API_KEY` | OpenAI API key | — |
| `OPENAI_MODEL` | OpenAI model name | `gpt-4o` |
| `OLLAMA_BASE_URL` | Ollama server URL | `http://localhost:11434` |
| `OLLAMA_MODEL` | Ollama model name | `llama3.2` |
| `COPILOT_API_KEY` | Azure OpenAI API key | — |
| `COPILOT_ENDPOINT` | Azure OpenAI endpoint URL | — |
| `COPILOT_DEPLOYMENT` | Azure OpenAI deployment name | `gpt-4` |

## Adding a New AI Provider

1. Create `backend/api/services/ai_providers/my_provider.py`
2. Subclass `BaseAIProvider` and implement `chat`, `generate_linkedin_post`, `analyze_xray_image`
3. Register it in `registry.py`'s `_bootstrap_registry()` function

## Switching Providers at Runtime

```bash
# Activate OpenAI
curl -X POST http://localhost:8000/api/providers/openai/activate \
  -H "Content-Type: application/json" \
  -d '{"api_key": "sk-..."}'

# Switch back to the built-in knowledge base
curl -X POST http://localhost:8000/api/providers/mock/activate \
  -H "Content-Type: application/json" \
  -d '{"api_key": ""}'
```
