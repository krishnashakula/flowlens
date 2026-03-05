# FlowLens

> **Real-time voice + vision AI agent** — speak to your screen, get answers in under 3 seconds.

Built for the [Gemini Live Agent Challenge](https://geminiliveagentchallenge.devpost.com/) · Powered by Gemini Live API · Deployed on Google Cloud Run

---

## The Problem

Every time a developer or designer hits a visual problem, the current workflow kills momentum:

1. Screenshot the screen
2. Alt-tab to ChatGPT
3. Attach the image
4. **Type** a description of what's wrong

**Average time: 34 seconds.** That's context-switching overhead, every single time.

## The Solution

FlowLens sits as a floating window in the corner of your screen. Hold Space, ask your question out loud, and get a voice answer in **2.8 seconds** — while FlowLens can already see everything on your screen.

```
BEFORE → user screenshots Figma, pastes into ChatGPT, types description: 34 seconds
AFTER  → user holds space, speaks to FlowLens which sees screen: 2.8 seconds
```

---

## Quick Start (one command)

```bash
# 1. Clone and configure
git clone https://github.com/your-org/flowlens.git
cd flowlens
cp .env.example .env
# Edit .env: set GEMINI_API_KEY=your-key-here

# 2. Start local stack (backend + redis)
docker compose up

# 3. In a separate terminal — start the Electron app
cd frontend
npm install
npm run dev
```

Backend will be live at `http://localhost:8000`. Health check: `http://localhost:8000/health`.

---

## Architecture

```
┌─────────────────────────────────────────────────────┐
│  Electron Desktop App (React + Vite)                │
│  ├── Screen capture: getDisplayMedia() 1 FPS        │
│  ├── Audio: WebRTC microphone, 100ms chunks         │
│  └── WebSocket client → FastAPI backend             │
├─────────────────────────────────────────────────────┤
│  FastAPI Backend (Google Cloud Run)                 │
│  ├── gemini-2.0-flash-live-001 — voice streaming    │
│  ├── gemini-2.0-flash — screen frame analysis       │
│  ├── asyncio.gather() — parallel frame + voice      │
│  └── Redis (GCP Memorystore) — last 5 exchanges     │
├─────────────────────────────────────────────────────┤
│  Infrastructure (Terraform IaC)                     │
│  ├── Cloud Run (min_instances=1, no cold start)     │
│  ├── Artifact Registry — container images           │
│  └── Memorystore Redis — conversation state         │
└─────────────────────────────────────────────────────┘
```

### Latency optimizations

| Optimization | Before | After | Saving |
|---|---|---|---|
| JPEG compression (60%) | 2-4MB PNG | ~80KB JPEG | ~300ms |
| Gemini connection pooling | new client/req | reused client | ~500ms |
| Parallel frame+voice setup | sequential | `asyncio.gather()` | ~400ms |
| 100ms audio chunks | full buffer on release | streaming | ~200ms |
| Redis pipelining | 2 round trips | 1 pipeline | ~20ms |

**Total savings: ~1420ms → p50 target < 2500ms**

---

## Project Structure

```
flowlens/
├── backend/
│   ├── main.py          FastAPI app, WebSocket endpoint, /health
│   ├── agent.py         Core: Gemini Live API + vision integration
│   ├── memory.py        Conversation buffer (last 5 exchanges)
│   ├── screen.py        JPEG compression utilities
│   ├── requirements.txt Python deps (pinned)
│   └── Dockerfile       Multi-stage, non-root user
├── frontend/
│   ├── electron/
│   │   ├── main.js      Electron main process, 380×520 floating window
│   │   └── preload.js   contextBridge API
│   └── src/
│       ├── App.jsx       4-state UI: IDLE/LISTENING/PROCESSING/SPEAKING
│       ├── components/
│       │   ├── StatusBar.jsx
│       │   ├── ScreenPreview.jsx
│       │   └── VoiceIndicator.jsx
│       └── hooks/
│           ├── useWebSocket.js    Auto-reconnect, audio streaming
│           └── useScreenCapture.js getDisplayMedia, 1 FPS JPEG
├── infra/terraform/
│   ├── main.tf          Cloud Run + Artifact Registry + Redis + IAM
│   ├── variables.tf
│   └── outputs.tf
├── scripts/
│   └── submission_check.py  Pre-submission completeness checker
├── .github/workflows/
│   └── deploy.yml       CI/CD: test → build → push → terraform apply
├── docker-compose.yml   Local dev: backend + redis
├── .env.example         All required env vars documented
├── Makefile             make dev / build / deploy / latency / check
└── README.md            ← you are here
```

---

## Available Commands

```bash
make dev        # Start local backend + redis
make test       # Run pytest suite
make build      # Build + push Docker image to Artifact Registry
make deploy     # Full GCP deploy (build + terraform apply)
make logs       # Tail Cloud Run logs
make latency    # Show p50/p95 latency from /health endpoint
make demo       # Open live demo in browser
make check      # Run submission completeness checker
```

---

## Required Environment Variables

| Variable | Required | Description |
|---|---|---|
| `GEMINI_API_KEY` | ✅ | From [Google AI Studio](https://aistudio.google.com/app/apikey) |
| `REDIS_URL` | optional | Default: `redis://localhost:6379/0` |
| `GCP_PROJECT_ID` | deploy only | Your Google Cloud project |
| `GCP_REGION` | deploy only | Default: `us-central1` |
| `CLOUD_RUN_URL` | operations | Set after first deploy |

---

## GCP Deployment

```bash
# Authenticate
gcloud auth login
gcloud auth application-default login

# Set project
gcloud config set project YOUR_PROJECT_ID

# Deploy (builds, pushes, terraform apply in one command)
make deploy
```

After deploy, verify at `$(CLOUD_RUN_URL)/health`:

```json
{
  "status": "healthy",
  "gemini_connected": true,
  "redis_connected": true,
  "p50_latency_ms": 2100,
  "p95_latency_ms": 2800,
  "total_sessions": 47
}
```

---

## Hackathon Track

**Track:** Live Agent  
**Mandatory tech:** Gemini Live API · ADK · Google Cloud Run  
**Challenge:** [geminiliveagentchallenge.devpost.com](https://geminiliveagentchallenge.devpost.com)

> *"I created this piece of content for the purposes of entering the Gemini Live Agent Challenge hackathon."*

---

## License

MIT
