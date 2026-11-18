<div align="center">

# Autonomous Research & Analysis Agent (ARAA)

**Deep web investigation, empirical evidence synthesis, and verifiable agent trajectories.**

[![Live Demo](https://img.shields.io/badge/Live%20Demo-araa.prshnt.com-blue?style=for-the-badge&logo=cloudflare&logoColor=white)](https://araa.prshnt.com/)
[![Python 3.12](https://img.shields.io/badge/Python-3.12-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Docker](https://img.shields.io/badge/Docker-Production%20Ready-2496ED?style=for-the-badge&logo=docker&logoColor=white)](https://www.docker.com/)
[![Zero Cost](https://img.shields.io/badge/Cost-$0.00%20Forever-22C55E?style=for-the-badge)](https://araa.prshnt.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=for-the-badge)](https://opensource.org/licenses/MIT)

[**Explore Live Agent**](https://araa.prshnt.com/) • [**System Architecture**](#-system-architecture) • [**Security & Guardrails**](#-tool-permission--security-matrix) • [**Quickstart**](#-quickstart-local-development) • [**API Reference**](#-api--streaming-reference)

---

> 🚀 **Live Production Application:** **[https://araa.prshnt.com](https://araa.prshnt.com)**  
> ARAA is fully deployed and accessible globally. No local installation, Docker containers, or API keys are required to use the agent.

</div>

## Overview

**ARAA (Autonomous Research and Analysis Agent)** is a production-grade, bounded, observable, and permission-governed autonomous agent. It decomposes complex research directives into auditable multi-step plans, gathers live web intelligence, runs sandboxed computations, and synthesizes grounded reports with verifiable citations.

Unlike toy autonomous agents that loop indefinitely, hallucinate unchecked facts, or rack up surprise API costs, ARAA is built on the core principle:

> **"The Model Proposes, The Policy Engine Disposes."**  
> *The LLM is treated as an untrusted reasoning engine. Hard deterministic software controls state transitions, enforces cost and step budgets, sandboxes code execution, and requires cryptographic human approvals for privileged mutations.*

---

## Key Highlights

- **Exa.ai-Inspired Minimalist Interface**: Clean, editorial-grade UI styled with *Instrument Serif*, *Inter*, and *JetBrains Mono*, complete with instant prompt chips, real-time telemetry, and dark/light themes.
- **Frameworkless Wire-Level Control**: Built with raw `asyncio`, `httpx`, and `pydantic`—zero bloat from heavy frameworks like LangChain or AutoGen.
- **Deterministic Loop & Anti-Stall Guard**: Automatically detects repetitive calls (3 identical actions with no new knowledge = automatic loop break) and enforces hard step/budget ceilings.
- **Role-Based Access Control (RBAC) & HITL**: Distinct permission tiers (`Viewer`, `Researcher`, `Operator`, `Admin`) with cryptographic token-hashed Human-in-the-Loop approvals for side effects.
- **Multi-Source Intelligence**: Dual-mode web search with **Tavily AI Search** and zero-key **DuckDuckGo**, protected by Anti-SSRF IP boundary validators.
- **Isolated Code Sandbox**: Executes Python calculations and data processing in resource-capped subprocesses (`timeout: 5s`, `memory: 128MB`, strict stdout truncation).
- **Episodic Vector Memory**: Native `pgvector` embeddings in PostgreSQL for persistent knowledge retrieval across investigation sessions.
- **100% Zero-Cost Deployment**: Engineered to run on permanent free-tier cloud infrastructure (Neon Postgres + Upstash Redis + Google AI Studio + Cloudflare).

---

## System Architecture

```
User Directive ──► FastAPI (REST & SSE) ──► Redis Stream ──► Orchestrator Loop
                                                                    │
   ┌────────────────────────────────────────────────────────────────┴──────────────────┐
   ▼                                                                                   ▼
1. Planner Subsystem                                                    2. Deterministic Loop Controller
   • Goal Decomposition                                                    • Step & Budget Ceilings
   • Sub-task Sequencing                                                   • 3-Call Loop & Stall Detector
                                                                           • Untrusted Data Sanitation
                                                                           • Step Checkpoints in PostgreSQL
                                                                                       │
   ┌───────────────────────────────────────────────────────────────────────────────────┘
   ▼
3. Tool Execution Registry (RBAC & Policy Engine)
   ├── Tier 1 (Read): Calculator, RAG Vector Search
   ├── Tier 2 (External): Web Search (Tavily/DDG), Anti-SSRF URL Fetcher
   ├── Tier 3 (Write / Sandboxed): Python Subprocess Sandbox (Resource Bounded)
   └── Tier 4 (Dangerous): System Shell (Disabled by Default)
   │
   ▼
4. Grounding Verifier & Synthesizer
   • NLI Claim Checking vs. Recorded Evidence
   • Grounding Audit Score Calculation (0 - 100%)
   • Structured Final Markdown Report with Source Citations
```

---

## Tool Permission & Security Matrix

| Risk Tier | Tools Available | Default Policy | Human Approval Required? |
| :--- | :--- | :--- | :---: |
| **Tier 1: Read** | `calculator`, `evidence_search` | Auto-approved across all roles | No |
| **Tier 2: Read External** | `web_search`, `fetch_url` | Auto-approved for `Researcher`, `Operator`, `Admin` | No |
| **Tier 3: Write / Exec** | `python_sandbox` | Auto for `Operator`/`Admin`; Pauses for `Researcher` | **Yes (HITL)** |
| **Tier 4: Dangerous** | `system_shell`, destructive ops | Strictly forbidden | **Disabled** |

### Security Defenses Built-In
1. **Anti-SSRF Protection**: Internal private networks (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`, `127.0.0.1`, `169.254.169.254` AWS/GCP metadata endpoints) are actively blocked from tool-based fetching.
2. **Untrusted Data Isolation**: All external web excerpts are wrapped in untrusted boundary tags to prevent indirect prompt injection from hijacking agent instructions.
3. **TOCTOU Defense**: Approval tokens are hashed against the exact proposed tool arguments. Altering arguments invalidates the approval token.

---

## Zero-Cost Cloud Deployment ($0.00/Month)

ARAA is deployed live in production using permanent free-tier services:

| Component | Provider | Tier Details |
| :--- | :--- | :--- |
| **Edge & SSL** | [Cloudflare](https://www.cloudflare.com/) | Global DNS, DDoS protection, automatic SSL ([araa.prshnt.com](https://araa.prshnt.com/)) |
| **Web Service** | [Render](https://render.com/) | Multi-stage Docker container runner (`python:3.12-slim`) |
| **Database** | [Neon.tech](https://neon.tech/) | Serverless PostgreSQL with native `pgvector` support |
| **Cache & Bus** | [Upstash](https://upstash.com/) | Serverless Redis (10,000 commands/day free) |
| **LLM Provider** | [Google AI Studio](https://aistudio.google.com/) | Gemini 2.0 / 3.5 Flash Lite Free Tier |
| **Web Search** | [Tavily](https://tavily.com/) / DuckDuckGo | 1,000 free requests/month with DuckDuckGo fallback |

---

## Getting Started & Live Access

### 🚀 Instant Access (Production Live)

The fastest way to experience ARAA is through the live deployment:

👉 **[https://araa.prshnt.com](https://araa.prshnt.com)**

The live deployment is connected to Google Gemini, Neon PostgreSQL (`pgvector`), Upstash Redis, and Cloudflare edge security. You can run multi-step research investigations, inspect streaming agent trajectories, review empirical grounding audits, and test all four permission roles directly in your browser.

---

### 🛠️ Developer Setup (Self-Hosting from Source)

If you wish to contribute to ARAA or run a self-hosted instance locally:

#### 1. Prerequisites
- Python 3.12+
- Docker & Docker Compose (for local database and Redis cluster)
- Free Gemini API key from [Google AI Studio](https://aistudio.google.com/)

#### 2. Installation
```bash
# Clone the repository
git clone https://github.com/echoistprashant/ARAA.git
cd ARAA

# Create and activate virtual environment
python -m venv .venv

# Windows:
.venv\Scripts\activate
# Linux / macOS:
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

#### 3. Environment Setup
Create a `.env` file from the provided template:
```bash
cp .env.example .env
```
Populate your environment variables:
```ini
APP_ENV=local
DEBUG=true
PORT=8000

# LLM Configuration
LLM_PROVIDER=gemini
GEMINI_API_KEY=your_gemini_api_key_here
PLANNER_MODEL=gemini-3.5-flash-lite
ACTOR_MODEL=gemini-3.5-flash-lite
VERIFIER_MODEL=gemini-3.5-flash-lite

# Search Configuration
SEARCH_PROVIDER=duckduckgo
# Optional: TAVILY_API_KEY=tvly-...

# Storage (Docker Compose or Cloud)
DATABASE_URL=postgresql+asyncpg://araa_user:araa_password@localhost:5433/araa_db
REDIS_URL=redis://localhost:6380/0
JWT_SECRET=change-this-to-a-secure-random-secret
```

#### 4. Launch Local Development Server
```bash
# Start local Postgres (pgvector) and Redis
docker compose up -d

# Start ARAA development server
uvicorn app.main:create_app --factory --reload --port 8000
```
The server will start on port 8000, or you can access the live production deployment anytime at **[https://araa.prshnt.com](https://araa.prshnt.com)**.

---

## Docker Production Build

Build and run the production image locally using Docker:
```bash
# Build multi-stage production image
docker build -t araa:latest .

# Run container as unprivileged non-root user (port 8000)
docker run -p 8000:8000 --env-file .env araa:latest
```

---

## API & Streaming Reference

### Create an Investigation Run
```http
POST /api/v1/runs
Content-Type: application/json

{
  "task": "Investigate ASML extreme ultraviolet lithography market share in 2026",
  "role": "researcher"
}
```

**Response (200 OK):**
```json
{
  "run_id": "run_9a8b7c6d5e",
  "task": "Investigate ASML extreme ultraviolet lithography market share in 2026",
  "status": "queued",
  "step_count": 0,
  "final_report": null,
  "audit_passed": null
}
```

### Stream Live Trajectory Events (Server-Sent Events)
```http
GET /api/v1/runs/{run_id}/events
Accept: text/event-stream
```

Streams real-time JSON events:
- `plan_created`: Decomposed sub-task roadmap.
- `step_started`: Model thought signature and proposed tool call.
- `tool_executed`: Observation output and provenance metadata.
- `approval_required`: Pauses execution for HITL confirmation.
- `report_generated`: Verifier audit score and cited markdown report.

### Submit Human Approval
```http
POST /api/v1/approvals/{approval_token}
Content-Type: application/json

{
  "approved": true
}
```

### Health & Liveness Probe
```http
GET /health
```
```json
{
  "status": "ok"
}
```

---

## Repository Structure

```
ARAA/
├── app/
│   ├── agents/          # Planner, Synthesizer, Verifier, Loop Detector, Budget
│   ├── api/v1/          # REST & SSE Endpoints (/runs, /events, /approvals)
│   ├── core/            # 12-factor configuration, logging, errors
│   ├── db/              # SQLAlchemy async session & pgvector models
│   ├── llm/             # Wire-level LLM clients (Gemini, Groq, Ollama)
│   ├── sandbox/         # Subprocess resource-bounded code executor
│   ├── static/          # Single-page Exa-inspired interface, tokens, monogram logo
│   ├── tools/           # Tool implementations (web_search, calculator, fetch_url)
│   └── main.py          # FastAPI application factory
├── tests/               # Unit, integration, and security test suite
├── Dockerfile           # Multi-stage unprivileged production container
├── docker-compose.yml   # Postgres (pgvector) & Redis local cluster
├── requirements.txt     # Locked production dependencies
├── pyproject.toml       # Hatchling project specifications
└── README.md            # Documentation
```

---

## Testing

Run the automated test suite:
```bash
# Run unit and API tests
pytest

# Run tests with coverage
pytest --cov=app --cov-report=term-missing
```

---

## License

This project is licensed under the [MIT License](LICENSE).

<div align="center">
  <sub>Built with precision by <a href="https://github.com/echoistprashant">Prashant Yadav</a>.</sub>
</div>
