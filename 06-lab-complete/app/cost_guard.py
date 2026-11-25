"""
Cost guard (tiêu chí 8) — Cộng dồn chi phí LLM vào Redis.
"""
import time
from fastapi import HTTPException
from app.config import settings
from app.redis_client import r

# Giá USD / 1K tokens (tham khảo gpt-4o-mini)
PRICE_INPUT_PER_1K = 0.00015
PRICE_OUTPUT_PER_1K = 0.0006


def _cost_key() -> str:
    day = time.strftime("%Y-%m-%d")
    return f"cost:daily:{day}:{settings.agent_api_key or 'default'}"


def check_budget() -> None:
    """Gọi TRƯỚC khi gọi LLM. Hết budget -> raise HTTPException(status_code=402)."""
    budget = min(settings.daily_budget_usd, settings.monthly_budget_usd)
    try:
        raw = r.get(_cost_key())
        current_cost = float(raw) if raw is not None else 0.0
    except Exception:
        current_cost = 0.0

    if current_cost >= budget:
        raise HTTPException(
            status_code=402,
            detail={
                "error": "Budget exceeded",
                "used_usd": current_cost,
                "budget_usd": budget,
            },
        )


def record_cost(input_tokens: int, output_tokens: int) -> float:
    """Gọi SAU khi gọi LLM. Cộng chi phí của request vào tổng trong Redis."""
    cost = (input_tokens / 1000.0) * PRICE_INPUT_PER_1K + (output_tokens / 1000.0) * PRICE_OUTPUT_PER_1K
    key = _cost_key()
    try:
        r.incrbyfloat(key, cost)
        r.expire(key, 86400 * 2)
    except Exception:
        pass
    return cost
