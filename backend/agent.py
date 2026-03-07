"""
FlowLens — Core Agent Engine
Integrates Gemini Live API (voice) + gemini-2.0-flash (vision).
Latency target: p50 < 2500ms, p95 < 3000ms end-to-end.
"""

import asyncio
import base64
import json
import os
import time
from pathlib import Path
from typing import AsyncIterator, Optional

from dotenv import load_dotenv
load_dotenv(dotenv_path=Path(__file__).parent.parent / ".env", override=False)

from google import genai
from google.genai import types as genai_types
import structlog
from fastapi import WebSocket

from memory import ConversationMemory
from screen import compress_frame

log = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# System prompt — used verbatim for all Gemini calls
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are FlowLens, an AI productivity assistant with real-time visibility \
into the user's screen. You communicate exclusively by voice.

## Core Behaviour
- Answer in 1-2 sentences unless the user explicitly asks for more detail.
- Use plain, natural spoken language — no markdown, bullet points, or code \
  blocks in responses (you are speaking, not writing).
- Never narrate your reasoning or thinking aloud. Deliver the answer directly.
- Do not start responses with filler phrases like "Sure!", "Great question!", \
  "Of course!", "Certainly!", or "I can see that...".

## Grounding Rules (Critical)
- You receive a structured screen description under "Current screen:". \
  ONLY reference facts explicitly stated there. If something is not in the \
  screen description, it does not exist — do not infer, guess, or fabricate.
- If no screen context is provided, answer from general knowledge without \
  mentioning screen visibility at all — never say you cannot see the screen.
- If the screen description is ambiguous, ask one short clarifying question.

## Conversation Continuity
- Use "Conversation history:" to maintain context across turns.
- If the user asks a follow-up (e.g. "why?", "how do I fix that?"), answer \
  in reference to the previous turn — do not re-explain from scratch.
- Track what you have already said; do not repeat the same information.

## Accuracy Standards
- For code on screen: quote exact identifiers, function names, and line \
  context from the screen description. Never invent variable names or APIs.
- For errors or exceptions: identify the exact error type and message shown. \
  Suggest the most likely fix based only on what is visible.
- For UI / design: describe precisely what element or state is shown before \
  giving feedback.

## Tone
- Calm, confident, and efficient. Treat the user as a competent professional.
- Be direct. Brevity is a feature, not rudeness."""


# ---------------------------------------------------------------------------
# Latency Profiler
# ---------------------------------------------------------------------------


class LatencyProfiler:
    """
    Tracks per-turn latency breakdown.
    Logs structured events to Cloud Logging / stdout.
    Updates running stats in Redis when available.
    """

    def __init__(self, redis_client):
        self._redis = redis_client

    def record_turn(
        self,
        frame_received_at: float,
        frame_analyzed_at: float,
        gemini_connected_at: float,
        first_audio_byte_at: float,
        session_id: str,
    ) -> dict:
        breakdown = {
            "frame_analysis_ms": round((frame_analyzed_at - frame_received_at) * 1000, 1),
            "gemini_setup_ms": round((gemini_connected_at - frame_analyzed_at) * 1000, 1),
            "first_byte_ms": round((first_audio_byte_at - gemini_connected_at) * 1000, 1),
            "total_ms": round((first_audio_byte_at - frame_received_at) * 1000, 1),
            "session_id": session_id,
        }

        log.info("turn_latency", **breakdown)

        if breakdown["total_ms"] > 3000:
            log.warning(
                "latency_exceeded_target",
                total_ms=breakdown["total_ms"],
                session_id=session_id,
            )

        # Persist to Redis asynchronously (fire-and-forget via task)
        if self._redis:
            asyncio.create_task(self._push_to_redis(breakdown))

        return breakdown

    async def _push_to_redis(self, breakdown: dict):
        try:
            pipe = self._redis.pipeline()
            key = "flowlens:latency_samples"
            pipe.lpush(key, json.dumps(breakdown))
            pipe.ltrim(key, 0, 999)  # keep last 1000
            await pipe.execute()
        except Exception as exc:
            log.warning("redis_latency_write_failed", error=str(exc))


# ---------------------------------------------------------------------------
# FlowLens Agent
# ---------------------------------------------------------------------------


class FlowLensAgent:
    """
    Core agent: accepts screen frames + audio, returns voice response.
    Latency target: <3000ms from first input to first audio output byte.

    Lifecycle:
      1. __init__     — instantiate (no I/O)
      2. warm_up()    — start Gemini Live connection proactively
      3. handle_message() — process one incoming WS message
      4. shutdown()   — clean up connections, persist memory
    """

    def __init__(self, session_id: str, redis_client):
        self.session_id = session_id
        self._redis = redis_client
        self._memory = ConversationMemory(session_id=session_id, redis_client=redis_client)
        self._profiler = LatencyProfiler(redis_client=redis_client)

        api_key = os.environ.get("GEMINI_API_KEY", "")
        if not api_key:
            raise ValueError(
                "GEMINI_API_KEY is not set. Set it in .env or as an environment variable."
            )

        # Vision client — default API version (v1beta)
        self._client = genai.Client(api_key=api_key)

        # Live API client — must use v1alpha; gemini-2.0-flash-live-001 is not
        # available on v1beta which became the SDK default in genai >=1.5.0
        self._live_client = genai.Client(
            api_key=api_key,
            http_options=genai_types.HttpOptions(api_version="v1alpha"),
        )

        # Model names — allow override via env vars for easy experimentation
        self._vision_model_name = os.environ.get(
            "VISION_MODEL", "gemini-2.5-flash"
        )
        self._live_model_name = os.environ.get(
            "LIVE_MODEL", "gemini-2.5-flash-native-audio-latest"
        )

        # Accumulated state for the current turn
        self._current_frame: Optional[bytes] = None
        self._audio_buffer: list[bytes] = []

        # Turn lock — prevents overlapping turns
        self._turn_lock = asyncio.Lock()

        log.info("agent_created", session_id=session_id)

    # -----------------------------------------------------------------------
    # Warm-up — called immediately after WS connect
    # -----------------------------------------------------------------------

    async def warm_up(self):
        """
        Pre-load conversation memory from Redis.
        The Gemini Live connection itself is opened per-turn (stateless API).
        """
        await self._memory.load()
        log.info("agent_warmed_up", session_id=self.session_id)

    # -----------------------------------------------------------------------
    # Message dispatch
    # -----------------------------------------------------------------------

    async def handle_message(self, raw_message: dict, websocket: WebSocket) -> Optional[float]:
        """
        Dispatch an incoming WebSocket message.
        Returns latency_ms for the turn, or None if not a turn-completing message.
        """
        if "bytes" in raw_message:
            # Raw audio bytes (PCM 16kHz mono) — accumulate
            self._audio_buffer.append(raw_message["bytes"])
            return None

        if "text" not in raw_message:
            return None

        try:
            envelope = json.loads(raw_message["text"])
        except json.JSONDecodeError:
            log.warning("invalid_json", raw=raw_message.get("text", "")[:100])
            return None

        msg_type = envelope.get("type")

        if msg_type == "frame":
            # Screen frame — store latest, don't trigger turn yet
            frame_b64 = envelope.get("data", "")
            if frame_b64:
                self._current_frame = base64.b64decode(frame_b64)
            return None

        if msg_type == "listening_start":
            # Client signals start of a new listening session \u2014 reset buffer
            self._audio_buffer = []
            return None

        if msg_type == "audio_end":
            # User released space bar \u2014 process the complete turn
            audio_data = b"".join(self._audio_buffer)
            self._audio_buffer = []
            if not audio_data:
                log.warning("audio_end_empty", session_id=self.session_id)
                await websocket.send_text(
                    json.dumps({"type": "error", "message": "No audio received. Hold Space and speak."})
                )
                return None
            async with self._turn_lock:
                try:
                    return await asyncio.wait_for(
                        self.process_turn(
                            screen_frame=self._current_frame,
                            audio_data=audio_data,
                            websocket=websocket,
                        ),
                        timeout=20.0,  # hard cap — never hang forever
                    )
                except asyncio.TimeoutError:
                    log.error("turn_timeout", session_id=self.session_id)
                    await websocket.send_text(
                        json.dumps({"type": "error", "message": "Request timed out, please try again."})
                    )
            return None

        if msg_type == "audio_chunk":
            # Inline audio chunk (base64-encoded in JSON)
            chunk_b64 = envelope.get("data", "")
            if chunk_b64:
                self._audio_buffer.append(base64.b64decode(chunk_b64))
            return None

        log.debug("unhandled_message_type", msg_type=msg_type)
        return None

    # -----------------------------------------------------------------------
    # Core turn processing
    # -----------------------------------------------------------------------

    async def process_turn(
        self,
        screen_frame: Optional[bytes],
        audio_data: bytes,
        websocket: WebSocket,
    ) -> float:
        """
        Full turn: screen frame + audio → voice response streamed back.
        Returns measured latency_ms.

        Architecture: the JPEG frame is sent directly into the Gemini Live
        session as a realtime video input so the model sees the screen AND
        hears the audio simultaneously.  No separate vision pre-processing
        step — eliminates the timeout that was causing blank screen context.
        """
        t_received = time.perf_counter()
        log.info("turn_start", session_id=self.session_id, audio_bytes=len(audio_data))

        # Compress frame if present
        compressed_frame: Optional[bytes] = None
        if screen_frame:
            try:
                compressed_frame = compress_frame(screen_frame)
                log.debug("frame_compressed", bytes=len(compressed_frame))
            except Exception as exc:
                log.warning("frame_compress_failed", error=str(exc))

        # Memory load is fast (in-memory / Redis)
        memory_context = await self._memory.get_context_string()
        t_frame_analyzed = time.perf_counter()  # no separate vision call

        # Build system context (no frame_description — model sees raw frame)
        context = self._build_context(memory_context)

        # Call Gemini Live: frame + audio sent together inside the session
        transcript, user_transcript, t_first_byte, t_gemini_connected = await self._stream_voice_response(
            context=context,
            audio_data=audio_data,
            screen_frame=compressed_frame,
            websocket=websocket,
        )

        # Record latency
        breakdown = self._profiler.record_turn(
            frame_received_at=t_received,
            frame_analyzed_at=t_frame_analyzed,
            gemini_connected_at=t_gemini_connected,
            first_audio_byte_at=t_first_byte,
            session_id=self.session_id,
        )

        # Update conversation memory with real transcripts when available
        has_screen = compressed_frame is not None
        screen_tag = "[screen shared] " if has_screen else ""
        user_summary = user_transcript if user_transcript else f"{screen_tag}[audio query]"
        await self._memory.append(user_turn=user_summary, agent_turn=transcript)

        return breakdown["total_ms"]

    # -----------------------------------------------------------------------
    # Context builder
    # -----------------------------------------------------------------------

    def _build_context(self, memory_context: str) -> str:
        parts = [SYSTEM_PROMPT]
        if memory_context:
            parts.append(f"\nConversation history:\n{memory_context}")
        return "\n".join(parts)

    # -----------------------------------------------------------------------
    # Gemini Live API — voice streaming
    # -----------------------------------------------------------------------

    async def _stream_voice_response(
        self,
        context: str,
        audio_data: bytes,
        screen_frame: Optional[bytes],
        websocket: WebSocket,
    ) -> tuple[str, str, float, float]:
        """
        Call Gemini Live API.
        Sends the screen JPEG frame + PCM audio as realtime inputs so the
        model can see and hear simultaneously.
        Streams audio bytes back to the WebSocket.
        Returns (agent_transcript, user_transcript, t_first_byte, t_gemini_connected).
        """
        t_gemini_connected = time.perf_counter()
        transcript_parts: list[str] = []
        user_transcript_parts: list[str] = []
        t_first_byte = t_gemini_connected  # updated when first audio byte sent

        live_config = genai_types.LiveConnectConfig(
            # Native-audio models only support AUDIO modality (no TEXT);
            # SpeechConfig/VoiceConfig are not supported on these models.
            response_modalities=["AUDIO"],
            system_instruction=context,
            # Enable transcription so we still get text transcript of the response
            output_audio_transcription=genai_types.AudioTranscriptionConfig(),
            # Disable thinking — gemini-2.5 models think by default which adds
            # 5-10s of CoT latency before the first audio byte. For a voice
            # assistant < 3s total latency is the target.
            thinking_config=genai_types.ThinkingConfig(thinking_budget=0),
        )

        try:
            async with self._live_client.aio.live.connect(
                model=self._live_model_name,
                config=live_config,
            ) as session:
                t_gemini_connected = time.perf_counter()

                # Send screen frame first so the model has visual context
                # before it hears the audio question.
                if screen_frame:
                    await session.send_realtime_input(
                        video=genai_types.Blob(
                            data=screen_frame,
                            mime_type="image/jpeg",
                        )
                    )
                    log.debug("frame_sent_to_live", bytes=len(screen_frame))

                # Send raw PCM chunks (Int16, 16kHz mono)
                CHUNK = 4096 * 2  # 4096 Int16 samples = one ScriptProcessor buffer
                for i in range(0, len(audio_data), CHUNK):
                    chunk = audio_data[i : i + CHUNK]
                    await session.send_realtime_input(
                        audio=genai_types.Blob(
                            data=chunk,
                            mime_type="audio/pcm;rate=16000",
                        )
                    )

                # Signal end of audio turn
                await session.send_realtime_input(audio_stream_end=True)

                first_byte_sent = False
                async for response in session.receive():
                    # Audio bytes — comes via response.data for native-audio models
                    audio_bytes = response.data
                    if audio_bytes:
                        if not first_byte_sent:
                            t_first_byte = time.perf_counter()
                            first_byte_sent = True
                        await websocket.send_bytes(audio_bytes)

                    # Text transcript — native-audio models return transcript via
                    # server_content.output_transcription.text (not response.text)
                    sc = response.server_content
                    if sc:
                        # Capture what the user said (input transcription)
                        if sc.input_transcription and sc.input_transcription.text:
                            user_transcript_parts.append(sc.input_transcription.text)

                        if sc.output_transcription and sc.output_transcription.text:
                            text_chunk = sc.output_transcription.text
                            transcript_parts.append(text_chunk)
                            await websocket.send_text(
                                json.dumps(
                                    {"type": "transcript", "text": text_chunk, "partial": True}
                                )
                            )
                        # Also catch plain .text for non-native models (fallback)
                        elif response.text:
                            transcript_parts.append(response.text)
                            await websocket.send_text(
                                json.dumps(
                                    {"type": "transcript", "text": response.text, "partial": True}
                                )
                            )

                        if sc.turn_complete:
                            break

                    # Safety: if first audio has been received but nothing new
                    # for 8s, assume turn is done (server forgot to send turn_complete)
                    if first_byte_sent and not audio_bytes and not (
                        sc and sc.output_transcription and sc.output_transcription.text
                    ):
                        elapsed = time.perf_counter() - t_first_byte
                        if elapsed > 8.0:
                            log.warning("receive_loop_timeout_fallback", session_id=self.session_id)
                            break

        except asyncio.TimeoutError:
            log.error("live_api_timeout", session_id=self.session_id)
            fallback = await self._generate_fallback_response(context, websocket)
            return fallback, "", time.perf_counter(), t_gemini_connected
        except Exception as exc:
            log.error("live_api_error", error=str(exc), session_id=self.session_id)
            await websocket.send_text(
                json.dumps({"type": "error", "message": "Voice response failed, please retry."})
            )

        transcript = " ".join(transcript_parts).strip()
        user_transcript = " ".join(user_transcript_parts).strip()
        if transcript:
            await websocket.send_text(
                json.dumps({"type": "transcript", "text": transcript, "partial": False})
            )

        return transcript, user_transcript, t_first_byte, t_gemini_connected

    # -----------------------------------------------------------------------
    # Fallback voice response (text-to-speech via TTS endpoint)
    # -----------------------------------------------------------------------

    async def _generate_fallback_response(
        self, context: str, websocket: WebSocket
    ) -> str:
        """Return a text-only fallback when Live API times out."""
        fallback_text = "Sorry, I had trouble processing that. Could you try again?"
        await websocket.send_text(
            json.dumps({"type": "transcript", "text": fallback_text, "partial": False})
        )
        return fallback_text

    # -----------------------------------------------------------------------
    # Shutdown
    # -----------------------------------------------------------------------

    async def shutdown(self):
        """Persist memory; called on WebSocket disconnect."""
        try:
            await self._memory.save()
            log.info("memory_saved", session_id=self.session_id)
        except Exception as exc:
            log.warning("memory_save_failed", error=str(exc))
