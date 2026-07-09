# Climate Policy Debate Simulator

Three AI agents — representing the United States, European Union, and China — debate
global climate policy in a structured, turn-based format. Each agent retrieves relevant
positions from its country's policy document before generating a response, so its
arguments are grounded in documented policy rather than general model knowledge.

The simulation runs entirely on local infrastructure using Ollama for the language model
and ChromaDB for in-memory vector retrieval. A single `docker-compose up` command starts
the complete system.

---

## Architecture

```
Browser
   |
   | HTTP
   v
FastAPI (port 8000)
   |
   |-- GET  /                  --> static/index.html
   |-- GET  /health            --> {"status": "ok"}
   |-- GET  /policies/{code}   --> policy JSON
   |-- POST /debate/start      --> debate transcript
   |
   |-- RAGService (ChromaDB, in-memory)
   |      |
   |      |-- usa_policy collection (all-MiniLM-L6-v2 embeddings)
   |      |-- eu_policy collection
   |      `-- china_policy collection
   |
   `-- DebaterAgent x3 (per turn)
          |
          | HTTP POST /api/generate
          v
       Ollama (port 11434)
          |
          `-- llama3.1:8b (local model)
```

### Debate flow

1. A POST request arrives with a topic and round count.
2. For each round, the coordinator iterates through USA, EU, China.
3. For each agent, the RAG service queries that agent's ChromaDB collection
   using the current topic and recent history as a composite query.
4. The top-k retrieved policy chunks are injected into the agent's prompt.
5. The agent calls the Ollama LLM and parses the response for a stance declaration.
6. The message is appended to the shared history and returned in the final transcript.

Turn order is fixed: USA then EU then China, repeating for each round.

---

## Prerequisites

- Docker Engine 24.0 or later
- Docker Compose 2.20 or later
- 6 GB of free disk space (for the LLM model and Docker layers)
- An internet connection on first run for the model download

---

## Getting Started

### 1. Clone the repository

```bash
git clone https://github.com/Rushikesh-5706/AI-Powered-Climate-Policy-Debate-Simulator.git
cd AI-Powered-Climate-Policy-Debate-Simulator
```

### 2. Configure environment

```bash
cp .env.example .env
```

The default values work without modification when running with Docker Compose. If you
are running the API outside Docker and have Ollama installed locally, change
`OLLAMA_BASE_URL` to `http://localhost:11434`.

### 3. Build and start

```bash
docker compose up --build
```

The first start downloads `llama3.1:8b` through Ollama (~4 GB). The model is stored in
the `ollama_data` volume and reused on all subsequent starts. The API becomes available
once both healthchecks pass — typically two to three minutes on first run.

### 4. Open the interface

Navigate to `http://localhost:8000` in a browser. Enter a topic, choose the number of
rounds, and click Run Simulation.

---

## API Reference

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Returns `{"status": "ok"}` when the service is running |
| GET | `/policies/{country_code}` | Returns the full policy document for `usa`, `eu`, or `china` |
| POST | `/debate/start` | Runs a full debate and returns the complete transcript |
| GET | `/` | Serves the frontend interface |

### POST /debate/start

**Request body**

```json
{
  "topic": "Carbon pricing mechanisms in international trade",
  "rounds": 2
}
```

`rounds` must be an integer between 1 and 5.

**Response body**

```json
{
  "messages": [
    {
      "round": 1,
      "agent": "USA",
      "message": "The United States recognises the importance of...",
      "stance": "supportive",
      "timestamp": "2024-06-01T10:30:00+00:00"
    }
  ]
}
```

The response contains `rounds × 3` messages. Agents appear in the order USA, EU, China
for every round. The `stance` field is always one of `supportive`, `opposed`, or
`neutral`.

**Interactive documentation** is available at `http://localhost:8000/docs` when the
application is running.

---

## Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `OLLAMA_BASE_URL` | URL of the Ollama service | `http://ollama:11434` |
| `LLM_MODEL_NAME` | Ollama model identifier | `llama3.1:8b` |

All variables are documented in `.env.example`. Copy it to `.env` before starting.

---

## Project Structure

```
.
├── agents/
│   ├── __init__.py
│   └── debater.py          # DebaterAgent: prompt construction and LLM calls
├── core/
│   ├── __init__.py
│   └── rag_service.py      # RAGService: document ingestion and retrieval
├── data/
│   └── policies/
│       ├── usa_policy.json
│       ├── eu_policy.json
│       └── china_policy.json
├── static/
│   ├── index.html          # Frontend UI
│   └── script.js           # Fetch API calls and DOM rendering
├── tests/
│   ├── __init__.py
│   ├── conftest.py
│   └── test_debate.py
├── main.py                 # FastAPI application, endpoints, lifespan
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
├── pytest.ini
├── .env.example
└── README.md
```

---

## Running Tests

Tests use mocked LLM responses so they do not require Ollama to be running.

```bash
# Install dependencies locally
pip install -r requirements.txt

# Run the full test suite
pytest tests/ -v
```

All tests should pass in roughly ten to thirty seconds depending on how long
sentence-transformers takes to load the embedding model on the first run.

---

## Stopping the Application

```bash
# Stop containers
docker compose down

# Stop containers and remove the model cache volume
docker compose down -v
```

---

## Design Notes

**Why in-memory ChromaDB**: The three policy documents are small and static.
Re-ingesting them at startup takes under two seconds. Persisting them to disk adds
volume management complexity for no practical benefit at this scale.

**Why the sentence-transformer model is pre-downloaded in the Dockerfile**: Downloading
a 90 MB model at container startup adds latency to every cold start. Baking it into the
image layer means the embedding function is available immediately.

**Why the stance is parsed from the response rather than using structured output**: Ollama
with llama3.1:8b supports JSON mode, but enforcing a strict schema across a multi-turn
conversation can cause the model to prioritise format compliance over content quality.
Parsing a clearly labelled last-line declaration is reliable and keeps the main response
free of format constraints.
