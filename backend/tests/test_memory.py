"""
Tests for memory.py — ConversationMemory.

Risk tier: HIGH — conversation context powers every Gemini response.
Bugs here silently drop context or corrupt turns.

Test categories: capacity enforcement, redis persistence, redis failure
                 graceful degradation, context string format, isolation
                 between sessions, clear, load/save round-trip.
"""

import json

import pytest

from memory import MAX_EXCHANGES, TTL_SECONDS, ConversationMemory


# ---------------------------------------------------------------------------
# In-memory fallback (null_redis)
# ---------------------------------------------------------------------------

class TestMemoryWithoutRedis:
    """All operations must work when redis_client=None."""

    @pytest.mark.asyncio
    async def test_empty_memory_returns_empty_string(self):
        mem = ConversationMemory(session_id="s1", redis_client=None)
        assert await mem.get_context_string() == ""

    @pytest.mark.asyncio
    async def test_single_exchange_appears_in_context(self):
        mem = ConversationMemory(session_id="s2", redis_client=None)
        await mem.append("what is on my screen?", "VS Code with agent.py open")

        ctx = await mem.get_context_string()
        assert "what is on my screen?" in ctx
        assert "VS Code with agent.py open" in ctx

    @pytest.mark.asyncio
    async def test_multiple_exchanges_all_present(self):
        mem = ConversationMemory(session_id="s3", redis_client=None)
        await mem.append("q1", "a1")
        await mem.append("q2", "a2")
        await mem.append("q3", "a3")

        ctx = await mem.get_context_string()
        for token in ("q1", "a1", "q2", "a2", "q3", "a3"):
            assert token in ctx

    @pytest.mark.asyncio
    async def test_capacity_hard_cap_enforced(self):
        """Appending more than MAX_EXCHANGES must evict the oldest, never grow beyond cap."""
        mem = ConversationMemory(session_id="cap", redis_client=None)
        for i in range(MAX_EXCHANGES + 10):
            await mem.append(f"user-{i}", f"agent-{i}")

        assert mem.exchange_count == MAX_EXCHANGES  # never exceeds

    @pytest.mark.asyncio
    async def test_capacity_evicts_oldest_not_newest(self):
        """The oldest exchange must be dropped, not the newest."""
        mem = ConversationMemory(session_id="evict", redis_client=None)
        for i in range(MAX_EXCHANGES + 1):
            await mem.append(f"user-{i}", f"agent-{i}")

        ctx = await mem.get_context_string()
        # The very first exchange (user-0 / agent-0) must be gone
        assert "user-0" not in ctx
        assert "agent-0" not in ctx
        # The most recent must be present
        assert f"user-{MAX_EXCHANGES}" in ctx

    @pytest.mark.asyncio
    async def test_clear_wipes_all_exchanges(self):
        mem = ConversationMemory(session_id="clr", redis_client=None)
        await mem.append("q", "a")
        await mem.clear()

        assert mem.exchange_count == 0
        assert await mem.get_context_string() == ""

    @pytest.mark.asyncio
    async def test_exchange_count_starts_at_zero(self):
        mem = ConversationMemory(session_id="cnt", redis_client=None)
        assert mem.exchange_count == 0

    @pytest.mark.asyncio
    async def test_exchange_count_increments(self):
        mem = ConversationMemory(session_id="cnt2", redis_client=None)
        await mem.append("q1", "a1")
        await mem.append("q2", "a2")
        assert mem.exchange_count == 2

    @pytest.mark.asyncio
    async def test_sessions_are_isolated(self):
        """Two sessions with different IDs must not share memory."""
        m1 = ConversationMemory(session_id="alice", redis_client=None)
        m2 = ConversationMemory(session_id="bob", redis_client=None)

        await m1.append("alice-q", "alice-a")
        await m2.append("bob-q", "bob-a")

        ctx1 = await m1.get_context_string()
        ctx2 = await m2.get_context_string()

        assert "alice-q" in ctx1
        assert "bob-q" not in ctx1
        assert "bob-q" in ctx2
        assert "alice-q" not in ctx2


# ---------------------------------------------------------------------------
# Context string format
# ---------------------------------------------------------------------------

class TestContextStringFormat:
    """The context string must be parseable and structured for the LLM."""

    @pytest.mark.asyncio
    async def test_turns_are_numbered(self):
        mem = ConversationMemory(session_id="fmt", redis_client=None)
        await mem.append("q1", "a1")
        await mem.append("q2", "a2")

        ctx = await mem.get_context_string()
        assert "Turn 1:" in ctx
        assert "Turn 2:" in ctx

    @pytest.mark.asyncio
    async def test_user_and_flowlens_labels_present(self):
        mem = ConversationMemory(session_id="lbl", redis_client=None)
        await mem.append("hello", "hi there")

        ctx = await mem.get_context_string()
        assert "User:" in ctx
        assert "FlowLens:" in ctx

    @pytest.mark.asyncio
    async def test_context_is_string_not_bytes(self):
        mem = ConversationMemory(session_id="type", redis_client=None)
        await mem.append("q", "a")
        result = await mem.get_context_string()
        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_empty_memory_is_empty_string_not_whitespace(self):
        mem = ConversationMemory(session_id="ws", redis_client=None)
        ctx = await mem.get_context_string()
        assert ctx == ""


# ---------------------------------------------------------------------------
# Redis persistence
# ---------------------------------------------------------------------------

class TestMemoryWithRedis:
    """Memory loaded from Redis must be identical to what was saved."""

    @pytest.mark.asyncio
    async def test_save_writes_to_redis(self, mock_redis):
        mem = ConversationMemory(session_id="persist1", redis_client=mock_redis)
        await mem.append("saved-q", "saved-a")

        key = f"flowlens:memory:persist1"
        assert key in mock_redis._store

    @pytest.mark.asyncio
    async def test_save_uses_correct_ttl(self, mock_redis):
        mem = ConversationMemory(session_id="ttl1", redis_client=mock_redis)
        await mem.append("q", "a")

        key = f"flowlens:memory:ttl1"
        assert mock_redis._expiries.get(key) == TTL_SECONDS  # must match the constant

    @pytest.mark.asyncio
    async def test_load_restores_saved_exchanges(self, mock_redis):
        session_id = "round-trip"
        key = f"flowlens:memory:{session_id}"

        # Pre-populate Redis with serialised exchange
        data = [{"user": "pre-q", "agent": "pre-a", "ts": 1000.0}]
        mock_redis._store[key] = json.dumps(data).encode()

        mem = ConversationMemory(session_id=session_id, redis_client=mock_redis)
        await mem.load()

        assert mem.exchange_count == 1
        ctx = await mem.get_context_string()
        assert "pre-q" in ctx
        assert "pre-a" in ctx

    @pytest.mark.asyncio
    async def test_load_with_empty_redis_starts_blank(self, mock_redis):
        mem = ConversationMemory(session_id="fresh", redis_client=mock_redis)
        await mem.load()
        assert mem.exchange_count == 0

    @pytest.mark.asyncio
    async def test_clear_deletes_redis_key(self, mock_redis):
        session_id = "del-test"
        key = f"flowlens:memory:{session_id}"
        mem = ConversationMemory(session_id=session_id, redis_client=mock_redis)
        await mem.append("q", "a")

        assert key in mock_redis._store
        await mem.clear()
        assert key not in mock_redis._store

    @pytest.mark.asyncio
    async def test_save_stores_valid_json(self, mock_redis):
        mem = ConversationMemory(session_id="json-check", redis_client=mock_redis)
        await mem.append("q", "a")

        key = "flowlens:memory:json-check"
        raw = mock_redis._store[key]
        parsed = json.loads(raw)  # must not raise
        assert isinstance(parsed, list)
        assert parsed[0]["user"] == "q"


# ---------------------------------------------------------------------------
# Redis failure — graceful degradation
# ---------------------------------------------------------------------------

class TestMemoryRedisFailure:
    """Redis errors must never crash the application \u2014 fall back silently."""

    @pytest.mark.asyncio
    async def test_load_failure_does_not_crash(self, broken_redis):
        mem = ConversationMemory(session_id="fails", redis_client=broken_redis)
        try:
            await mem.load()  # Redis raises ConnectionError
        except Exception as exc:
            pytest.fail(f"load() crashed on Redis failure: {exc}")

    @pytest.mark.asyncio
    async def test_save_failure_does_not_crash(self, broken_redis):
        mem = ConversationMemory(session_id="fail-save", redis_client=broken_redis)
        try:
            await mem.append("q", "a")  # triggers save internally
        except Exception as exc:
            pytest.fail(f"append() crashed on Redis failure: {exc}")

    @pytest.mark.asyncio
    async def test_clear_failure_does_not_crash(self, broken_redis):
        mem = ConversationMemory(session_id="fail-clear", redis_client=broken_redis)
        mem._exchanges = [{"user": "q", "agent": "a", "ts": 1.0}]
        try:
            await mem.clear()
        except Exception as exc:
            pytest.fail(f"clear() crashed on Redis failure: {exc}")

    @pytest.mark.asyncio
    async def test_in_memory_still_works_after_redis_failure(self, broken_redis):
        """Even if Redis is broken, the in-memory store must keep working."""
        mem = ConversationMemory(session_id="degraded", redis_client=broken_redis)
        await mem.append("q", "a")  # Redis write fails silently

        ctx = await mem.get_context_string()
        assert "q" in ctx  # in-memory data is NOT lost
        assert "a" in ctx
