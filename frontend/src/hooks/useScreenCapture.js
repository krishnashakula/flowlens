/**
 * useScreenCapture — getDisplayMedia wrapper for FlowLens.
 *
 * Captures screen at 1 FPS, converts each frame to JPEG (60% quality)
 * via Canvas, and exposes as base64 data URL.
 *
 * Exposes: { isCapturing, currentFrame, startCapture, stopCapture, error }
 */

import { useCallback, useEffect, useRef, useState } from "react";

const CAPTURE_FPS = 1;       // 1 frame per second
const JPEG_QUALITY = 0.6;    // 60% quality ~50–120KB
const MAX_WIDTH = 1280;
const MAX_HEIGHT = 720;

export function useScreenCapture() {
  const [isCapturing, setIsCapturing] = useState(false);
  const [currentFrame, setCurrentFrame] = useState(null);
  const [error, setError] = useState(null);

  const streamRef = useRef(null);
  const videoRef = useRef(null);
  const canvasRef = useRef(null);
  const intervalRef = useRef(null);
  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;

    // Create off-screen canvas once
    const canvas = document.createElement("canvas");
    canvasRef.current = canvas;

    // Create off-screen video element once
    const video = document.createElement("video");
    video.autoplay = true;
    video.muted = true;
    video.playsInline = true;
    videoRef.current = video;

    return () => {
      mountedRef.current = false;
      stopCapture();
    };
  }, []);

  // ---- start ----
  const startCapture = useCallback(async () => {
    setError(null);
    try {
      let stream;

      // In Electron 22+, getDisplayMedia() is intercepted by setDisplayMediaRequestHandler
      // in main.js which auto-selects the primary screen — no system picker shown.
      // In a regular browser, this shows the system screen-picker.
      stream = await navigator.mediaDevices.getDisplayMedia({
        video: {
          frameRate: { ideal: 1, max: 2 },
          width: { ideal: MAX_WIDTH },
          height: { ideal: MAX_HEIGHT },
        },
        audio: false,
      });

      streamRef.current = stream;
      const video = videoRef.current;
      video.srcObject = stream;
      await video.play();

      setIsCapturing(true);

      // Handle user stopping capture via browser UI
      stream.getVideoTracks()[0].onended = () => {
        if (mountedRef.current) stopCapture();
      };

      // Begin frame capture loop
      intervalRef.current = setInterval(() => captureFrame(), 1000 / CAPTURE_FPS);

    } catch (err) {
      const msg =
        err.name === "NotAllowedError"
          ? "Screen recording permission denied. Check System Preferences → Privacy → Screen Recording."
          : `Screen capture failed: ${err.message}`;
      setError(msg);
      console.error("[FlowLens Capture]", err);
    }
  }, []);

  // ---- stop ----
  const stopCapture = useCallback(() => {
    clearInterval(intervalRef.current);
    intervalRef.current = null;

    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;

    if (videoRef.current) {
      videoRef.current.srcObject = null;
    }

    setIsCapturing(false);
    setCurrentFrame(null);
  }, []);

  // ---- capture one frame ----
  const captureFrame = useCallback(() => {
    const video = videoRef.current;
    const canvas = canvasRef.current;
    if (!video || !canvas || video.readyState < 2) return;

    const vw = video.videoWidth;
    const vh = video.videoHeight;
    if (!vw || !vh) return;

    // Compute target dimensions (maintain aspect ratio)
    const scale = Math.min(MAX_WIDTH / vw, MAX_HEIGHT / vh, 1);
    canvas.width = Math.floor(vw * scale);
    canvas.height = Math.floor(vh * scale);

    const ctx = canvas.getContext("2d");
    ctx.drawImage(video, 0, 0, canvas.width, canvas.height);

    const dataUrl = canvas.toDataURL("image/jpeg", JPEG_QUALITY);
    // Strip "data:image/jpeg;base64," prefix → just base64
    const b64 = dataUrl.split(",")[1];
    if (mountedRef.current) setCurrentFrame(b64);
  }, []);

  return { isCapturing, currentFrame, startCapture, stopCapture, error };
}
