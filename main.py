import json
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from agents.debater import DebaterAgent
from core.rag_service import RAGService

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

POLICIES_DIR = Path("data/policies")
AGENT_ORDER = ["USA", "EU", "China"]
COUNTRY_FILE_MAP = {
    "usa": "usa_policy.json",
    "eu": "eu_policy.json",
    "china": "china_policy.json",
}

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
LLM_MODEL_NAME = os.getenv("LLM_MODEL_NAME", "llama3.1:8b")

rag_service: RAGService | None = None


async def _pull_model() -> None:
    try:
        async with httpx.AsyncClient(timeout=600.0) as client:
            logger.info("Pulling model %s from Ollama...", LLM_MODEL_NAME)
            response = await client.post(
                f"{OLLAMA_BASE_URL}/api/pull",
                json={"name": LLM_MODEL_NAME, "stream": False},
            )
            response.raise_for_status()
            logger.info("Model %s is ready.", LLM_MODEL_NAME)
    except Exception as exc:
        logger.warning(
            "Could not pull model %s: %s. Continuing — model may already be cached.",
            LLM_MODEL_NAME,
            exc,
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    global rag_service
    logger.info("Initialising RAG service...")
    rag_service = RAGService(policies_dir=POLICIES_DIR)
    await rag_service.initialize()
    logger.info("RAG service ready.")
    await _pull_model()
    yield
    rag_service = None
    logger.info("Application shutdown complete.")


app = FastAPI(
    title="Climate Policy Debate Simulator",
    description=(
        "A multi-agent AI system that simulates structured debates between "
        "USA, EU, and China representatives on global climate policy topics."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/", include_in_schema=False)
async def serve_frontend() -> FileResponse:
    return FileResponse("static/index.html", media_type="text/html")


@app.get("/health", tags=["System"])
async def health_check() -> dict:
    return {"status": "ok"}


@app.get("/policies/{country_code}", tags=["Policies"])
async def get_policy(country_code: str) -> dict:
    code = country_code.lower()
    if code not in COUNTRY_FILE_MAP:
        raise HTTPException(
            status_code=404,
            detail=f"No policy document found for country code '{country_code}'. "
                   f"Valid codes are: usa, eu, china.",
        )
    file_path = POLICIES_DIR / COUNTRY_FILE_MAP[code]
    if not file_path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Policy file for '{country_code}' is missing from the data directory.",
        )
    with open(file_path, "r", encoding="utf-8") as f:
        policy = json.load(f)
    return policy


class DebateRequest(BaseModel):
    topic: str = Field(
        ...,
        min_length=1,
        description="The subject of the climate policy debate.",
    )
    rounds: int = Field(
        ...,
        ge=1,
        le=5,
        description="Number of debate rounds. Each round produces one statement per agent.",
    )


class DebateMessage(BaseModel):
    round: int
    agent: str
    message: str
    stance: Literal["supportive", "opposed", "neutral"]
    timestamp: str


class DebateResponse(BaseModel):
    messages: list[DebateMessage]


@app.post("/debate/start", response_model=DebateResponse, tags=["Debate"])
async def start_debate(request: DebateRequest) -> DebateResponse:
    if rag_service is None:
        raise HTTPException(
            status_code=503,
            detail="RAG service is not initialised. The application may still be starting up.",
        )

    logger.info(
        "Starting debate: topic='%s', rounds=%d", request.topic, request.rounds
    )

    messages: list[DebateMessage] = []
    history: list[dict] = []

    for round_number in range(1, request.rounds + 1):
        for agent_name in AGENT_ORDER:
            relevant_context = await rag_service.retrieve(
                agent_name=agent_name,
                query=request.topic,
                history=history,
            )
            agent = DebaterAgent(
                country=agent_name,
                policy_context=relevant_context,
            )
            try:
                response = await agent.generate(
                    topic=request.topic,
                    history=history,
                )
            except RuntimeError as exc:
                raise HTTPException(
                    status_code=502,
                    detail=f"LLM generation failed for agent {agent_name}: {exc}",
                ) from exc

            msg = DebateMessage(
                round=round_number,
                agent=agent_name,
                message=response["message"],
                stance=response["stance"],
                timestamp=datetime.now(timezone.utc).isoformat(),
            )
            messages.append(msg)
            history.append(
                {"agent": agent_name, "message": response["message"]}
            )
            logger.info(
                "Round %d — %s responded (stance: %s)",
                round_number,
                agent_name,
                response["stance"],
            )

    logger.info("Debate complete. Total messages: %d", len(messages))
    return DebateResponse(messages=messages)
