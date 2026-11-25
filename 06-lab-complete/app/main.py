"""
Production AI Agent — Part 6 Final Project
"""
import json
import logging
import signal
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, Field

from app.auth import verify_api_key
from app.config import settings
from app.cost_guard import check_budget, record_cost
from app.rate_limiter import check_rate_limit
from app.redis_client import redis_healthy
from utils.mock_llm import ask as llm_ask


class JsonFormatter(logging.Formatter):
    """Định dạng mọi dòng log của app thành 1 JSON object hợp lệ trên 1 dòng."""

    def format(self, record: logging.LogRecord) -> str:
        msg = record.getMessage()
        try:
            parsed = json.loads(msg)
            if isinstance(parsed, dict):
                payload = {
                    "ts": datetime.now(timezone.utc).isoformat(),
                    "lvl": record.levelname,
                    **parsed,
                }
                return json.dumps(payload, ensure_ascii=False)
        except Exception:
            pass
        return json.dumps(
            {
                "ts": datetime.now(timezone.utc).isoformat(),
                "lvl": record.levelname,
                "logger": record.name,
                "msg": msg,
            },
            ensure_ascii=False,
        )


handler = logging.StreamHandler()
handler.setFormatter(JsonFormatter())
logger = logging.getLogger("agent")
logger.setLevel(logging.INFO)
logger.handlers = [handler]
logger.propagate = False

START_TIME = time.time()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(
        json.dumps(
            {
                "event": "startup",
                "environment": settings.environment,
                "port": settings.port,
            }
        )
    )
    yield
    logger.info(json.dumps({"event": "shutdown", "status": "graceful"}))


app = FastAPI(title="Production AI Agent", version="1.0.0", lifespan=lifespan)


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    user_id: str | None = Field(default="anonymous")


@app.get("/health")
def health():
    """Liveness probe: luôn trả 200 khi process còn chạy, không phụ thuộc Redis."""
    return {
        "status": "ok",
        "uptime_seconds": round(time.time() - START_TIME, 2),
        "environment": settings.environment,
    }


@app.get("/ready")
def ready():
    """Readiness probe: trả 200 khi Redis kết nối được, 503 khi Redis mất kết nối."""
    if not redis_healthy():
        logger.warning(json.dumps({"event": "readiness_failed", "reason": "redis_unavailable"}))
        raise HTTPException(status_code=503, detail="Redis unavailable")
    return {"status": "ready"}


@app.post("/ask")
def ask(body: AskRequest, api_key: str = Depends(verify_api_key)):
    """Protected endpoint: Auth (401) -> Rate Limit (429) -> Cost Guard (402) -> LLM -> Record Cost."""
    t0 = time.time()
    check_rate_limit(api_key)
    check_budget()

    answer = llm_ask(body.question)

    input_tokens = max(1, len(body.question.split()) * 2)
    output_tokens = max(1, len(answer.split()) * 2)
    cost = record_cost(input_tokens, output_tokens)
    latency_ms = round((time.time() - t0) * 1000, 2)

    logger.info(
        json.dumps(
            {
                "event": "ask",
                "path": "/ask",
                "status": 200,
                "ms": latency_ms,
                "cost_usd": round(cost, 8),
            }
        )
    )
    return {
        "question": body.question,
        "answer": answer,
        "cost_usd": round(cost, 8),
    }


_previous_sigterm = signal.getsignal(signal.SIGTERM)


def _on_sigterm(signum, frame):
    logger.info(json.dumps({"event": "sigterm_received", "signal": signum}))
    if callable(_previous_sigterm):
        _previous_sigterm(signum, frame)


signal.signal(signal.SIGTERM, _on_sigterm)
