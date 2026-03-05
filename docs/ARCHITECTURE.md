# Architecture Diagram

Place your architecture diagram here as `architecture.png` or `architecture.svg`.

You can generate one using:
- [draw.io](https://draw.io) (free, export as PNG)
- [Mermaid Live](https://mermaid.live) (paste diagram below, screenshot)

## Mermaid source

```mermaid
graph TB
    subgraph Desktop["Electron Desktop App"]
        UI[React UI - 4 states]
        SC[Screen Capture - 1 FPS JPEG]
        MIC[Microphone - PCM 100ms chunks]
        WS_CLIENT[WebSocket Client]
        UI --> WS_CLIENT
        SC --> WS_CLIENT
        MIC --> WS_CLIENT
    end

    subgraph CloudRun["Google Cloud Run (us-central1)"]
        FASTAPI[FastAPI Backend]
        AGENT[FlowLensAgent]
        MEMORY[ConversationMemory]
        SCREEN_PROC[Screen Processor - JPEG compress]
        FASTAPI --> AGENT
        AGENT --> MEMORY
        AGENT --> SCREEN_PROC
    end

    subgraph GeminiAPIs["Gemini APIs"]
        LIVE[gemini-2.0-flash-live-001 - Voice]
        VISION[gemini-2.0-flash - Vision]
    end

    subgraph GCPInfra["GCP Infrastructure"]
        REDIS[(Memorystore Redis)]
        ARTIFACT[Artifact Registry]
        SECRETS[Secret Manager]
    end

    WS_CLIENT <-->|WebSocket| FASTAPI
    AGENT <-->|asyncio.gather| LIVE
    AGENT <-->|asyncio.gather| VISION
    MEMORY <--> REDIS
    FASTAPI -.->|reads| SECRETS
    CloudRun -.->|image from| ARTIFACT
```

Copy this Mermaid source into [mermaid.live](https://mermaid.live), screenshot the result,
and save it as `docs/architecture.png`.
