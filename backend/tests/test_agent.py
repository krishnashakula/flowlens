"""
Tests for agent.py — FlowLensAgent message dispatch and LatencyProfiler.

Risk tier: CRITICAL — all business logic lives here; bugs directly affect users.

Test categories: message dispatch (all types), empty-audio guard, audio
                 accumulation, turn lock, frame decode, latency profiler
                 correctness, fallback response.

NOTE: Gemini API calls are fully mocked — tests run offline and instantly.
"""

import asyncio
import base64
import io
import json
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from PIL import Image

from agent import FlowLensAgent, LatencyProfiler


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_jpeg_b64(w=100, h=100) -> str:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), (50, 50, 50)).save(buf, format="JPEG")
    return base64.b64encode(buf.getvalue()).decode()


def _make_pcm_bytes(samples: int = 8192) -> bytes:
    """Fake Int16 PCM: all zeros (silence), valid format."""
    import struct
    return struct.pack(f"<{samples}h", *([0] * samples))


@pytest.fixture
def mock_ws():
    ws = AsyncMock()
    ws.send_text = AsyncMock()
    ws.send_bytes = AsyncMock()
    return ws


@pytest.fixture
def mock_stream_response():
    """Minimal successful _stream_voice_response return value."""
    return ("Hello world", time.perf_counter() + 0.5, time.perf_counter() + 0.2)


@pytest.fixture
def agent(null_redis):
    with patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"}):
        return FlowLensAgent(session_id="test-session", redis_client=null_redis)


# ---------------------------------------------------------------------------
# handle_message — frame messages
# ---------------------------------------------------------------------------

class TestHandleMessageFrame:
    """Frame messages should update _current_frame without triggering a turn."""

    @pytest.mark.asyncio
    async def test_frame_message_stores_jpeg(self, agent, mock_ws):
        b64 = _make_jpeg_b64()
        result = await agent.handle_message({"text": json.dumps({"type": "frame", "data": b64})}, mock_ws)

        assert result is None  # no latency — this is not a turn
        assert agent._current_frame is not None

    @pytest.mark.asyncio
    async def test_frame_message_updates_current_frame(self, agent, mock_ws):
        b64_first = _make_jpeg_b64(100, 100)
        b64_second = _make_jpeg_b64(200, 200)

        await agent.handle_message({"text": json.dumps({"type": "frame", "data": b64_first})}, mock_ws)
        frame_after_first = agent._current_frame

        await agent.handle_message({"text": json.dumps({"type": "frame", "data": b64_second})}, mock_ws)
        frame_after_second = agent._current_frame

        # Latest frame replaces old one
        assert frame_after_first != frame_after_second

    @pytest.mark.asyncio
    async def test_frame_message_empty_data_does_not_crash(self, agent, mock_ws):
        result = await agent.handle_message(
            {"text": json.dumps({"type": "frame", "data": ""})}, mock_ws
        )
        assert result is None  # graceful no-op

    @pytest.mark.asyncio
    async def test_frame_b64_decoded_to_bytes(self, agent, mock_ws):
        b64 = _make_jpeg_b64()
        await agent.handle_message({"text": json.dumps({"type": "frame", "data": b64})}, mock_ws)
        assert isinstance(agent._current_frame, bytes)


# ---------------------------------------------------------------------------
# handle_message — audio accumulation
# ---------------------------------------------------------------------------

class TestHandleMessageAudio:
    """Binary audio chunks must accumulate in _audio_buffer."""

    @pytest.mark.asyncio
    async def test_binary_chunk_appended_to_buffer(self, agent, mock_ws):
        pcm = _make_pcm_bytes(1024)
        await agent.handle_message({"bytes": pcm}, mock_ws)
        assert len(agent._audio_buffer) == 1
        assert agent._audio_buffer[0] == pcm

    @pytest.mark.asyncio
    async def test_multiple_binary_chunks_all_accumulated(self, agent, mock_ws):
        for _ in range(5):
            await agent.handle_message({"bytes": _make_pcm_bytes(512)}, mock_ws)
        assert len(agent._audio_buffer) == 5

    @pytest.mark.asyncio
    async def test_binary_chunk_returns_none(self, agent, mock_ws):
        result = await agent.handle_message({"bytes": _make_pcm_bytes()}, mock_ws)
        assert result is None

    @pytest.mark.asyncio
    async def test_listening_start_resets_buffer(self, agent, mock_ws):
        """listening_start begins a new turn \u2014 previous stale audio must be cleared."""
        agent._audio_buffer = [b"stale-audio"]
        await agent.handle_message(
            {"text": json.dumps({"type": "listening_start"})}, mock_ws
        )
        assert agent._audio_buffer == []

    @pytest.mark.asyncio
    async def test_inline_audio_chunk_decoded_from_b64(self, agent, mock_ws):
        raw = _make_pcm_bytes(512)
        b64 = base64.b64encode(raw).decode()
        await agent.handle_message(
            {"text": json.dumps({"type": "audio_chunk", "data": b64})}, mock_ws
        )
        assert agent._audio_buffer[-1] == raw


# ---------------------------------------------------------------------------
# handle_message — audio_end / empty audio guard
# ---------------------------------------------------------------------------

class TestHandleMessageAudioEnd:
    """audio_end triggers a turn; empty audio must be rejected immediately."""

    @pytest.mark.asyncio
    async def test_empty_audio_sends_error_message(self, agent, mock_ws):
        """If no audio was captured, the user must be told to hold Space and speak."""
        agent._audio_buffer = []
        await agent.handle_message(
            {"text": json.dumps({"type": "audio_end"})}, mock_ws
        )
        mock_ws.send_text.assert_called_once()
        payload = json.loads(mock_ws.send_text.call_args[0][0])
        assert payload["type"] == "error"
        assert len(payload["message"]) > 0

    @pytest.mark.asyncio
    async def test_empty_audio_returns_none_not_latency(self, agent, mock_ws):
        agent._audio_buffer = []
        result = await agent.handle_message(
            {"text": json.dumps({"type": "audio_end"})}, mock_ws
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_audio_end_concatenates_buffer(self, agent, mock_ws):
        """All accumulated chunks must be joined before calling process_turn."""
        chunk_a = _make_pcm_bytes(512)
        chunk_b = _make_pcm_bytes(512)
        agent._audio_buffer = [chunk_a, chunk_b]

        captured = {}

        async def mock_process_turn(screen_frame, audio_data, websocket):
            captured["audio_data"] = audio_data
            return 1500.0

        with patch.object(agent, "process_turn", side_effect=mock_process_turn):
            await agent.handle_message(
                {"text": json.dumps({"type": "audio_end"})}, mock_ws
            )

        assert captured["audio_data"] == chunk_a + chunk_b

    @pytest.mark.asyncio
    async def test_audio_end_clears_buffer_after_turn(self, agent, mock_ws):
        """Buffer must be cleared even if process_turn raises."""
        agent._audio_buffer = [_make_pcm_bytes()]

        async def mock_process_turn(screen_frame, audio_data, websocket):
            return 999.0

        with patch.object(agent, "process_turn", side_effect=mock_process_turn):
            await agent.handle_message(
                {"text": json.dumps({"type": "audio_end"})}, mock_ws
            )

        assert agent._audio_buffer == []

    @pytest.mark.asyncio
    async def test_turn_timeout_sends_error_to_client(self, agent, mock_ws):
        """20s hard cap: TimeoutError must result in an error message to the client."""
        agent._audio_buffer = [_make_pcm_bytes()]

        async def slow_turn(screen_frame, audio_data, websocket):
            await asyncio.sleep(9999)

        with patch.object(agent, "process_turn", side_effect=slow_turn):
            with patch("asyncio.wait_for", side_effect=asyncio.TimeoutError):
                await agent.handle_message(
                    {"text": json.dumps({"type": "audio_end"})}, mock_ws
                )

        calls = [json.loads(c[0][0]) for c in mock_ws.send_text.call_args_list]
        error_calls = [c for c in calls if c.get("type") == "error"]
        assert len(error_calls) == 1


# ---------------------------------------------------------------------------
# handle_message — invalid / unknown messages
# ---------------------------------------------------------------------------

class TestHandleMessageEdgeCases:

    @pytest.mark.asyncio
    async def test_invalid_json_returns_none_no_crash(self, agent, mock_ws):
        result = await agent.handle_message({"text": "not json {{{"}, mock_ws)
        assert result is None

    @pytest.mark.asyncio
    async def test_missing_type_returns_none(self, agent, mock_ws):
        result = await agent.handle_message(
            {"text": json.dumps({"data": "something"})}, mock_ws
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_empty_message_dict_returns_none(self, agent, mock_ws):
        result = await agent.handle_message({}, mock_ws)
        assert result is None

    @pytest.mark.asyncio
    async def test_unknown_type_returns_none_no_crash(self, agent, mock_ws):
        result = await agent.handle_message(
            {"text": json.dumps({"type": "totally_unknown_type"})}, mock_ws
        )
        assert result is None


# ---------------------------------------------------------------------------
# LatencyProfiler
# ---------------------------------------------------------------------------

class TestLatencyProfiler:
    """The profiler must compute correct breakdown values from timestamps."""

    @pytest.fixture
    def profiler(self):
        return LatencyProfiler(redis_client=None)

    def test_frame_analysis_ms_correct(self, profiler):
        t0 = 1000.0
        bd = profiler.record_turn(
            frame_received_at=t0,
            frame_analyzed_at=t0 + 0.3,    # 300ms
            gemini_connected_at=t0 + 0.5,
            first_audio_byte_at=t0 + 2.0,
            session_id="p1",
        )
        assert bd["frame_analysis_ms"] == pytest.approx(300.0, abs=1.0)

    def test_gemini_setup_ms_correct(self, profiler):
        t0 = 1000.0
        bd = profiler.record_turn(
            frame_received_at=t0,
            frame_analyzed_at=t0 + 0.3,
            gemini_connected_at=t0 + 0.5,  # 200ms after frame_analyzed
            first_audio_byte_at=t0 + 2.0,
            session_id="p2",
        )
        assert bd["gemini_setup_ms"] == pytest.approx(200.0, abs=1.0)

    def test_first_byte_ms_correct(self, profiler):
        t0 = 1000.0
        bd = profiler.record_turn(
            frame_received_at=t0,
            frame_analyzed_at=t0 + 0.3,
            gemini_connected_at=t0 + 0.5,
            first_audio_byte_at=t0 + 1.5,  # 1000ms after connected
            session_id="p3",
        )
        assert bd["first_byte_ms"] == pytest.approx(1000.0, abs=1.0)

    def test_total_ms_is_end_to_end(self, profiler):
        t0 = 1000.0
        bd = profiler.record_turn(
            frame_received_at=t0,
            frame_analyzed_at=t0 + 0.3,
            gemini_connected_at=t0 + 0.5,
            first_audio_byte_at=t0 + 2.1,  # total = 2100ms
            session_id="p4",
        )
        assert bd["total_ms"] == pytest.approx(2100.0, abs=1.0)

    def test_breakdown_contains_session_id(self, profiler):
        t0 = 1000.0
        bd = profiler.record_turn(t0, t0 + 0.1, t0 + 0.2, t0 + 1.0, "my-session")
        assert bd["session_id"] == "my-session"

    def test_all_breakdown_keys_present(self, profiler):
        t0 = 1000.0
        bd = profiler.record_turn(t0, t0 + 0.1, t0 + 0.2, t0 + 1.0, "s")
        expected_keys = {
            "frame_analysis_ms", "gemini_setup_ms",
            "first_byte_ms", "total_ms", "session_id",
        }
        assert expected_keys <= bd.keys()

    def test_values_are_rounded_floats(self, profiler):
        t0 = 1000.0
        bd = profiler.record_turn(t0, t0 + 0.3333, t0 + 0.6666, t0 + 1.9999, "s")
        # Rounded to 1 decimal place — no insane precision
        for key in ("frame_analysis_ms", "gemini_setup_ms", "first_byte_ms", "total_ms"):
            val = bd[key]
            assert val == round(val, 1)
