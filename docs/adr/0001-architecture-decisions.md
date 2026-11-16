# ADR 0001: Core Architecture & Framework Selection

## Status
Accepted

## Context
When building autonomous research agents, developers frequently face choices between all-in-one frameworks (such as LangChain or AutoGen) and custom, deterministic orchestration harnesses.

## Decision
1. **Deterministic Control Loop:** Build the core loop in custom Python code rather than relying entirely on opaque framework abstractions. The orchestrator explicitly manages state transitions, step budgets, and termination conditions.
2. **Model Context Protocol (MCP):** Use MCP for modular tool integration. This decouples tool implementation from the agent's core reasoning engine and enables seamless reuse across hosts.
3. **PostgreSQL + pgvector:** Single transactional datastore for both relational run checkpoints and semantic vector retrieval over intermediate evidence.
4. **Zero-Cost Design:** Support free provider tiers (Google Gemini Free Tier, Groq, local Ollama) and free search options (DuckDuckGo, Tavily Free Tier) so development and evaluation require $0.

## Consequences
* High transparency and debuggability.
* No framework lock-in.
* Clear trust boundaries: the model proposes, deterministic software disposes.
