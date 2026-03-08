<div align="center">

<img src="docs/architecture.svg" alt="FlowLens" width="72" />

# FlowLens

### Real-Time Voice + Vision AI Agent for Your Screen

[![Cloud Run](https://img.shields.io/badge/Cloud%20Run-deployed-4285F4?logo=google-cloud&logoColor=white)](https://flowlens-backend-rxwer3bgva-uk.a.run.app)
[![Gemini Live API](https://img.shields.io/badge/Gemini%202.5%20Flash-Live%20API-34A853?logo=google&logoColor=white)](https://ai.google.dev)
[![Python](https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=white)](https://python.org)
[![Electron](https://img.shields.io/badge/Electron-33-47848F?logo=electron&logoColor=white)](https://electronjs.org)
[![React](https://img.shields.io/badge/React-18-61DAFB?logo=react&logoColor=black)](https://react.dev)
[![License](https://img.shields.io/badge/license-MIT-22c55e)](LICENSE)
[![Hackathon](https://img.shields.io/badge/Gemini%20Live%20Agent%20Challenge-2026-FBBC04)](https://geminiliveagentchallenge.devpost.com)

<br/>

**Hold a button. Ask anything about your screen. Get a spoken answer in under 2 seconds.**

No copy-paste. No tab-switching. No typing.

<br/>

[**ðŸš€ Live Demo**](https://flowlens-backend-rxwer3bgva-uk.a.run.app) Â· [**ðŸ“– How It Works**](#architecture) Â· [**âš¡ Quick Start**](#quick-start) Â· [**ðŸ§  Gemini Live API**](#gemini-live-api-integration)

</div>

---

## The Problem

Every time a developer hits a visual bug, a designer needs a critique, or someone stares at an unfamiliar error â€” the workflow is the same painful loop:

```
ðŸ“¸ Screenshot  â†’  ðŸ”€ Alt-Tab  â†’  ðŸ“‹ Paste  â†’  âŒ¨ï¸ Describe  â†’  â³ Wait  â†’  ðŸ“– Read
                                                                    â†‘
                                                              ~34 seconds
```

**FlowLens collapses that to 2 seconds.**

---

## What Is FlowLens?

FlowLens is an **always-on-top desktop overlay** (Electron + React) that:

- ðŸ‘ï¸ **Sees your screen** â€” captures 1 FPS JPEG frames via `getDisplayMedia()`
- ðŸŽ™ï¸ **Hears your voice** â€” streams raw PCM at 16 kHz via AudioWorklet
- ðŸ§  **Runs Gemini 2.5 Flash** â€” via the Live API's bidirectional `bidiGenerateContent` stream
- ðŸ”Š **Speaks back** â€” native audio response directly to your speakers
- ðŸ’¾ **Remembers context** â€” Redis-backed rolling window of the last 10 turns

```
You: "Why is this CSS layout broken?"
FlowLens: [sees your screen] "The flex container is missing align-items:
           center. The child div has an explicit height that's overflowing."
          [2.1s total latency]
```

Built for the [Gemini Live Agent Challenge](https://geminiliveagentchallenge.devpost.com/) Â· Powered by Gemini Live API Â· Deployed on Google Cloud Run

---

## Quick Start

### Option A â€” Use Cloud Run backend *(no Python needed)*

```bash
git clone https://github.com/krishnashakula/flowlens
cd flowlens/frontend

# Point at the live Cloud Run backend
echo "VITE_WS_URL=wss://flowlens-backend-rxwer3bgva-uk.a.run.app" > .env

npm install
npx vite &        # Vite dev server on :5173
npx electron .    # Launch the overlay
```

### Option B â€” Run everything locally

```bash
# 1. Clone
git clone https://github.com/krishnashakula/flowlens
cd flowlens

# 2. Backend
cd backend
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt
set GEMINI_API_KEY=your_key
uvicorn main:app --port 8000

# 3. Frontend (new terminal)
cd frontend
npm install
npx vite &
npx electron .
```

### Controls

| Key / Action | Effect |
|---|---|
| **Hold "Hold to Talk" button** | Stream voice â†’ Gemini â†’ hear response |
| `Space` (widget focused) | Same as button |
| `Alt + S` | Capture screen + send frame |
| `Esc` | Cancel current query |
| `Ctrl + Shift + I` | Open DevTools |

---

## Architecture

```
â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
â”‚  Electron Desktop  (React 18 + Vite 6)                           â”‚
â”‚                                                                    â”‚
â”‚  â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”    â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â” â”‚
â”‚  â”‚  getDisplayMedia  â”‚    â”‚  AudioWorkletNode (pcm-processor)   â”‚ â”‚
â”‚  â”‚  1 FPS @ 720p     â”‚    â”‚  Int16 PCM @ 16 kHz                 â”‚ â”‚
â”‚  â”‚  JPEG 60%, ~80KB  â”‚    â”‚  128-sample callbacks               â”‚ â”‚
â”‚  â””â”€â”€â”€â”€â”€â”€â”€â”€â”¬â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜    â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”¬â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜ â”‚
â”‚           â”‚  base64                        â”‚  ArrayBuffer          â”‚
â”‚           â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”¬â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜                        â”‚
â”‚                           â”‚  WebSocket  (binary + JSON)            â”‚
â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”¼â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
                            â”‚
                 wss://flowlens-backend-rxwer3bgva-uk.a.run.app
                            â”‚
â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”¼â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
â”‚  FastAPI Backend  (Cloud Run Â· us-east4)                           â”‚
â”‚                           â”‚                                         â”‚
â”‚  /ws/{session_id}  â”€â”€â”€â”€â”€â”€â”€â”˜                                         â”‚
â”‚  â”œâ”€â”€ session ID validation (regex, 1â€“64 chars)                      â”‚
â”‚  â”œâ”€â”€ binary frames â†’ session.send(audio, mime=pcm;rate=16000)       â”‚
â”‚  â”œâ”€â”€ base64 frames â†’ session.send(image/jpeg)                       â”‚
â”‚  â””â”€â”€ receive loop:                                                  â”‚
â”‚       â”œâ”€â”€ audio chunks â”€â”€â–º WS binary â”€â”€â–º speakers                  â”‚
â”‚       â”œâ”€â”€ input_transcription â”€â”€â–º Redis memory                      â”‚
â”‚       â””â”€â”€ latency event â”€â”€â–º WS JSON â”€â”€â–º UI                         â”‚
â”‚                                                                      â”‚
â”‚  â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”   â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”    â”‚
â”‚  â”‚  agent.py          â”‚   â”‚  memory.py                         â”‚    â”‚
â”‚  â”‚  Gemini Live v1Î±   â”‚   â”‚  Redis Â· rolling 10-turn window    â”‚    â”‚
â”‚  â”‚  bidiGenContent    â”‚   â”‚  safe JSON deserialize             â”‚    â”‚
â”‚  â””â”€â”€â”€â”€â”€â”€â”€â”€â”¬â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜   â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜    â”‚
â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”¼â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
            â”‚
    Gemini 2.5 Flash Native Audio
    gemini-2.5-flash-native-audio-latest
```

---

## Gemini Live API Integration

FlowLens uses the **v1alpha bidirectional streaming API** â€” not the standard generate API.

```python
# agent.py
config = types.LiveConnectConfig(
    response_modalities=["AUDIO"],
    speech_config=types.SpeechConfig(
        voice_config=types.VoiceConfig(
            prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name="Charon")
        )
    ),
    input_audio_transcription=types.AudioTranscriptionConfig(),  # capture user speech as text
    system_instruction=types.Content(parts=[types.Part(text=system_prompt)]),
    thinking_config=types.ThinkingConfig(thinking_budget=0),     # disable CoT â†’ lower latency
)

async with client.aio.live.connect(model=LIVE_MODEL, config=config) as session:
    await session.send(input=pcm_bytes,  end_of_turn=False)           # audio
    await session.send(input={"mime_type": "image/jpeg", "data": b64}) # screen frame
```

> **Why `thinking_budget=0`?** Chain-of-thought adds 600â€“1200ms to first-byte latency. For real-time voice, we want raw inference. The screen frame already provides all the visual context needed.

---

## Latency Breakdown

| Stage | p50 | p95 |
|---|---|---|
| WS send (PCM) | ~5ms | ~15ms |
| Gemini first audio byte | ~900ms | ~1800ms |
| WS receive + decode | ~10ms | ~25ms |
| **Total (hold â†’ hear)** | **~1.4s** | **~2.8s** |

---

## Project Structure

```
flowlens/
â”‚
â”œâ”€â”€ backend/                          FastAPI backend
â”‚   â”œâ”€â”€ main.py                       WebSocket endpoint, CORS, /health, latency
â”‚   â”œâ”€â”€ agent.py                      Gemini Live API session lifecycle
â”‚   â”œâ”€â”€ memory.py                     Redis conversation buffer
â”‚   â”œâ”€â”€ screen.py                     JPEG encode helpers
â”‚   â”œâ”€â”€ static/index.html             Landing page at Cloud Run URL
â”‚   â”œâ”€â”€ requirements.txt
â”‚   â””â”€â”€ Dockerfile                    Multi-stage, non-root
â”‚
â”œâ”€â”€ frontend/                         Electron + React overlay
â”‚   â”œâ”€â”€ electron/
â”‚   â”‚   â”œâ”€â”€ main.js                   Window creation, IPC, screen permissions
â”‚   â”‚   â”œâ”€â”€ preload.js                contextBridge API
â”‚   â”‚   â””â”€â”€ entitlements.mac.plist    macOS mic + screen entitlements
â”‚   â””â”€â”€ src/
â”‚       â”œâ”€â”€ App.jsx                   4-state machine: IDLEâ†’LISTENINGâ†’PROCESSINGâ†’SPEAKING
â”‚       â”œâ”€â”€ components/
â”‚       â”‚   â”œâ”€â”€ StatusBar.jsx         Connection dot + latency + state label
â”‚       â”‚   â”œâ”€â”€ ScreenPreview.jsx     Live JPEG thumbnail
â”‚       â”‚   â””â”€â”€ VoiceIndicator.jsx    CSS-only animated waveform bars
â”‚       â””â”€â”€ hooks/
â”‚           â”œâ”€â”€ useWebSocket.js       WS connect/reconnect, AudioWorklet mic, audio send
â”‚           â””â”€â”€ useScreenCapture.js   getDisplayMedia, 1 FPS canvas JPEG
â”‚
â”œâ”€â”€ infra/terraform/                  Infrastructure as Code
â”‚   â”œâ”€â”€ main.tf                       Cloud Run + Artifact Registry + Redis + IAM
â”‚   â”œâ”€â”€ variables.tf
â”‚   â””â”€â”€ outputs.tf
â”‚
â”œâ”€â”€ scripts/
â”‚   â””â”€â”€ submission_check.py           13-point hackathon submission checker
â”‚
â”œâ”€â”€ tests/                            98 passing tests
â”‚   â”œâ”€â”€ test_agent.py
â”‚   â”œâ”€â”€ test_memory.py
â”‚   â”œâ”€â”€ test_screen.py
â”‚   â””â”€â”€ test_main.py
â”‚
â”œâ”€â”€ cloudbuild.yaml                   Cloud Build CI/CD
â”œâ”€â”€ docker-compose.yml                Local dev: backend + Redis
â””â”€â”€ .env.example                      All env vars documented
```

---

## Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `GEMINI_API_KEY` | âœ… | â€” | [Google AI Studio](https://aistudio.google.com/app/apikey) |
| `REDIS_URL` | optional | `redis://localhost:6379/0` | Conversation memory store |
| `LIVE_MODEL` | optional | `gemini-2.5-flash-native-audio-latest` | Override Live model |
| `VISION_MODEL` | optional | `gemini-2.5-flash` | Override vision model |
| `CLOUD_RUN_URL` | operations | â€” | Set after first deploy |
| `VITE_WS_URL` | frontend | `ws://localhost:8000` | Backend WebSocket URL |

---

## Cloud Run Deployment

```bash
gcloud auth login
gcloud config set project gen-lang-client-0435276974

gcloud builds submit --config=cloudbuild.yaml --project=gen-lang-client-0435276974
```

Config applied automatically (`cloudbuild.yaml`):

```yaml
--timeout=3600          # Supports long WebSocket sessions
--session-affinity      # Sticky routing â€” stateful WS sessions
--min-instances=1       # No cold starts
--max-instances=10
--set-secrets=GEMINI_API_KEY=GEMINI_API_KEY:latest
```

**Health check:**

```bash
curl https://flowlens-backend-rxwer3bgva-uk.a.run.app/health
# {"status":"healthy","gemini_connected":true}
```

---

## Tech Stack

<div align="center">

| Category | Technology |
|---|---|
| ðŸ§  AI Model | Gemini 2.5 Flash Native Audio |
| ðŸ”— AI API | Gemini Live API v1alpha Â· `bidiGenerateContent` |
| ðŸ–¥ï¸ Desktop | Electron 33 Â· React 18 Â· Vite 6 |
| ðŸŽ™ï¸ Audio | Web AudioWorklet Â· PCM Int16 Â· 16 kHz |
| ðŸ“¸ Screen | `getDisplayMedia` Â· Canvas JPEG encode |
| âš¡ Backend | FastAPI Â· Python 3.11 Â· asyncio |
| ðŸ’¾ Memory | Redis Â· rolling 10-turn context window |
| â˜ï¸ Cloud | Google Cloud Run Â· Cloud Build Â· Artifact Registry |
| ðŸ—ï¸ IaC | Terraform Â· Secret Manager |
| ðŸŽ¨ UI | Tailwind CSS Â· CSS keyframe animations |

</div>

---

## Key Engineering Decisions

<details>
<summary><strong>Why AudioWorklet instead of MediaRecorder?</strong></summary>

`MediaRecorder` buffers audio in WebM/Opus container format every ~250ms. The Gemini Live API requires raw PCM with MIME type `audio/pcm;rate=16000`. `AudioWorkletNode` runs in a dedicated audio thread, fires 128-sample callbacks (~8ms at 16kHz), and lets us encode Int16 PCM directly â€” zero container overhead.

</details>

<details>
<summary><strong>Why thinking_budget=0?</strong></summary>

Gemini's chain-of-thought adds 600â€“1200ms to first-byte latency. For a real-time voice agent with visual screen context already provided, deliberate reasoning increases latency without meaningful quality gain. Disabled for sub-2s p50 target.

</details>

<details>
<summary><strong>Why session affinity on Cloud Run?</strong></summary>

A Gemini `bidiGenerateContent` stream and its Redis session state are tied to a specific backend process. Without sticky routing, mid-session WebSocket reconnects land on a cold instance with no open Gemini session â€” silently dropping the conversation. `--session-affinity` routes by cookie to the same instance.

</details>

<details>
<summary><strong>Why Electron instead of a browser extension?</strong></summary>

Three capabilities are unavailable to browser extensions: (1) system audio loopback capture, (2) always-on-top window above all other apps, (3) global keyboard shortcuts via `globalShortcut` API. Electron provides all three with a single React codebase.

</details>

---

## Bugs Squashed

| Bug | Root Cause | Fix |
|---|---|---|
| "No audio received" | `audio_end` fired before AudioWorklet init (~200ms) completed | Await `micInitPromise` in `stopMic` before sending `audio_end` |
| Blank screen on launch | `stopMic` declared below `useEffect` that used it â€” JS TDZ | Hoisted all `useCallback` above `useEffect` |
| WS sessions killed at 60s | Cloud Run default `timeoutSeconds=60` | `timeoutSeconds=3600` in `cloudbuild.yaml` |
| Mic echo / feedback | `workletNode.connect(ctx.destination)` piped mic â†’ speakers | Removed â€” sourceâ†’worklet only |
| SPEAKING state freezes | No fallback if Gemini omits final transcript | 5s timeout â†’ force `IDLE` |
| Stale keyboard handlers | React closures captured stale `appState` at mount | Sync state â†’ `useRef`, read `.current` in handlers |
| Windows stdout crash | `cp1252` can't encode Unicode box-drawing chars | Wrap `sys.stdout` in UTF-8 `TextIOWrapper` |
| Screen capture AbortError | `startCapture` called twice while stream loading | Guard: `if (streamRef.current) return` |

---

## Tests

```bash
cd backend
pip install -r requirements.txt
pytest tests/ -v
# 98 passed in 2.34s
```

---

## Links

| | |
|---|---|
| ðŸŒ Live Backend | https://flowlens-backend-rxwer3bgva-uk.a.run.app |
| ðŸ’š Health Check | https://flowlens-backend-rxwer3bgva-uk.a.run.app/health |
| ðŸ’» Source Code | https://github.com/krishnashakula/flowlens |
| ðŸ‘¤ GDG Profile | https://gdg.community.dev/u/m45uxf/#/about |
| ðŸ† Hackathon | https://geminiliveagentchallenge.devpost.com |

---

## Hackathon

**Challenge:** Gemini Live Agent Challenge 2026
**Track:** Live Agent
**Mandatory tech:** Gemini Live API Â· Google Cloud Run Â· `google-genai` SDK

> *"I created this piece of content for the purposes of entering the Gemini Live Agent Challenge hackathon."*

---

<div align="center">

MIT License © 2026 Krishna Shakula

</div>
