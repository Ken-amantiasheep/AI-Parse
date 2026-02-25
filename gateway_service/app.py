"""
Internal AI gateway service.
Runs on the company server and keeps Anthropic API key only on server side.
"""
import logging
import os
import threading
import time
import uuid
from collections import defaultdict, deque
from pathlib import Path
from typing import Dict, Optional

from fastapi import FastAPI, Header, HTTPException, Request
from pydantic import BaseModel, Field

from utils.json_generator import IntactJSONGenerator
from version import APP_VERSION


class GenerateRequest(BaseModel):
    company: str = Field(default="Intact")
    documents: Dict[str, str]
    model: Optional[str] = None
    max_tokens: Optional[int] = None
    temperature: Optional[float] = None


def _build_logger() -> logging.Logger:
    logger = logging.getLogger("gateway")
    if logger.handlers:
        return logger

    log_dir = Path(os.environ.get("GATEWAY_LOG_DIR", "logs"))
    log_dir.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(log_dir / "gateway.log", encoding="utf-8")
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    return logger


class FixedWindowRateLimiter:
    def __init__(self, limit_per_minute: int):
        self.limit = limit_per_minute
        self.lock = threading.Lock()
        self.events = defaultdict(deque)

    def allow(self, key: str) -> bool:
        now = time.time()
        with self.lock:
            queue = self.events[key]
            while queue and (now - queue[0]) > 60:
                queue.popleft()
            if len(queue) >= self.limit:
                return False
            queue.append(now)
            return True


logger = _build_logger()
API_KEY = os.environ.get("ANTHROPIC_API_KEY", "").strip()
INTERNAL_TOKEN = os.environ.get("INTERNAL_API_TOKEN", "").strip()
RATE_LIMIT_PER_MIN = int(os.environ.get("RATE_LIMIT_PER_MIN", "60"))
limiter = FixedWindowRateLimiter(RATE_LIMIT_PER_MIN)

if not API_KEY:
    raise RuntimeError("ANTHROPIC_API_KEY is required")

app = FastAPI(title="AI Parse Gateway", version=APP_VERSION)


def _auth(x_internal_token: str):
    # If INTERNAL_API_TOKEN is set, enforce it. If empty, gateway works in trusted LAN mode.
    if INTERNAL_TOKEN and x_internal_token != INTERNAL_TOKEN:
        raise HTTPException(status_code=401, detail="Unauthorized")


@app.get("/health")
def health():
    return {"ok": True, "service": "ai-gateway", "version": APP_VERSION}


@app.post("/v1/generate-json")
def generate_json(req: GenerateRequest, request: Request, x_internal_token: str = Header(default="")):
    _auth(x_internal_token)

    client_key = x_internal_token or request.client.host or "anonymous"
    if not limiter.allow(client_key):
        raise HTTPException(status_code=429, detail="Rate limit exceeded")

    request_id = f"req_{uuid.uuid4().hex[:12]}"
    company = (req.company or "Intact").strip() or "Intact"

    if not req.documents:
        raise HTTPException(status_code=400, detail="documents is required")

    try:
        generator = IntactJSONGenerator(
            company=company,
            mode="direct",
            api_key=API_KEY
        )

        if req.model:
            generator.model = req.model
        if req.max_tokens:
            generator.max_tokens = req.max_tokens
        if req.temperature is not None:
            generator.temperature = req.temperature

        result = generator.generate_json_from_documents(req.documents, company=company)
        logger.info(
            "request_id=%s company=%s docs=%s status=success",
            request_id,
            company,
            ",".join(req.documents.keys())
        )
        return {"ok": True, "request_id": request_id, "data": result}
    except Exception as e:
        logger.exception("request_id=%s company=%s status=error error=%s", request_id, company, str(e))
        raise HTTPException(status_code=500, detail=f"Generation failed: {e}")
