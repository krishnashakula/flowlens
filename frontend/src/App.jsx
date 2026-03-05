/**
 * FlowLens — Main React Component
 * Four states: IDLE → LISTENING → PROCESSING → SPEAKING
 */

import { useEffect, useRef, useState } from "react";
import { v4 as uuidv4 } from "uuid";
import StatusBar from "./components/StatusBar";
import ScreenPreview from "./components/ScreenPreview";
import VoiceIndicator from "./components/VoiceIndicator";
import { useWebSocket } from "./hooks/useWebSocket";
import { useScreenCapture } from "./hooks/useScreenCapture";

// Stable session id for this app session
const SESSION_ID = uuidv4();

// App states
const STATE = {
  IDLE: "IDLE",
  LISTENING: "LISTENING",
  PROCESSING: "PROCESSING",
  SPEAKING: "SPEAKING",
};

export default function App() {
  const [appState, setAppState] = useState(STATE.IDLE);
  const [transcript, setTranscript] = useState("");
  const [partialTranscript, setPartialTranscript] = useState("");
  const [lastLatency, setLastLatency] = useState(null);
  const [processingTimer, setProcessingTimer] = useState(0);
  const processingStart = useRef(null);
  const timerRef = useRef(null);
  const audioCtxRef = useRef(null);
  const audioQueueRef = useRef([]);
  const isPlayingRef = useRef(false);

  // Screen capture
  const { isCapturing, currentFrame, startCapture, stopCapture, error: captureError } =
    useScreenCapture();

  // WebSocket
  const { isConnected, send, latency } = useWebSocket({
    sessionId: SESSION_ID,
    onAudioChunk: (bytes) => enqueueAudio(bytes),
    onTranscript: (text, partial) => {
      if (partial) {
        setPartialTranscript(text);
      } else {
        setTranscript(text);
        setPartialTranscript("");
        setAppState(STATE.IDLE);
        if (processingStart.current) {
          setLastLatency(((Date.now() - processingStart.current) / 1000).toFixed(1));
        }
      }
    },
    onError: () => setAppState(STATE.IDLE),
  });

  // ---------- keyboard handling ----------
  useEffect(() => {
    const onKeyDown = (e) => {
      if (e.code === "Space" && !e.repeat && appState === STATE.IDLE) {
        e.preventDefault();
        if (!isCapturing) startCapture();
        setAppState(STATE.LISTENING);
        send({ type: "listening_start" });
        // Send the most recent known frame immediately so short holds
        // still provide screen context (don't wait for 1-FPS interval tick).
        if (currentFrame) send({ type: "frame", data: currentFrame });
      }
      if (e.code === "Escape") {
        setAppState(STATE.IDLE);
        send({ type: "cancel" });
        stopTimer();
      }
    };

    const onKeyUp = (e) => {
      if (e.code === "Space" && appState === STATE.LISTENING) {
        e.preventDefault();
        setAppState(STATE.PROCESSING);
        processingStart.current = Date.now();
        startTimer();
        send({ type: "audio_end" });
      }
    };

    window.addEventListener("keydown", onKeyDown);
    window.addEventListener("keyup", onKeyUp);
    return () => {
      window.removeEventListener("keydown", onKeyDown);
      window.removeEventListener("keyup", onKeyUp);
    };
  }, [appState, isCapturing]);

  // ---------- processing timer + safety timeout ----------
  const startTimer = () => {
    timerRef.current = setInterval(() => {
      setProcessingTimer((prev) => {
        // Auto-escape after 15s — prevents forever-stuck PROCESSING state
        if (prev >= 15.0) {
          setAppState(STATE.IDLE);
          return 0;
        }
        return prev + 0.1;
      });
    }, 100);
  };
  const stopTimer = () => {
    if (timerRef.current) clearInterval(timerRef.current);
    setProcessingTimer(0);
  };

  useEffect(() => {
    if (appState !== STATE.PROCESSING) stopTimer();
    if (appState === STATE.SPEAKING) stopTimer();
  }, [appState]);

  // ---------- audio playback ----------
  const enqueueAudio = (bytes) => {
    setAppState(STATE.SPEAKING);
    audioQueueRef.current.push(bytes);
    if (!isPlayingRef.current) playNext();
  };

  const playNext = async () => {
    if (audioQueueRef.current.length === 0) {
      isPlayingRef.current = false;
      return;
    }
    isPlayingRef.current = true;

    if (!audioCtxRef.current) {
      audioCtxRef.current = new AudioContext({ sampleRate: 24000 });
    }
    const ctx = audioCtxRef.current;
    const bytes = audioQueueRef.current.shift();

    try {
      const pcm = new Int16Array(bytes.buffer || bytes);
      const float32 = new Float32Array(pcm.length);
      for (let i = 0; i < pcm.length; i++) {
        float32[i] = pcm[i] / 32768;
      }
      const buffer = ctx.createBuffer(1, float32.length, 24000);
      buffer.copyToChannel(float32, 0);
      const source = ctx.createBufferSource();
      source.buffer = buffer;
      source.connect(ctx.destination);
      source.onended = playNext;
      source.start();
    } catch {
      playNext();
    }
  };

  // ---------- frame sending (1 FPS while LISTENING) ----------
  useEffect(() => {
    if (appState !== STATE.LISTENING || !currentFrame) return;
    send({ type: "frame", data: currentFrame });
  }, [currentFrame, appState]);

  // ---------- render ----------
  return (
    <div
      className="w-[380px] min-h-[100px] rounded-2xl bg-[#0f0f0f] border border-[#2a2a2a] shadow-2xl 
                 flex flex-col overflow-hidden select-none"
      style={{ WebkitAppRegion: "drag" }}
    >
      {/* Title bar */}
      <div className="flex items-center justify-between px-4 py-2 border-b border-[#1e1e1e]"
           style={{ WebkitAppRegion: "drag" }}>
        <span className="text-[#4285f4] font-semibold text-sm tracking-wide">FlowLens</span>
        <StatusBar isConnected={isConnected} latency={lastLatency} state={appState} />
      </div>

      {/* Main content area */}
      <div className="flex flex-col items-center px-4 py-4 gap-3" style={{ WebkitAppRegion: "no-drag" }}>

        {/* IDLE state */}
        {appState === STATE.IDLE && (
          <div className="flex flex-col items-center gap-3 w-full">
            <VoiceIndicator state={STATE.IDLE} />
            <p className="text-[#666] text-xs text-center">
              Hold <kbd className="bg-[#1e1e1e] text-[#aaa] px-1.5 py-0.5 rounded text-[10px] font-mono">Space</kbd> to talk
            </p>
            {transcript && (
              <div className="bg-[#1a1a1a] rounded-xl px-3 py-2 w-full">
                <p className="text-[#e0e0e0] text-xs leading-relaxed line-clamp-2">{transcript}</p>
              </div>
            )}
          </div>
        )}

        {/* LISTENING state */}
        {appState === STATE.LISTENING && (
          <div className="flex flex-col items-center gap-3 w-full">
            <VoiceIndicator state={STATE.LISTENING} />
            <ScreenPreview frame={currentFrame} />
            {lastLatency && (
              <p className="text-[#555] text-[10px]">Last: {lastLatency}s</p>
            )}
          </div>
        )}

        {/* PROCESSING state */}
        {appState === STATE.PROCESSING && (
          <div className="flex flex-col items-center gap-3 w-full">
            <div className="w-8 h-8 border-2 border-[#4285f4] border-t-transparent rounded-full animate-spin" />
            <p className="text-[#888] text-xs">Analyzing screen…</p>
            <p className="text-[#4285f4] text-lg font-mono tabular-nums">
              {processingTimer.toFixed(1)}s
            </p>
          </div>
        )}

        {/* SPEAKING state */}
        {appState === STATE.SPEAKING && (
          <div className="flex flex-col items-center gap-3 w-full">
            <VoiceIndicator state={STATE.SPEAKING} />
            {(partialTranscript || transcript) && (
              <div className="bg-[#1a1a1a] rounded-xl px-3 py-2 w-full">
                <p className="text-[#e0e0e0] text-xs leading-relaxed">
                  {partialTranscript || transcript}
                </p>
              </div>
            )}
          </div>
        )}

        {/* Capture error */}
        {captureError && (
          <p className="text-red-400 text-[10px] text-center px-2">{captureError}</p>
        )}
      </div>

      {/* Footer hint */}
      <div className="px-4 pb-3 text-center">
        <p className="text-[#333] text-[9px]">Esc to cancel · ⌘Q to quit</p>
      </div>
    </div>
  );
}
