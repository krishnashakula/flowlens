"""
FlowLens — Conversation Memory
Stores last 5 (user, agent) exchange pairs.
Primary store: Redis with 10-minute TTL.
Fallback: in-memory dict (no persistence across restarts).
"""

import json
import time
from typing import Optional

import structlog

log = structlog.get_logger(__name__)

MAX_EXCHANGES = 5
TTL_SECONDS = 600  # 10 minutes — resume on reconnect within this window


class ConversationMemory:
    """
    Manages a rolling window of the last MAX_EXCHANGES conversation turns.
    Thread-safe via asyncio; all methods are coroutines.
    """

    def __init__(self, session_id: str, redis_client):
        self.session_id = session_id
        self._redis = redis_client
        self._redis_key = f"flowlens:memory:{session_id}"
        self._exchanges: list[dict] = []  # in-memory fallback
        self._loaded = False

    # -----------------------------------------------------------------------
    # Persistence
    # -----------------------------------------------------------------------

    async def load(self):
        """Load memory from Redis on session start (warm-up)."""
        if self._redis:
            try:
                raw = await self._redis.get(self._redis_key)
                if raw:
                    try:
                        loaded = json.loads(raw)
                        if isinstance(loaded, list):
                            self._exchanges = loaded
                    except (json.JSONDecodeError, KeyError, TypeError) as parse_err:
                        log.warning("memory_parse_failed", error=str(parse_err))
                        self._exchanges = []
                    log.info(
                        "memory_loaded",
                        session_id=self.session_id,
                        exchanges=len(self._exchanges),
                    )
            except Exception as exc:
                log.warning("memory_load_failed", error=str(exc))
        self._loaded = True

    async def save(self):
        """Persist current memory to Redis with TTL."""
        if self._redis:
            try:
                await self._redis.setex(
                    self._redis_key,
                    TTL_SECONDS,
                    json.dumps(self._exchanges),
                )
            except Exception as exc:
                log.warning("memory_save_failed", error=str(exc))

    # -----------------------------------------------------------------------
    # Read / write
    # -----------------------------------------------------------------------

    async def append(self, user_turn: str, agent_turn: str):
        """Add a new exchange, evicting oldest if at capacity."""
        if not self._loaded:
            await self.load()
        self._exchanges.append(
            {
                "user": user_turn,
                "agent": agent_turn,
                "ts": time.time(),
            }
        )
        # Keep only last MAX_EXCHANGES
        if len(self._exchanges) > MAX_EXCHANGES:
            self._exchanges = self._exchanges[-MAX_EXCHANGES:]

        await self.save()

    async def get_context_string(self) -> str:
        """
        Return conversation history as a formatted string for Gemini context.
        """
        if not self._loaded:
            await self.load()
        if not self._exchanges:
            return ""

        lines: list[str] = []
        for i, ex in enumerate(self._exchanges, start=1):
            lines.append(f"Turn {i}:")
            lines.append(f"  User: {ex['user']}")
            lines.append(f"  FlowLens: {ex['agent']}")

        return "\n".join(lines)

    async def clear(self):
        """Wipe memory (called on explicit session reset)."""
        self._exchanges = []
        if self._redis:
            try:
                await self._redis.delete(self._redis_key)
            except Exception:
                pass

    @property
    def exchange_count(self) -> int:
        return len(self._exchanges)
