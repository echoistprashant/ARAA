# Autonomous Research & Analysis Agent (ARAA)

[![CI](https://github.com/echoistprashant/ARAA/actions/workflows/ci.yml/badge.svg)](https://github.com/echoistprashant/ARAA/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Cost: $0.00](https://img.shields.io/badge/Cost-$0.00%20Zero--Cost-brightgreen.svg)](#zero-cost-setup)

A production-grade, bounded, observable, and permission-controlled autonomous research agent that plans tasks, executes tools via **native Function Calling** and **Model Context Protocol (MCP)**, sandboxes code execution, and delivers citation-backed reports with human approval gates.

---

## 1. Problem Solved

Knowledge workers spend hours querying search engines, reading dozens of unstructured documents, writing scratchpad scripts to compute metrics, and cross-referencing conflicting numbers.

* **Single LLM calls** hallucinate facts and cannot browse or compute accurately.
* **Toy agents** get stuck in infinite loops, waste money, and execute unverified actions.
* **ARAA** implements **bounded autonomy**: the LLM proposes actions within typed JSON schemas, but deterministic software controls the loop, enforces hard budgets, requires human approval for risky steps, and verifies every claim against recorded evidence.

---

## 2. Core Architecture

```
User Task ---> API (FastAPI) ---> Queue (Redis) ---> Worker (Orchestrator Loop)
                                                           |
          +------------------------------------------------+
          |
          v
   [ 1. Planner ] ---> Decomposes goal into checkable sub-goals
          |
          v
   [ 2. Loop (Reason -> Tool -> Observe) ]
          |-- Step / Cost / Time Budget Enforcement
          |-- Loop & Stall Detector (3 identical calls without new facts = abort)
          |-- Policy & Risk Engine (Read / External / Write / Dangerous)
          |-- Tool Execution (Local functions, MCP servers, Docker sandbox)
          |-- Untrusted Data Boundaries & Provenance Recording
          |-- Step Checkpoint in PostgreSQL
          |
          v
   [ 3. Verifier & Synthesizer ] ---> Verifies claims vs evidence, outputs cited report
```

---

## 3. Tool Permission & Risk Tiers

| Risk Tier | Examples | Policy |
| :--- | :--- | :--- |
| **Tier 1: Read** | `calculator`, `rag_search` | Auto-allowed |
| **Tier 2: Read-External** | `web_search`, `fetch_url` | Allowed with domain policy, size caps, and SSRF blocking |
| **Tier 3: Write / Side-Effect** | `send_email`, `create_ticket` | **Approval Required** (exact argument hash verified) |
| **Tier 4: Dangerous** | `system_shell`, `delete_data` | **Disabled by default** |

---

## 4. Zero-Cost Setup ($0.00)

ARAA is engineered to run completely free of cost using open-source infrastructure and free developer tiers:

* **LLM Engine:** Google AI Studio (Gemini 2.0 Flash Free Tier) or Groq Cloud Free Tier or local Ollama.
* **Search Engine:** DuckDuckGo (Free, no API key needed) or Tavily (1,000 free requests/mo).
* **Datastore:** PostgreSQL 16 + pgvector running in local Docker.
* **Cache & Bus:** Redis 7 running in local Docker.
* **Observability:** Self-hosted Langfuse via Docker.

### Quickstart

1. **Clone the repository:**
   ```bash
   git clone https://github.com/echoistprashant/ARAA.git
   cd ARAA
   ```

2. **Create and activate a virtual environment:**
   ```bash
   python -m venv .venv
   # Windows:
   .venv\Scripts\activate
   # Linux/macOS:
   source .venv/bin/activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -e ".[dev]"
   ```

4. **Configure environment:**
   ```bash
   cp .env.example .env
   # Edit .env with your free Gemini API key (https://aistudio.google.com/)
   ```

5. **Start local database & Redis:**
   ```bash
   docker compose up -d
   ```

6. **Run the API server:**
   ```bash
   uvicorn app.main:app --reload --port 8000
   ```
   Visit `http://localhost:8000/health` or `http://localhost:8000/docs`.

7. **Run tests:**
   ```bash
   pytest
   ```

---

## 5. Implementation Roadmap (16 Phases)

* [x] **Phase 1: Project Setup & CI Skeleton** (Repo, 12-factor config, structured JSON logging, health probes, CI)
* [ ] **Phase 2: LLM Tool-Calling Fundamentals** (Function calling at the wire level without frameworks)
* [ ] **Phase 3: State & Deterministic Orchestrator** (RunState, budgets, loop detection)
* [ ] **Phase 4: Tool Framework & Registry** (Pydantic schemas, timeouts, error taxonomy)
* [ ] **Phase 5: Planning & Replanning** (Plan-and-execute vs ReAct)
* [ ] **Phase 6: Persistence & Resume** (Step checkpoints, idempotency keys, crash recovery)
* [ ] **Phase 7: Memory & Evidence Store** (Working memory, episodic compression, pgvector)
* [ ] **Phase 8: Model Context Protocol (MCP)** (MCP client adapter & research tool servers)
* [ ] **Phase 9: Permissions & Human-in-the-Loop** (Policy engine, approval gates, TOCTOU defense)
* [ ] **Phase 10: Sandboxed Code Execution** (Isolated container, no-network, resource limits)
* [ ] **Phase 11: Verification & Synthesis** (Claim checking against evidence)
* [ ] **Phase 12: Agent Evaluation (AgentOps)** (30–60 task benchmark, pass@k, trajectory metrics)
* [ ] **Phase 13: Observability & Tracing** (OpenTelemetry spans, Langfuse dashboard)
* [ ] **Phase 14: Security Hardening** (SSRF, indirect prompt injection tests)
* [ ] **Phase 15: Docker & Cloud Deployment**
* [ ] **Phase 16: Performance & Optimization** (Caching, model routing)

---

## 6. Security Principles

1. **"The Model Proposes, The Policy Engine Disposes":** The LLM never has root or direct OS access.
2. **Untrusted Data Boundaries:** All web text is marked untrusted to prevent prompt injections from overriding instructions.
3. **No-Network Sandbox:** Agent-written Python code is executed in an isolated container with `--net=none`.
