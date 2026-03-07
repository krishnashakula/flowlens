"""
FlowLens — FastAPI Backend Entry Point
Real-time voice + vision productivity agent powered by Gemini Live API.
"""

import asyncio
import json
import os
import re
import time
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

_SESSION_ID_RE = re.compile(r'^[a-zA-Z0-9_\-]{1,64}$')

# Auto-load .env from project root (two levels up from backend/)
from dotenv import load_dotenv

_env_path = Path(__file__).parent.parent / ".env"
load_dotenv(dotenv_path=_env_path, override=False)


import redis.asyncio as aioredis
import structlog
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles

from agent import FlowLensAgent
from memory import ConversationMemory

log = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# App state
# ---------------------------------------------------------------------------

_redis_client: Optional[aioredis.Redis] = None
_latency_store: dict = {
    "samples": [],
    "total_sessions": 0,
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialise shared resources; clean up on shutdown."""
    global _redis_client

    redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    try:
        _redis_client = await aioredis.from_url(
            redis_url,
            encoding="utf-8",
            decode_responses=False,
            socket_connect_timeout=3,
        )
        await _redis_client.ping()
        log.info("redis_connected", url=redis_url)
    except Exception as exc:
        log.warning("redis_unavailable", error=str(exc), fallback="in-memory")
        _redis_client = None  # agent will fall back gracefully

    yield

    # Shutdown
    if _redis_client:
        await _redis_client.aclose()
        log.info("redis_disconnected")


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(
    title="FlowLens",
    version="1.0.0",
    description="Real-time voice + vision AI agent",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Electron app uses custom scheme; credentials excluded to satisfy CORS spec
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve Vite-built frontend static assets (js/css/img)
_static_dir = Path(__file__).parent / "static"
if _static_dir.exists():
    app.mount("/assets", StaticFiles(directory=_static_dir / "assets"), name="assets")


# ---------------------------------------------------------------------------
# Root — landing page for judges hitting the bare URL
# ---------------------------------------------------------------------------


@app.get("/")
async def root():
    """Serve the React frontend, or JSON info if no static build present."""
    index = Path(__file__).parent / "static" / "index.html"
    if index.exists():
        return FileResponse(index)
    return JSONResponse(
        {
            "service": "FlowLens Backend",
            "status": "running",
            "description": "Real-time voice + vision AI productivity agent powered by Gemini Live API",
            "endpoints": {
                "health": "/health",
                "demo":   "/demo",
                "ws":     "/ws/{session_id}",
            },
            "github": "https://github.com/krishnashakula/flowlens",
        }
    )


# ---------------------------------------------------------------------------
# Health endpoint — doubles as "Proof of GCP Deployment" screen
# ---------------------------------------------------------------------------


@app.get("/health")
async def health() -> JSONResponse:
    """
    Returns live health + latency stats.
    This endpoint is shown in the hackathon demo video as GCP proof.
    """
    gemini_ok = bool(os.environ.get("GEMINI_API_KEY"))

    redis_ok = False
    if _redis_client:
        try:
            await asyncio.wait_for(_redis_client.ping(), timeout=1.0)
            redis_ok = True
        except Exception:
            redis_ok = False

    samples = _latency_store["samples"][-200:]  # last 200 samples
    p50 = _percentile(samples, 50) if samples else 0
    p95 = _percentile(samples, 95) if samples else 0

    return JSONResponse(
        {
            "status": "healthy",
            "gemini_connected": gemini_ok,
            "redis_connected": redis_ok,
            "p50_latency_ms": round(p50),
            "p95_latency_ms": round(p95),
            "total_sessions": _latency_store["total_sessions"],
        }
    )


@app.get("/demo")
async def demo_page():
    """Quick endpoint judges can hit to see live stats in a browser."""
    return JSONResponse(
        {
            "project": "FlowLens",
            "track": "Live Agent",
            "demo_url": os.environ.get("CLOUD_RUN_URL", "http://localhost:8000"),
            "health_url": "/health",
            "websocket_url": "/ws/{session_id}",
        }
    )


# ---------------------------------------------------------------------------
# WebSocket endpoint — one session per client connection
# ---------------------------------------------------------------------------


@app.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    # Validate session id to prevent Redis key injection
    if not _SESSION_ID_RE.match(session_id):
        await websocket.close(code=4000, reason="invalid session_id")
        return

    await websocket.accept()
    _latency_store["total_sessions"] += 1

    log.info("ws_connected", session_id=session_id)

    agent = FlowLensAgent(
        session_id=session_id,
        redis_client=_redis_client,
    )

    # Boot Gemini connection eagerly — reduces first-turn latency by ~400ms
    await agent.warm_up()

    try:
        while True:
            # Receive a turn: client sends a JSON envelope or raw bytes
            message = await websocket.receive()

            if message.get("type") == "websocket.disconnect":
                break

            # The agent handles the full turn internally and streams back audio
            latency_ms = await agent.handle_message(message, websocket)

            if latency_ms is not None:
                _latency_store["samples"].append(latency_ms)
                # Trim to last 1000 samples to prevent unbounded growth
                if len(_latency_store["samples"]) > 1000:
                    _latency_store["samples"] = _latency_store["samples"][-1000:]
                # Inform the frontend so the HUD can display live latency
                try:
                    await websocket.send_text(
                        json.dumps({"type": "latency", "ms": round(latency_ms)})
                    )
                except Exception:
                    pass

    except WebSocketDisconnect:
        log.info("ws_disconnected", session_id=session_id)
    except Exception as exc:
        log.error("ws_error", session_id=session_id, error=str(exc))
    finally:
        await agent.shutdown()
        log.info("agent_shutdown", session_id=session_id)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _percentile(data: list[float], pct: int) -> float:
    if not data:
        return 0.0
    sorted_data = sorted(data)
    idx = int(len(sorted_data) * pct / 100)
    idx = min(idx, len(sorted_data) - 1)
    return sorted_data[idx]


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 8000)),
        reload=os.environ.get("DEBUG", "false").lower() == "true",
        log_level="info",
    )
