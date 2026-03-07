/**
 * useWebSocket — WebSocket connection manager for FlowLens.
 *
 * Features:
 *  - Auto-connect on mount to ws://localhost:8000/ws/{sessionId}
 *  - Reconnect with exponential backoff (1s → 2s → 4s → … → 30s max)
 *  - 1 FPS screen frame sending while in LISTENING state
 *  - PCM audio chunk streaming while space bar held
 *  - Incoming audio bytes → onAudioChunk callback (played immediately)
 *  - Incoming transcript text → onTranscript callback
 *
 * Exposes: { isConnected, send, latency }
 */

import { useCallback, useEffect, useRef, useState } from "react";

const BACKEND_WS =
  import.meta.env.VITE_WS_URL || "ws://localhost:8000";

const MIN_BACKOFF_MS = 1000;
const MAX_BACKOFF_MS = 30_000;

export function useWebSocket({ sessionId, onAudioChunk, onTranscript, onError }) {
  const [isConnected, setIsConnected] = useState(false);
  const [latency, setLatency] = useState(null);

  const wsRef = useRef(null);
  const backoffRef = useRef(MIN_BACKOFF_MS);
  const reconnectTimer = useRef(null);
  const mountedRef = useRef(true);
  const micStreamRef = useRef(null);

  // ---- connect ----
  const connect = useCallback(() => {
    if (!mountedRef.current) return;

    const url = `${BACKEND_WS}/ws/${sessionId}`;
    const ws = new WebSocket(url);
    ws.binaryType = "arraybuffer";
    wsRef.current = ws;

    ws.onopen = () => {
      if (!mountedRef.current) { ws.close(); return; }
      setIsConnected(true);
      backoffRef.current = MIN_BACKOFF_MS;
      console.info("[FlowLens WS] connected", url);
    };

    ws.onmessage = (event) => {
      if (!mountedRef.current) return;

      // Binary → audio bytes
      if (event.data instanceof ArrayBuffer) {
        onAudioChunk?.(new Uint8Array(event.data));
        return;
      }

      // Text → JSON envelope
      try {
        const msg = JSON.parse(event.data);
        if (msg.type === "transcript") {
          onTranscript?.(msg.text, msg.partial ?? false);
        } else if (msg.type === "latency") {
          setLatency(msg.ms);
        } else if (msg.type === "error") {
          console.error("[FlowLens WS] server error:", msg.message);
          onError?.(msg.message);
        }
      } catch (e) {
        console.warn("[FlowLens WS] unparseable message", event.data);
      }
    };

    ws.onclose = (event) => {
      setIsConnected(false);
      if (!mountedRef.current) return;
      console.info(`[FlowLens WS] closed (${event.code}), reconnecting in ${backoffRef.current}ms`);
      reconnectTimer.current = setTimeout(() => {
        backoffRef.current = Math.min(backoffRef.current * 2, MAX_BACKOFF_MS);
        connect();
      }, backoffRef.current);
    };

    ws.onerror = (err) => {
      console.error("[FlowLens WS] error", err);
      ws.close(); // triggers onclose → reconnect
    };
  }, [sessionId]);

  // ---- mount / unmount ----
  useEffect(() => {
    mountedRef.current = true;
    connect();
    return () => {
      mountedRef.current = false;
      clearTimeout(reconnectTimer.current);
      wsRef.current?.close(1000, "unmount");
      // Stop microphone if still active (e.g. user closes window while recording)
      stopMic();
    };
  }, [connect, stopMic]);

  // ---- send ----
  const send = useCallback((payload) => {
    const ws = wsRef.current;
    if (!ws || ws.readyState !== WebSocket.OPEN) return;

    // audio_end must NOT be sent immediately — stop the mic first so the
    // final ondataavailable chunk is flushed before the backend sees audio_end
    if (payload?.type === "audio_end") {
      stopMic(ws, () => {
        if (ws.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({ type: "audio_end" }));
        }
      });
      return;
    }

    if (payload instanceof ArrayBuffer || ArrayBuffer.isView(payload)) {
      ws.send(payload);
    } else {
      ws.send(JSON.stringify(payload));
    }

    // Handle mic start/stop based on message type
    if (payload?.type === "listening_start") {
      startMic(ws);
    } else if (payload?.type === "cancel") {
      stopMic(ws);
    }
  }, []);

  // ---- microphone streaming ----
  // Uses AudioWorkletNode (modern API) to capture raw PCM Int16 @ 16kHz.
  // The processor runs in a dedicated audio thread for lower latency.
  const audioCtxMicRef = useRef(null);
  const audioWorkletNodeRef = useRef(null);

  // Inline AudioWorklet processor — avoids needing a separate static file.
  const WORKLET_CODE = `
class PCMProcessor extends AudioWorkletProcessor {
  process(inputs) {
    const ch = inputs[0]?.[0];
    if (!ch) return true;
    const int16 = new Int16Array(ch.length);
    for (let i = 0; i < ch.length; i++) {
      const s = Math.max(-1, Math.min(1, ch[i]));
      int16[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
    }
    this.port.postMessage(int16.buffer, [int16.buffer]);
    return true;
  }
}
registerProcessor('pcm-processor', PCMProcessor);
`;

  const startMic = useCallback(async (ws) => {
    // Guard against double-invocation while mic is already active
    if (audioCtxMicRef.current) {
      log.debug?.("[FlowLens WS] startMic called while already active — skipping");
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,
          sampleRate: 16000,
          echoCancellation: true,
          noiseSuppression: true,
        },
      });
      micStreamRef.current = stream;

      const ctx = new AudioContext({ sampleRate: 16000 });
      audioCtxMicRef.current = ctx;

      // Load the processor via an inline Blob URL — no separate static file needed.
      const blob = new Blob([WORKLET_CODE], { type: "application/javascript" });
      const blobUrl = URL.createObjectURL(blob);
      try {
        await ctx.audioWorklet.addModule(blobUrl);
      } finally {
        // Always revoke the Blob URL to prevent memory leaks, even on error
        URL.revokeObjectURL(blobUrl);
      }

      const source = ctx.createMediaStreamSource(stream);
      const workletNode = new AudioWorkletNode(ctx, "pcm-processor");
      audioWorkletNodeRef.current = workletNode;

      workletNode.port.onmessage = (e) => {
        if (ws.readyState === WebSocket.OPEN) {
          ws.send(e.data);
        }
      };

      // Connect source → worklet ONLY — do NOT connect worklet to destination
      // (connecting to destination would play mic audio through the speakers = echo)
      source.connect(workletNode);
    } catch (err) {
      console.error("[FlowLens WS] mic access denied:", err);
    }
  }, []);

  const stopMic = useCallback(async (ws, onDone) => {
    audioWorkletNodeRef.current?.disconnect();
    audioWorkletNodeRef.current = null;

    // Await close so the AudioContext flushes pending PCM before we send audio_end
    if (audioCtxMicRef.current) {
      try {
        await audioCtxMicRef.current.close();
      } catch (_) {
        // ignore — already closed
      }
      audioCtxMicRef.current = null;
    }

    micStreamRef.current?.getTracks().forEach((t) => t.stop());
    micStreamRef.current = null;

    onDone?.();
  }, []);

  return { isConnected, send, latency };
}
